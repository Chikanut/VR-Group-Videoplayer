import asyncio
import logging
import os
from typing import Any

import aiohttp

from .config import get_config
from .device_manager import device_manager

logger = logging.getLogger("vrclassroom.playback")

REQUEST_TIMEOUT = 5


async def _send_to_player(ip: str, method: str, path: str, json_body: dict | None = None) -> dict[str, Any]:
    """Send an HTTP request to a player device."""
    config = get_config()
    player_port = config.get("playerPort", 8080)
    url = f"http://{ip}:{player_port}{path}"

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
            else:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    data = await resp.json()
                    return {"success": resp.status == 200, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _resolve_devices(device_ids: list[str]) -> list:
    """Resolve device IDs to DeviceState objects. Empty list means all online player devices."""
    if device_ids:
        devices = []
        for did in device_ids:
            d = await device_manager.get(did)
            if d and d.online and d.player_connected:
                devices.append(d)
        return devices
    else:
        return await device_manager.get_online_player_devices()


async def open_video(video_id: str, device_ids: list[str]) -> dict[str, Any]:
    """Open a video on target devices."""
    config = get_config()
    videos = config.get("requirementVideos", [])

    # Find the video by ID
    video = None
    for v in videos:
        if v.get("id") == video_id:
            video = v
            break

    if not video:
        return {"error": f"Video with ID {video_id} not found"}

    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"error": "No online devices with player connected"}

    local_path = (video.get("localPath", "") or "").strip()
    device_path = f"/sdcard/Movies/{os.path.basename(local_path)}" if local_path else video.get("devicePath", "")
    video_type = video.get("videoType", "360")
    loop = video.get("loop", False)

    # Map video type to player mode
    mode_map = {"2d": "2d", "360": "360", "360_mono": "360"}
    mode = mode_map.get(video_type, "360")

    payload = {
        "file": device_path,
        "mode": mode,
        "loop": loop,
    }

    # Check which devices have the video
    success_list = []
    failed_list = []
    missing_list = []

    tasks = []
    for d in devices:
        # Check if video is present (from cached requirements)
        video_present = True
        if d.requirements_detail:
            for req in d.requirements_detail:
                if req.get("type") == "video" and req.get("devicePath") == device_path:
                    if not req.get("present", False):
                        video_present = False
                    break

        if not video_present:
            missing_list.append({"deviceId": d.device_id, "name": d.name or d.device_id})
            continue

        tasks.append((d, _send_to_player(d.ip, "POST", "/open", payload)))

    results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

    for (d, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed_list.append({"deviceId": d.device_id, "error": str(result)})
        elif result.get("success"):
            success_list.append({"deviceId": d.device_id})
        else:
            failed_list.append({"deviceId": d.device_id, "error": result.get("error", "Unknown error")})

    return {
        "success": success_list,
        "failed": failed_list,
        "missing": missing_list,
    }


async def send_command(command: str, device_ids: list[str]) -> dict[str, Any]:
    """Send a playback command (play/pause/stop/recenter) to target devices."""
    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"success": [], "failed": [], "message": "No online devices with player connected"}

    path = f"/{command}"
    tasks = [(d, _send_to_player(d.ip, "POST", path)) for d in devices]
    results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

    success_list = []
    failed_list = []

    for (d, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failed_list.append({"deviceId": d.device_id, "error": str(result)})
        elif result.get("success"):
            success_list.append({"deviceId": d.device_id})
        else:
            failed_list.append({"deviceId": d.device_id, "error": result.get("error", "Unknown error")})

    return {"success": success_list, "failed": failed_list}


async def ping_device(device_id: str) -> dict[str, Any]:
    """Send a ping (beep) to a single device."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}
    if not device.player_connected:
        return {"error": "Player not connected"}

    result = await _send_to_player(device.ip, "POST", "/ping")
    return result
