"""Shared helpers for talking to the player's HTTP status endpoint.

Used by network discovery (subnet scan), by the WebSocket status handler and by the
liveness loop in DeviceManager, so that every code path maps the player's status JSON
to DeviceState fields in exactly the same way.
"""
import logging
from typing import Any, Dict, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT

logger = logging.getLogger("vrclassroom.probe")

# Direct probe of a known device. Quest Wi-Fi in power-save mode can add >1s of latency,
# so this is deliberately more generous than the subnet-scan connect timeout.
PROBE_TIMEOUT_SEC = 3.0

# Player status JSON key -> DeviceState attribute name.
STATUS_FIELD_MAP = {
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
    "playerVersion": "player_version",
    "settingsProfile": "settings_profile",
    "androidId": "android_id",
    "android_id": "android_id",
    "deviceModel": "device_model",
    "model": "device_model",
    "macAddress": "mac_address",
    "mac": "mac_address",
    "personalVolume": "personal_volume",
    "effectiveVolume": "effective_volume",
    # Headset agent (player 1.9.0+): sent whether or not the player runs.
    "playerRunning": "player_connected",
    "agentVersion": "agent_version",
    "autostart": "autostart",
    "storageFreeMb": "storage_free_mb",
    "content": "content",
    "update": "update_status",
}


def status_to_kwargs(status: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a player status payload into DeviceState attribute kwargs."""
    kwargs: Dict[str, Any] = {}
    for json_key, attr_name in STATUS_FIELD_MAP.items():
        if json_key in status:
            kwargs[attr_name] = status[json_key]
    return kwargs


def extract_device_id(status: Dict[str, Any], fallback: str) -> str:
    """Pick the device identifier out of a status payload, falling back to `fallback`."""
    for key in ("deviceId", "androidId", "android_id"):
        value = str(status.get(key, "") or "").strip()
        if value:
            return value
    return fallback


AGENT_HTTP_PORT = 8081  # headset agent / watchdog (WatchdogService.java), up while the player is closed


async def probe_player_status(ip: str, timeout: float = PROBE_TIMEOUT_SEC, port: int = PLAYER_HTTP_PORT) -> Optional[Dict[str, Any]]:
    """GET http://<ip>:<port>/status. Returns the parsed dict, or None if unreachable/invalid."""
    if not ip or ip == "unknown":
        return None

    url = f"http://{ip}:{port}/status"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("Status probe failed for %s: %s", ip, exc)
        return None
