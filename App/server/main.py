import asyncio
import json
import logging
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    export_device_names,
    get_config,
    load_config,
    replace_device_names,
    update_config,
)
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
    VolumeUpdate,
)
from .playback_controller import (
    get_global_volume,
    open_video,
    ping_device,
    send_command,
    set_device_volume,
    set_global_volume,
    toggle_debug,
)
from .requirements_manager import check_requirements, refresh_all_requirements
from .websocket_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vrclassroom")

_discovery_task: Optional[asyncio.Task] = None


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _discovery_task

    config = load_config()
    logger.info(
        "Startup runtime diagnostics: isAndroidRuntime=%s networkSubnet=%s",
        config.get("isAndroidRuntime"),
        config.get("networkSubnet", ""),
    )
    await device_manager.start()
    _discovery_task = asyncio.create_task(discovery_loop())
    logger.info("VR Classroom server started (discovery + offline_check loops)")
    yield

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


@app.get("/api/health")
async def health_check():
    return {"ok": True}


@app.get("/api/config")
async def get_config_endpoint():
    return get_config()


@app.put("/api/config")
async def update_config_endpoint(config: ConfigModel):
    new_config = update_config(_model_to_dict(config))
    await refresh_all_requirements()
    await ws_manager.broadcast({"type": "config_updated", "config": new_config})
    return new_config


@app.get("/api/device-names")
async def get_device_names_endpoint():
    return export_device_names()


@app.put("/api/device-names")
async def replace_device_names_endpoint(body: Dict[str, str]):
    names = replace_device_names(body)
    await device_manager.sync_device_names()
    return names


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
    profile_data = _model_to_dict(profile)
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
    await refresh_all_requirements()
    await ws_manager.broadcast({"type": "config_updated", "config": new_config})

    for video in new_config.get("requirementVideos", []):
        if video.get("id") == video_id:
            return video

    return JSONResponse(status_code=500, content={"error": "Failed to save video profile"})


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
    await handle_self_registration(_model_to_dict(reg))
    return {"ok": True}


@app.post("/api/devices/{device_id}/ping")
async def device_ping(device_id: str):
    result = await ping_device(device_id)
    if result.get("error") == "Device not found":
        return JSONResponse(status_code=404, content=result)
    return result


@app.post("/api/devices/{device_id}/debug")
async def device_debug_toggle(device_id: str):
    result = await toggle_debug(device_id)
    if result.get("error") == "Device not found":
        return JSONResponse(status_code=404, content=result)
    return result


@app.get("/api/devices/{device_id}/requirements")
async def get_requirements(device_id: str):
    device = await device_manager.get(device_id)
    if not device:
        return JSONResponse(status_code=404, content={"error": "Device not found"})
    results = await check_requirements(device_id)
    return {"deviceId": device_id, "requirements": results}


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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        devices = device_manager.get_snapshot()
        await ws_manager.send_to(ws, {
            "type": "snapshot",
            "devices": devices,
            "config": get_config(),
        })

        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(ws)


@app.websocket("/ws/device")
async def device_websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for player devices."""
    await ws.accept()
    device_id = None
    ip = ""

    try:
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

        await device_ws_manager.register(device_id, ws)

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
        )

        device_name = str(msg.get("deviceName", "")).strip()
        if device_name:
            await device_manager.apply_device_name_from_device(device_id, device_name)

        logger.info("Device %s registered via WS from %s", device_id, ip)
        await check_requirements(device_id)

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "status":
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
                    "personalVolume": "personal_volume",
                    "effectiveVolume": "effective_volume",
                    "playerVersion": "player_version",
                    "androidId": "android_id",
                    "android_id": "android_id",
                    "deviceModel": "device_model",
                    "model": "device_model",
                    "macAddress": "mac_address",
                    "mac": "mac_address",
                }
                for json_key, attr_name in field_map.items():
                    if attr_name and json_key in msg:
                        update_kwargs[attr_name] = msg[json_key]

                new_ip = str(msg.get("ip", "")).strip()
                await device_manager.add_or_update(
                    device_id,
                    ip=new_ip or ip or "unknown",
                    player_connected=True,
                    **update_kwargs,
                )

            elif msg_type == "register":
                ip = str(msg.get("ip", ip)).strip()
                await device_manager.add_or_update(
                    device_id,
                    ip=ip or "unknown",
                    player_connected=True,
                    battery=msg.get("battery", -1),
                    player_version=msg.get("playerVersion", ""),
                )

    except WebSocketDisconnect:
        logger.info("Device %s WS disconnected normally", device_id or "unknown")
    except Exception as exc:
        logger.warning("Device %s WS error: %s", device_id or "unknown", exc)
    finally:
        if device_id:
            await device_ws_manager.disconnect(device_id)
            device = await device_manager.get(device_id)
            if device:
                await device_manager.add_or_update(
                    device_id,
                    ip=device.ip,
                    player_connected=False,
                )


@app.get("/api/server-info")
async def get_server_info():
    ip = _get_local_ip()
    config = get_config()
    port = config.get("serverPort", 8000)
    return {"ip": ip, "port": port, "url": f"http://{ip}:{port}"}


def _get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.1)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
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


def _resolve_frontend_dist() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path.cwd())) / "frontend" / "dist"

    candidate_paths = [
        Path(__file__).parent.parent / "frontend" / "dist",
        Path(__file__).parent.parent / "android_web_dist",
    ]
    for path in candidate_paths:
        if path.exists():
            return path

    return candidate_paths[0]


FRONTEND_DIST = _resolve_frontend_dist()

if FRONTEND_DIST.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/settings")
    async def serve_settings():
        return FileResponse(FRONTEND_DIST / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST)), name="static")
