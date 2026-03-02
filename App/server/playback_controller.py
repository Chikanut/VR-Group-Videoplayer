import asyncio
import logging
import os
from typing import Any

import aiohttp

from .adb_executor import adb_executor
from .config import get_config, get_device_video_path
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


async def _send_via_adb(ip: str, command: str, intent_extra: str = "") -> dict[str, Any]:
    """Send a command to device via ADB intent as fallback."""
    config = get_config()
    package_id = config.get("packageId", "com.vrclassroom.player")
    cmd = (
        f"am broadcast -a {package_id}.{command} "
        f"-n {package_id}/.CommandReceiver"
    )
    if intent_extra:
        cmd += f" {intent_extra}"
    success, output = await adb_executor.shell(ip, cmd)
    return {"success": success, "data": output, "via": "adb"}


async def _resolve_devices(device_ids: list[str], require_player: bool = True) -> list:
    """Resolve device IDs to DeviceState objects.
    Empty list means all online devices.
    If require_player is False and ignoreRequirements is set, include ADB-only devices.
    """
    config = get_config()
    ignore_req = config.get("ignoreRequirements", False)

    if device_ids:
        devices = []
        for did in device_ids:
            d = await device_manager.get(did)
            if not d or not d.online:
                continue
            if d.player_connected:
                devices.append(d)
            elif ignore_req and d.adb_connected:
                devices.append(d)
        return devices
    else:
        if ignore_req:
            async with device_manager._lock:
                return [d for d in device_manager._devices.values()
                        if d.online and (d.player_connected or d.adb_connected)]
        return await device_manager.get_online_player_devices()


async def _send_command_to_device(device, command: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    """Send command prioritizing HTTP API, falling back to ADB."""
    # Try HTTP API first if player is connected
    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", path, payload)
        if result.get("success"):
            return result
        logger.warning("HTTP command %s failed for %s, trying ADB fallback", command, device.ip)

    # Fallback to ADB
    if device.adb_connected:
        extra = ""
        if payload:
            for k, v in payload.items():
                if isinstance(v, bool):
                    extra += f" --ez {k} {str(v).lower()}"
                elif isinstance(v, str):
                    extra += f" --es {k} '{v}'"
                elif isinstance(v, (int, float)):
                    extra += f" --ei {k} {v}"
        return await _send_via_adb(device.ip, command, extra)

    return {"success": False, "error": "Neither player nor ADB connected"}


async def open_video(video_id: str, device_ids: list[str]) -> dict[str, Any]:
    """Open a video on target devices."""
    config = get_config()
    videos = config.get("requirementVideos", [])
    ignore_req = config.get("ignoreRequirements", False)

    video = None
    for v in videos:
        if v.get("id") == video_id:
            video = v
            break

    if not video:
        return {"error": f"Video with ID {video_id} not found"}

    devices = await _resolve_devices(device_ids)
    if not devices:
        return {"error": "No online devices available"}

    local_path = video.get("localPath", "")
    device_path = get_device_video_path(local_path) if local_path else ""
    video_type = video.get("videoType", "360")
    loop = video.get("loop", False)

    mode_map = {"2d": "2d", "360": "360", "360_mono": "360"}
    mode = mode_map.get(video_type, "360")

    payload = {
        "file": device_path,
        "mode": mode,
        "loop": loop,
    }

    success_list = []
    failed_list = []
    missing_list = []

    tasks = []
    for d in devices:
        video_present = True
        if not ignore_req and d.requirements_detail:
            for req in d.requirements_detail:
                if req.get("type") == "video" and req.get("id") == video_id:
                    if not req.get("present", False):
                        video_present = False
                    break

        if not video_present and not ignore_req:
            missing_list.append({"deviceId": d.device_id, "name": d.name or d.device_id})
            continue

        tasks.append((d, _send_command_to_device(d, "open", "/open", payload)))

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
        return {"success": [], "failed": [], "message": "No online devices available"}

    path = f"/{command}"
    tasks = [(d, _send_command_to_device(d, command, path)) for d in devices]
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


async def launch_player(device_ids: list[str]) -> dict[str, Any]:
    """Launch the player app on target devices via ADB."""
    config = get_config()
    package_id = config.get("packageId", "com.vrclassroom.player")
    player_port = config.get("playerPort", 8080)

    # Resolve to online ADB-connected devices
    if device_ids:
        devices = []
        for did in device_ids:
            d = await device_manager.get(did)
            if d and d.online and d.adb_connected:
                devices.append(d)
    else:
        devices = await device_manager.get_online_adb_devices()

    if not devices:
        return {"error": "No online ADB-connected devices available", "success": [], "failed": []}

    success_list = []
    failed_list = []

    async def _launch_on_device(device):
        # Launch via monkey command
        ok, output = await adb_executor.shell(
            device.ip,
            f"monkey -p {package_id} -c android.intent.category.LAUNCHER 1"
        )
        if not ok:
            return {"deviceId": device.device_id, "error": f"Launch failed: {output}"}

        # Wait for player to start and check HTTP
        await asyncio.sleep(5)
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{device.ip}:{player_port}/status"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        await device_manager.add_or_update(
                            device.device_id,
                            device.ip,
                            player_connected=True,
                            player_version=data.get("playerVersion", data.get("version", "")),
                            playback_state=data.get("state", "idle"),
                        )
                        return {"deviceId": device.device_id, "playerConnected": True}
        except Exception:
            pass

        # Player launched but HTTP not responding yet - still count as success
        return {"deviceId": device.device_id, "playerConnected": False, "note": "Launched but player HTTP not responding yet"}

    tasks = [_launch_on_device(d) for d in devices]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            failed_list.append({"error": str(result)})
        elif result.get("error"):
            failed_list.append(result)
        else:
            success_list.append(result)

    return {"success": success_list, "failed": failed_list}


async def ping_device(device_id: str) -> dict[str, Any]:
    """Send a ping (beep) to a single device."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}

    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", "/ping")
        if result.get("success"):
            return result

    if device.adb_connected:
        return await _send_via_adb(device.ip, "ping")

    return {"error": "Neither player nor ADB connected"}


async def toggle_debug(device_id: str) -> dict[str, Any]:
    """Toggle debug panel on a single device."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}

    if device.player_connected:
        result = await _send_to_player(device.ip, "POST", "/debug")
        if result.get("success"):
            return result

    if device.adb_connected:
        return await _send_via_adb(device.ip, "DEBUG")

    return {"error": "Neither player nor ADB connected"}
