import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager
from .format_compat import check_video_on_device
from .video_format import (
    DEFAULT_FORMAT,
    FORMAT_AUTO,
    format_id_from_filename,
    legacy_mode_for,
    normalize_format_id,
    projection_of,
    stereo_of,
)

logger = logging.getLogger("vrclassroom.playback")


def resolve_video_format(video: Dict[str, Any]) -> str:
    """Pick the effective formatId for a configured video.

    Manual value wins. ``auto`` uses the detection cached in the config when the video was
    added; failing that, the filename suffix; failing that, 360 mono (logged).
    """
    manual = normalize_format_id(video.get("videoType"))
    if manual and manual != FORMAT_AUTO:
        return manual

    detected = normalize_format_id(video.get("detectedType"))
    if detected and detected != FORMAT_AUTO:
        return detected

    from_name = format_id_from_filename(video.get("filename") or "")
    if from_name:
        return from_name

    logger.warning(
        "Video %s is set to auto but has no detection result and no filename suffix; using %s",
        video.get("name") or video.get("filename") or video.get("id"),
        DEFAULT_FORMAT,
    )
    return DEFAULT_FORMAT


def build_open_payload(video: Dict[str, Any]) -> Dict[str, Any]:
    """Build the /open body sent to players.

    ``mode`` carries the legacy "360" / "2d" value so pre-stereo players keep working;
    ``projection`` / ``stereo`` / ``swapEyes`` / ``forwardYaw`` are read by new players and
    take precedence over ``mode`` there. JsonUtility on old players ignores unknown keys.
    """
    format_id = resolve_video_format(video)
    payload = {
        "file": (video.get("filename") or "").strip(),
        "mode": legacy_mode_for(format_id),
        "format": format_id,
        "projection": projection_of(format_id),
        "stereo": stereo_of(format_id),
        "swapEyes": bool(video.get("swapEyes", False)),
        "forwardYaw": float(video.get("forwardYaw", 0.0) or 0.0),
        "loop": bool(video.get("loop", False)),
        "placementMode": video.get("placementMode", "default"),
    }

    advanced_settings = video.get("advancedSettings")
    if advanced_settings is not None:
        payload["advancedSettings"] = advanced_settings
    return payload

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

    payload = build_open_payload(video)
    logger.info(
        "Opening %s as %s (mode=%s projection=%s stereo=%s) on %d device(s)",
        filename, payload["format"], payload["mode"], payload["projection"], payload["stereo"], len(devices),
    )

    success_list = []
    failed_list = []
    missing_list = []
    warnings_list = []

    tasks = []
    for device in devices:
        device_warnings = check_video_on_device(video, device, payload["format"])
        if device_warnings:
            warnings_list.append({
                "deviceId": device.device_id,
                "name": device.name or device.device_id,
                "warnings": device_warnings,
            })

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
        "format": payload["format"],
        "warnings": warnings_list,
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


async def seek_video(time: float, device_ids: List[str]) -> Dict[str, Any]:
    """Seek target devices to a position in seconds. Empty device_ids seeks all players."""
    target = max(0.0, float(time))
    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"success": [], "failed": [], "message": "No online devices available"}

    payload = {"time": target}
    tasks = [(device, _send_command_to_device(device, "seek", "/seek", payload)) for device in devices]
    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

    success_list = []
    failed_list = []

    for (device, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed_list.append({"deviceId": device.device_id, "error": str(result)})
        elif result.get("success"):
            success_list.append({"deviceId": device.device_id})
            # Reflect the new position in the dashboard immediately instead of waiting
            # for the next heartbeat (up to 5s, or far longer if the heartbeat is stalled).
            await device_manager.add_or_update(
                device.device_id,
                getattr(device, "ip", ""),
                seen=False,
                playback_time=target,
            )
        else:
            failed_list.append({"deviceId": device.device_id, "error": result.get("error", "Unknown error")})

    return {"time": target, "success": success_list, "failed": failed_list}


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
        await device_manager.add_or_update(device.device_id, device.ip, seen=False, effective_volume=effective)
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
        seen=False,
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
