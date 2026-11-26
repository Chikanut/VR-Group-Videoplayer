import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager
from .pending_stops import pending_stops

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


async def _resolve_devices(device_ids: List[str], agent_ok: bool = False) -> List:
    """Resolve device IDs (empty = all) to online DeviceState objects whose player is
    connected - or, with agent_ok, whose headset agent is (commands the agent handles)."""
    devices = []
    for device_id in device_ids or await device_manager.get_all_ids():
        device = await device_manager.get(device_id)
        if device and device.online and (device.player_connected or (agent_ok and device.agent_connected)):
            devices.append(device)
    return devices


async def agent_command(action: str, device_ids: List[str], payload: Optional[Dict] = None) -> Dict[str, Any]:
    """Send a command handled by the headset agent itself (launch/close/restart_player, ...)."""
    success_list, failed_list = [], []
    for device in await _resolve_devices(device_ids, agent_ok=True):
        if not device.agent_connected:
            failed_list.append({"deviceId": device.device_id, "error": "No agent (player older than 1.9.0)"})
            continue
        command = {"type": "command", "action": action, **(payload or {})}
        if await device_ws_manager.send_command(device.device_id, command):
            success_list.append({"deviceId": device.device_id})
        else:
            failed_list.append({"deviceId": device.device_id, "error": "Agent is not reachable"})
    return {"success": success_list, "failed": failed_list}


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
            # A new video supersedes a stop the device may have missed.
            pending_stops.clear(device.device_id)
        else:
            failed_list.append({"deviceId": device.device_id, "error": result.get("error", "Unknown error")})

    return {
        "success": success_list,
        "failed": failed_list,
        "missing": missing_list,
    }


async def send_command(command: str, device_ids: List[str]) -> Dict[str, Any]:
    """Send a playback command (play/pause/stop/recenter) to target devices."""
    if command == "stop":
        # Marked before resolving: headsets that are asleep right now are not "online",
        # but must still be stopped when they wake up (see pending_stops).
        pending_stops.mark(device_ids or await device_manager.get_all_ids())

    # The agent puts a headset to sleep even while its player is closed.
    devices = await _resolve_devices(device_ids, agent_ok=command == "sleep")
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

WAKE_PORT = 8081  # player watchdog (WatchdogService.java), alive while the headset sleeps


async def _post_watchdog(ip: str, path: str) -> Dict[str, Any]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{ip}:{WAKE_PORT}{path}",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                # Players older than 1.8.2 answer 404 to /autostart/*.
                return {"success": True} if resp.status == 200 else {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"success": False, "error": str(exc) or type(exc).__name__}


async def _watchdog_command(path: str, device_ids: List[str], agent_command: Optional[Dict] = None) -> Dict[str, Any]:
    """Reach the watchdog of every known device (or the given ones), online or not: it answers
    while the headset sleeps or the player is closed. Through the agent's WebSocket when it is
    connected (player 1.9.0+), else HTTP POST to port 8081."""
    devices = [d for d in await device_manager.get_all() if d.get("ip") and d["ip"] != "unknown"]
    if device_ids:
        devices = [d for d in devices if d["deviceId"] in device_ids]

    async def reach(device: Dict[str, Any]) -> Dict[str, Any]:
        if agent_command and device.get("agentConnected") and device_ws_manager.is_connected(device["deviceId"]):
            if await device_ws_manager.send_command(device["deviceId"], {"type": "command", **agent_command}):
                return {"success": True}
        return await _post_watchdog(device["ip"], path)

    results = await asyncio.gather(*[reach(d) for d in devices])
    success_list, failed_list = [], []
    for device, result in zip(devices, results):
        if result["success"]:
            success_list.append({"deviceId": device["deviceId"]})
        else:
            failed_list.append({"deviceId": device["deviceId"], "error": result.get("error", "Unknown error")})
    return {"success": success_list, "failed": failed_list}


async def wake_devices(device_ids: List[str]) -> Dict[str, Any]:
    """Wake sleeping headsets. Asleep headsets show as offline, so every known device is targeted."""
    return await _watchdog_command("/wake", device_ids, {"action": "wake"})


async def get_autostart(device_id: str) -> Dict[str, Any]:
    """Ask the headset's watchdog whether it relaunches the player. autostart is None when unknown
    (headset off, or a player older than 1.8.2)."""
    device = await device_manager.get(device_id)
    if not device:
        return {"error": "Device not found"}
    if device.agent_connected and device.autostart is not None:
        return {"autostart": device.autostart}  # the agent reports it in every status
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://{device.ip}:{WAKE_PORT}/autostart",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json(content_type=None) if resp.status == 200 else {}
                return {"autostart": data.get("autostart")}
    except Exception as exc:
        return {"autostart": None, "error": str(exc) or type(exc).__name__}


async def set_autostart(enabled: bool, device_ids: List[str]) -> Dict[str, Any]:
    """Switch the watchdog's relaunching of the player on/off (persists on the headset)."""
    return await _watchdog_command(
        "/autostart/on" if enabled else "/autostart/off", device_ids, {"action": "autostart", "enabled": enabled}
    )


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
