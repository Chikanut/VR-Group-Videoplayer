import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.playback")

REQUEST_TIMEOUT = 5
global_volume = 1.0


async def _send_to_player(ip: str, method: str, path: str, json_body: Optional[Dict] = None) -> Dict[str, Any]:
    """Send an HTTP request to a player device."""
    url = f"http://{ip}:{PLAYER_HTTP_PORT}{path}"

    try:
        async with aiohttp.ClientSession() as session:
            if method == "POST":
                async with session.post(
                    url,
                    json=json_body,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    data = await resp.json()
                    return {"success": resp.status == 200, "data": data}

            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json()
                return {"success": resp.status == 200, "data": data}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _resolve_devices(device_ids: List[str]) -> List:
    """Resolve device IDs to online player-connected DeviceState objects."""
    if device_ids:
        devices = []
        for device_id in device_ids:
            device = await device_manager.get(device_id)
            if device and device.online and device.player_connected:
                devices.append(device)
        return devices

    return await device_manager.get_online_player_devices()


async def _send_command_to_device(device, command: str, path: str, payload: Optional[Dict] = None) -> Dict[str, Any]:
    """Send command prioritizing WebSocket, then HTTP API."""
    if device_ws_manager.is_connected(device.device_id):
        ws_command = {"type": "command", "action": command}
        if payload:
            ws_command.update(payload)
        sent = await device_ws_manager.send_command(device.device_id, ws_command)
        if sent:
            return {"success": True, "via": "ws"}

    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", path, payload)
        if result.get("success"):
            return result

    return {"success": False, "error": "Player is not reachable"}


async def open_video(video_id: str, device_ids: List[str]) -> Dict[str, Any]:
    """Open a video on target devices."""
    config = get_config()
    videos = config.get("requirementVideos", [])

    video = next((item for item in videos if item.get("id") == video_id), None)
    if not video:
        return {"error": f"Video with ID {video_id} not found"}

    filename = (video.get("filename") or "").strip()
    if not filename:
        return {"error": "Video filename is empty"}

    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"error": "No online devices available"}

    mode_map = {"2d": "2d", "360": "360", "360_mono": "360"}
    payload = {
        "file": filename,
        "mode": mode_map.get(video.get("videoType", "360"), "360"),
        "loop": bool(video.get("loop", False)),
        "placementMode": video.get("placementMode", "default"),
    }

    advanced_settings = video.get("advancedSettings")
    if advanced_settings is not None:
        payload["advancedSettings"] = advanced_settings

    success_list = []
    failed_list = []
    missing_list = []

    tasks = []
    for device in devices:
        video_present = True
        if device.requirements_detail:
            for requirement in device.requirements_detail:
                if requirement.get("type") == "video" and requirement.get("id") == video_id:
                    video_present = requirement.get("present", False)
                    break

        if not video_present:
            missing_list.append({"deviceId": device.device_id, "name": device.name or device.device_id})
            continue

        tasks.append((device, _send_command_to_device(device, "open", "/open", payload)))

    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

    for (device, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed_list.append({"deviceId": device.device_id, "error": str(result)})
        elif result.get("success"):
            success_list.append({"deviceId": device.device_id})
        else:
            failed_list.append({"deviceId": device.device_id, "error": result.get("error", "Unknown error")})

    return {
        "success": success_list,
        "failed": failed_list,
        "missing": missing_list,
    }


async def send_command(command: str, device_ids: List[str]) -> Dict[str, Any]:
    """Send a playback command (play/pause/stop/recenter) to target devices."""
    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"success": [], "failed": [], "message": "No online devices available"}

    path = f"/{command}"
    tasks = [(device, _send_command_to_device(device, command, path)) for device in devices]
    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

    success_list = []
    failed_list = []

    for (device, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed_list.append({"deviceId": device.device_id, "error": str(result)})
        elif result.get("success"):
            success_list.append({"deviceId": device.device_id})
        else:
            failed_list.append({"deviceId": device.device_id, "error": result.get("error", "Unknown error")})

    return {"success": success_list, "failed": failed_list}


async def ping_device(device_id: str) -> Dict[str, Any]:
    """Send a ping (beep) to a single device."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}

    if device_ws_manager.is_connected(device_id):
        sent = await device_ws_manager.send_command(device_id, {"type": "command", "action": "ping"})
        if sent:
            return {"success": True, "via": "ws"}

    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", "/ping")
        if result.get("success"):
            return result

    return {"error": "Player is not reachable"}


async def toggle_debug(device_id: str) -> Dict[str, Any]:
    """Toggle debug panel on a single device."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}

    if device_ws_manager.is_connected(device_id):
        sent = await device_ws_manager.send_command(device_id, {"type": "command", "action": "toggle_debug"})
        if sent:
            return {"success": True, "via": "ws"}

    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", "/debug")
        if result.get("success"):
            return result

    return {"error": "Player is not reachable"}


def get_global_volume() -> float:
    return global_volume


async def set_global_volume(volume: float) -> Dict[str, Any]:
    global global_volume

    clamped = max(0.0, min(1.0, float(volume)))
    global_volume = clamped

    async with device_manager._lock:
        all_devices = list(device_manager._devices.values())

    tasks = []
    for device in all_devices:
        personal = max(0.0, min(1.0, float(device.personal_volume)))
        effective = clamped * personal
        await device_manager.add_or_update(device.device_id, device.ip, effective_volume=effective)
        if not device.online or not device.player_connected:
            continue
        tasks.append((
            device,
            _send_command_to_device(
                device,
                "set_volume",
                "/volume",
                {"globalVolume": clamped, "personalVolume": personal},
            ),
        ))

    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True) if tasks else []
    success = []
    failed = []
    for (device, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed.append({"deviceId": device.device_id, "error": str(result)})
        elif result.get("success"):
            success.append({"deviceId": device.device_id})
        else:
            failed.append({"deviceId": device.device_id, "error": result.get("error", "Unknown error")})

    return {"globalVolume": clamped, "success": success, "failed": failed}


async def set_device_volume(device_id: str, volume: float) -> Dict[str, Any]:
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}

    personal = max(0.0, min(1.0, float(volume)))
    effective = get_global_volume() * personal
    await device_manager.add_or_update(
        device.device_id,
        device.ip,
        personal_volume=personal,
        effective_volume=effective,
    )

    if not device.online or not device.player_connected:
        return {
            "deviceId": device.device_id,
            "personalVolume": personal,
            "effectiveVolume": effective,
            "warning": "Volume saved, but device is offline or unreachable",
        }

    result = await _send_command_to_device(
        device,
        "set_volume",
        "/volume",
        {"globalVolume": get_global_volume(), "personalVolume": personal},
    )
    return {
        "deviceId": device.device_id,
        "personalVolume": personal,
        "effectiveVolume": effective,
        "sent": result.get("success", False),
        "error": result.get("error"),
    }
