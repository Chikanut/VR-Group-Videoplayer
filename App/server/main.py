import asyncio
import json
import logging
import os
import platform
import string
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adb_executor import adb_executor
from .config import ADB_AVAILABLE, get_config, load_config, update_config
from .device_discovery import discovery_loop, handle_self_registration
from .device_manager import device_manager
from .device_ws_manager import REGISTER_TIMEOUT, device_ws_manager
from .models import (
    ConfigModel,
    DeviceNameUpdate,
    DeviceRegistration,
    OpenCommand,
    PlaybackCommand,
    RequirementVideo,
    UsbInitOptions,
    VolumeUpdate,
)
from .playback_controller import (
    get_global_volume,
    launch_player,
    open_video,
    ping_device,
    restart_app,
    send_command,
    set_device_volume,
    set_global_volume,
    toggle_debug,
)
from .requirements_manager import (
    check_requirements,
    run_update,
    run_usb_update,
)
from .websocket_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vrclassroom")

_discovery_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _discovery_task
    # Startup
    load_config()
    if ADB_AVAILABLE:
        has_adb = await adb_executor.check_adb()
        if not has_adb:
            logger.warning("ADB not found in PATH. ADB-dependent features will not work.")
    else:
        logger.info("ADB explicitly disabled; running in HTTP-only mode")
    await device_manager.start()
    _discovery_task = asyncio.create_task(discovery_loop())
    logger.info("VR Classroom server started (discovery + offline_check loops)")
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


@app.get("/api/video-profiles")
async def get_video_profiles():
    config = get_config()
    return config.get("requirementVideos", [])


@app.get("/api/video-profiles/{video_id}")
async def get_video_profile(video_id: str):
    config = get_config()
    for video in config.get("requirementVideos", []):
        if video.get("id") == video_id:
            return video
    return JSONResponse(status_code=404, content={"error": "Video profile not found"})


@app.put("/api/video-profiles/{video_id}")
async def update_video_profile(video_id: str, profile: RequirementVideo):
    config = get_config()
    videos = config.get("requirementVideos", [])

    updated = False
    profile_data = profile.model_dump()
    profile_data["id"] = video_id

    for index, video in enumerate(videos):
        if video.get("id") == video_id:
            videos[index] = profile_data
            updated = True
            break

    if not updated:
        return JSONResponse(status_code=404, content={"error": "Video profile not found"})

    config["requirementVideos"] = videos
    new_config = update_config(config)
    await ws_manager.broadcast({"type": "config_updated", "config": new_config})

    for video in new_config.get("requirementVideos", []):
        if video.get("id") == video_id:
            return video

    return JSONResponse(status_code=500, content={"error": "Failed to save video profile"})


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
async def set_device_name_endpoint(device_id: str, body: DeviceNameUpdate):
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
    return await ping_device(device_id)


@app.post("/api/devices/{device_id}/debug")
async def device_debug_toggle(device_id: str):
    return await toggle_debug(device_id)


if ADB_AVAILABLE:
    @app.post("/api/devices/{device_id}/restart-app")
    async def device_restart_app(device_id: str):
        """Restart the player app on a device via ADB (force-stop + launch)."""
        result = await restart_app(device_id)
        if result.get("error") == "Device not found":
            return JSONResponse(status_code=404, content=result)
        if result.get("error") == "ADB not connected":
            return JSONResponse(status_code=400, content=result)
        if result.get("error"):
            return JSONResponse(status_code=500, content=result)
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
    if not ADB_AVAILABLE:
        return JSONResponse(status_code=400, content={"error": "ADB disabled"})
    if not device.adb_connected:
        return JSONResponse(status_code=400, content={"error": "ADB not connected"})
    if device.update_in_progress:
        return JSONResponse(status_code=409, content={
            "error": "Update already in progress",
            "progress": device.update_progress,
        })
    asyncio.create_task(run_update(device_id))
    return {"ok": True, "message": "Update started"}


@app.post("/api/devices/update-all")
async def update_all_devices():
    if not ADB_AVAILABLE:
        return {"started": [], "skipped": [], "error": "ADB disabled"}

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

if ADB_AVAILABLE:
    @app.get("/api/usb-devices")
    async def get_usb_devices():
        serials = await adb_executor.list_usb_devices()
        return {"devices": serials}


    @app.post("/api/usb-devices/{serial}/update")
    async def update_usb_device(serial: str, options: Optional[UsbInitOptions] = None):
        serials = await adb_executor.list_usb_devices()
        if serial not in serials:
            return JSONResponse(status_code=404, content={"error": "USB device not found"})
        opts = options or UsbInitOptions()
        asyncio.create_task(run_usb_update(
            serial,
            enable_wireless_adb=opts.enableWirelessAdb,
            update_app=opts.updateApp,
            update_content=opts.updateContent,
        ))
        return {"ok": True, "message": f"USB update started for {serial}"}


# ─── File browse endpoint ────────────────────────────────────────────────────

@app.get("/api/browse")
async def browse_files(
    path: str = Query("", description="Directory path to browse"),
    filter: str = Query("", description="File extension filter, e.g. .apk,.mp4"),
):
    if not path:
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
    return await launch_player(cmd.deviceIds)


@app.post("/api/devices/{device_id}/launch-player")
async def launch_player_single(device_id: str):
    device = await device_manager.get(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    if not ADB_AVAILABLE:
        return JSONResponse(status_code=400, content={"error": "ADB disabled"})
    if not device.adb_connected:
        return JSONResponse(status_code=400, content={"error": "ADB not connected"})
    return await launch_player([device_id])


# ─── Playback endpoints ──────────────────────────────────────────────────────


@app.post("/api/playback/open")
async def playback_open(cmd: OpenCommand):
    return await open_video(cmd.videoId, cmd.deviceIds)


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


# ─── Volume endpoints ────────────────────────────────────────────────────────


@app.get("/api/playback/volume/global")
async def playback_get_global_volume():
    return {"globalVolume": get_global_volume()}


@app.post("/api/playback/volume/global")
async def playback_set_global_volume(body: VolumeUpdate):
    return await set_global_volume(body.volume)


@app.post("/api/devices/{device_id}/volume")
async def playback_set_device_volume(device_id: str, body: VolumeUpdate):
    result = await set_device_volume(device_id, body.volume)
    if result.get("error") == "Device not found":
        return JSONResponse(status_code=404, content=result)
    return result


# ─── Frontend WebSocket endpoint ─────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        devices = device_manager.get_snapshot()
        snapshot_config = get_config()
        snapshot_config["adbAvailable"] = ADB_AVAILABLE
        await ws_manager.send_to(ws, {
            "type": "snapshot",
            "devices": devices,
            "config": snapshot_config,
        })

        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(ws)


# ─── Device WebSocket endpoint ───────────────────────────────────────────────


@app.websocket("/ws/device")
async def device_websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for player devices. Protocol:
    1. Device connects and sends {"type":"register","deviceId":"...","ip":"...",...}
    2. Device sends periodic {"type":"status",...} heartbeats every 5s
    3. Server sends {"type":"command","action":"...",...} to control the device
    """
    await ws.accept()
    device_id = None

    try:
        # Wait for register message with timeout
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=REGISTER_TIMEOUT)
            msg = json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            logger.warning("Device WS: no valid register message within %ds, closing", REGISTER_TIMEOUT)
            await ws.close(code=1008, reason="Register timeout")
            return

        if msg.get("type") != "register":
            logger.warning("Device WS: first message is not register: %s", msg.get("type"))
            await ws.close(code=1008, reason="Expected register message")
            return

        device_id = str(msg.get("deviceId", "")).strip()
        ip = str(msg.get("ip", "")).strip()
        if not device_id:
            logger.warning("Device WS: register without deviceId")
            await ws.close(code=1008, reason="Missing deviceId")
            return

        # Register the WS connection
        await device_ws_manager.register(device_id, ws)

        # Update device in device manager
        await device_manager.add_or_update(
            device_id,
            ip=ip or "unknown",
            player_connected=True,
            battery=msg.get("battery", -1),
            player_version=msg.get("playerVersion", ""),
            playback_state=msg.get("state", "idle"),
            android_id=msg.get("androidId", msg.get("android_id", "")),
            device_model=msg.get("deviceModel", msg.get("model", "")),
            mac_address=msg.get("macAddress", msg.get("mac", "")),
            installed_packages=msg.get("packages", []),
        )

        device_name = msg.get("deviceName", "")
        if device_name:
            await device_manager.apply_device_name_from_device(device_id, device_name)

        logger.info("Device %s registered via WS from %s", device_id, ip)

        # Main receive loop for heartbeats and status updates
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "status":
                # Update device state from heartbeat
                update_kwargs = {}
                field_map = {
                    "state": "playback_state",
                    "file": "current_video",
                    "mode": "current_mode",
                    "time": "playback_time",
                    "duration": "playback_duration",
                    "battery": "battery",
                    "batteryCharging": "battery_charging",
                    "locked": "locked",
                    "loop": "loop",
                    "uptimeMinutes": "uptime_minutes",
                    "globalVolume": None,  # skip, server manages this
                    "personalVolume": "personal_volume",
                    "effectiveVolume": "effective_volume",
                    "playerVersion": "player_version",
                    "androidId": "android_id",
                    "android_id": "android_id",
                    "deviceModel": "device_model",
                    "model": "device_model",
                    "macAddress": "mac_address",
                    "mac": "mac_address",
                    "packages": "installed_packages",
                }
                for json_key, attr_name in field_map.items():
                    if attr_name and json_key in msg:
                        update_kwargs[attr_name] = msg[json_key]

                new_ip = msg.get("ip", "")
                await device_manager.add_or_update(
                    device_id,
                    ip=new_ip or ip,
                    player_connected=True,
                    **update_kwargs,
                )

            elif msg_type == "register":
                # Re-registration (e.g. after reconnect within same WS)
                ip = str(msg.get("ip", ip)).strip()
                await device_manager.add_or_update(
                    device_id,
                    ip=ip,
                    player_connected=True,
                    battery=msg.get("battery", -1),
                    player_version=msg.get("playerVersion", ""),
                )

    except WebSocketDisconnect:
        logger.info("Device %s WS disconnected normally", device_id or "unknown")
    except Exception as e:
        logger.warning("Device %s WS error: %s", device_id or "unknown", e)
    finally:
        if device_id:
            await device_ws_manager.disconnect(device_id)
            # Mark player as disconnected immediately
            device = await device_manager.get(device_id)
            if device:
                await device_manager.add_or_update(
                    device_id,
                    ip=device.ip,
                    player_connected=False,
                )


# ─── Server info endpoint ─────────────────────────────────────────────────────


@app.get("/api/server-info")
async def get_server_info():
    ip = _get_local_ip()
    config = get_config()
    port = config.get("serverPort", 8000)
    return {"ip": ip, "port": port, "url": f"http://{ip}:{port}"}


def _get_local_ip() -> str:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


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
