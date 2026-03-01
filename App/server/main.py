import asyncio
import logging
import os
import platform
import string
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adb_executor import adb_executor
from .config import get_config, load_config, update_config
from .device_discovery import discovery_loop, handle_self_registration
from .device_manager import device_manager
from .models import (
    ConfigModel,
    DeviceNameUpdate,
    DeviceRegistration,
    OpenCommand,
    PlaybackCommand,
)
from .playback_controller import launch_player, open_video, ping_device, send_command
from .requirements_manager import check_requirements, run_update, run_usb_update
from .websocket_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vrclassroom")

_discovery_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _discovery_task
    # Startup
    load_config()
    has_adb = await adb_executor.check_adb()
    if not has_adb:
        logger.warning("ADB not found in PATH. ADB-dependent features will not work.")
    await device_manager.start()
    _discovery_task = asyncio.create_task(discovery_loop())
    logger.info("VR Classroom server started")
    yield
    # Shutdown
    if _discovery_task:
        _discovery_task.cancel()
    await device_manager.stop()
    logger.info("VR Classroom server stopped")


app = FastAPI(title="VR Classroom Control", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Config endpoints ─────────────────────────────────────────────────────────


@app.get("/api/config")
async def get_config_endpoint():
    return get_config()


@app.put("/api/config")
async def update_config_endpoint(config: ConfigModel):
    new_config = update_config(config.model_dump())
    await ws_manager.broadcast({"type": "config_updated", "config": new_config})
    return new_config


# ─── Device endpoints ─────────────────────────────────────────────────────────


@app.get("/api/devices")
async def get_devices():
    return await device_manager.get_all()


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    device = await device_manager.get_dict(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    return device


@app.put("/api/devices/{device_id}/name")
async def set_device_name(device_id: str, body: DeviceNameUpdate):
    success = await device_manager.update_name(device_id, body.name)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    return {"ok": True}


@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    success = await device_manager.remove(device_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    return {"ok": True}


@app.post("/api/devices/register")
async def register_device(reg: DeviceRegistration):
    await handle_self_registration(reg.model_dump())
    return {"ok": True}


@app.post("/api/devices/{device_id}/ping")
async def device_ping(device_id: str):
    result = await ping_device(device_id)
    return result


# ─── Requirements endpoints ───────────────────────────────────────────────────


@app.get("/api/devices/{device_id}/requirements")
async def get_requirements(device_id: str):
    device = await device_manager.get(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    results = await check_requirements(device_id)
    return {"deviceId": device_id, "requirements": results}


@app.post("/api/devices/{device_id}/update")
async def update_device(device_id: str):
    device = await device_manager.get(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    if not device.adb_connected:
        return JSONResponse(status_code=400, content={"error": "ADB not connected"})
    if device.update_in_progress:
        return JSONResponse(status_code=409, content={
            "error": "Update already in progress",
            "progress": device.update_progress,
        })

    # Run update in background
    asyncio.create_task(run_update(device_id))
    return {"ok": True, "message": "Update started"}


@app.post("/api/devices/update-all")
async def update_all_devices():
    config = get_config()
    devices = await device_manager.get_online_adb_devices()
    concurrency = config.get("updateConcurrency", 5)
    semaphore = asyncio.Semaphore(concurrency)

    started = []
    skipped = []

    async def update_with_semaphore(device_id: str):
        async with semaphore:
            await run_update(device_id)

    for d in devices:
        if d.update_in_progress:
            skipped.append(d.device_id)
            continue
        if d.requirements_met is True:
            skipped.append(d.device_id)
            continue
        started.append(d.device_id)
        asyncio.create_task(update_with_semaphore(d.device_id))

    return {"started": started, "skipped": skipped}


# ─── USB endpoints ───────────────────────────────────────────────────────────

@app.get("/api/usb-devices")
async def get_usb_devices():
    serials = await adb_executor.list_usb_devices()
    return {"devices": serials}


@app.post("/api/usb-devices/{serial}/update")
async def update_usb_device(serial: str):
    serials = await adb_executor.list_usb_devices()
    if serial not in serials:
        return JSONResponse(status_code=404, content={"error": "USB device not found"})
    asyncio.create_task(run_usb_update(serial))
    return {"ok": True, "message": f"USB update started for {serial}"}


# ─── File browse endpoint ────────────────────────────────────────────────────

@app.get("/api/browse")
async def browse_files(
    path: str = Query("", description="Directory path to browse"),
    filter: str = Query("", description="File extension filter, e.g. .apk,.mp4"),
):
    """Browse local file system for the file picker UI."""
    if not path:
        # Return drives on Windows, or home dir on Linux/Mac
        if platform.system() == "Windows":
            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.isdir(drive):
                    drives.append({"name": drive, "path": drive, "type": "directory"})
            return {"path": "", "entries": drives, "parent": ""}
        else:
            path = os.path.expanduser("~")

    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return JSONResponse(status_code=400, content={"error": "Not a directory"})

    entries = []
    ext_filter = set()
    if filter:
        for ext in filter.split(","):
            ext = ext.strip().lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            ext_filter.add(ext)

    try:
        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            if name.startswith("."):
                continue
            if os.path.isdir(full_path):
                entries.append({"name": name, "path": full_path, "type": "directory"})
            elif os.path.isfile(full_path):
                if ext_filter:
                    _, ext = os.path.splitext(name)
                    if ext.lower() not in ext_filter:
                        continue
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                entries.append({"name": name, "path": full_path, "type": "file", "size": size})
    except PermissionError:
        return JSONResponse(status_code=403, content={"error": "Permission denied"})

    parent = os.path.dirname(path)
    if parent == path:
        parent = ""

    return {"path": path, "entries": entries, "parent": parent}


# ─── Player launch endpoints ─────────────────────────────────────────────────


@app.post("/api/devices/launch-player")
async def launch_player_all(cmd: PlaybackCommand):
    """Launch the player app on all online ADB-connected devices."""
    return await launch_player(cmd.deviceIds)


@app.post("/api/devices/{device_id}/launch-player")
async def launch_player_single(device_id: str):
    """Launch the player app on a specific device via ADB."""
    device = await device_manager.get(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    if not device.adb_connected:
        return JSONResponse(status_code=400, content={"error": "ADB not connected"})
    return await launch_player([device_id])


# ─── Playback endpoints ──────────────────────────────────────────────────────


@app.post("/api/playback/open")
async def playback_open(cmd: OpenCommand):
    result = await open_video(cmd.videoId, cmd.deviceIds)
    return result


@app.post("/api/playback/play")
async def playback_play(cmd: PlaybackCommand):
    return await send_command("play", cmd.deviceIds)


@app.post("/api/playback/pause")
async def playback_pause(cmd: PlaybackCommand):
    return await send_command("pause", cmd.deviceIds)


@app.post("/api/playback/stop")
async def playback_stop(cmd: PlaybackCommand):
    return await send_command("stop", cmd.deviceIds)


@app.post("/api/playback/recenter")
async def playback_recenter(cmd: PlaybackCommand):
    return await send_command("recenter", cmd.deviceIds)


# ─── WebSocket endpoint ──────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        # Send initial snapshot
        devices = device_manager.get_snapshot()
        await ws_manager.send_to(ws, {
            "type": "snapshot",
            "devices": devices,
            "config": get_config(),
        })

        # Keep connection alive
        while True:
            try:
                data = await ws.receive_text()
                # Client can send ping/pong for keepalive
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(ws)


# ─── Static files (frontend) ─────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/settings")
    async def serve_settings():
        return FileResponse(FRONTEND_DIST / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST)), name="static")
