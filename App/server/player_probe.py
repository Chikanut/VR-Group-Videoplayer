"""Shared helpers for talking to the player's HTTP status endpoint.

Used by network discovery (subnet scan), by the WebSocket status handler and by the
liveness loop in DeviceManager, so that every code path maps the player's status JSON
to DeviceState fields in exactly the same way.
"""
import logging
from typing import Any, Dict, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT
from .video_format import (
    PROJECTIONS,
    STEREO_LAYOUTS,
    STEREO_MONO,
    projection_of,
    format_id_from_legacy_mode,
)

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
    "androidId": "android_id",
    "android_id": "android_id",
    "deviceModel": "device_model",
    "model": "device_model",
    "macAddress": "mac_address",
    "mac": "mac_address",
    "personalVolume": "personal_volume",
    "effectiveVolume": "effective_volume",
    # Stereo 3D / 180 fields (players >= 1.7). Old players simply do not send them.
    "projection": "current_projection",
    "stereo": "current_stereo",
    "swapEyes": "swap_eyes",
    "videoWidth": "video_width",
    "videoHeight": "video_height",
    "backend": "backend",
    "decoderCaps": "decoder_caps",
}


def status_to_kwargs(status: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a player status payload into DeviceState attribute kwargs.

    Backward compatibility: a pre-stereo player only reports ``mode`` ("360" / "2d").
    In that case ``current_projection`` / ``current_stereo`` are derived from ``mode`` so
    the dashboard always has a projection to show, and ``stereo_capable`` is set to
    False so the panel can warn that 3D content will play flat on that headset.
    """
    kwargs: Dict[str, Any] = {}
    for json_key, attr_name in STATUS_FIELD_MAP.items():
        if json_key in status:
            kwargs[attr_name] = status[json_key]

    has_projection = "projection" in status
    if has_projection:
        projection = str(status.get("projection") or "").strip().lower()
        if projection not in PROJECTIONS:
            projection = projection_of(format_id_from_legacy_mode(status.get("mode")))
        kwargs["current_projection"] = projection
        stereo = str(status.get("stereo") or "").strip().lower()
        kwargs["current_stereo"] = stereo if stereo in STEREO_LAYOUTS else STEREO_MONO
        kwargs["stereo_capable"] = True
    elif "mode" in status:
        kwargs["current_projection"] = projection_of(format_id_from_legacy_mode(status.get("mode")))
        kwargs["current_stereo"] = STEREO_MONO
        kwargs["stereo_capable"] = False

    if "swapEyes" in status:
        kwargs["swap_eyes"] = bool(status.get("swapEyes"))
    if "decoderCaps" in status and not isinstance(status.get("decoderCaps"), dict):
        kwargs.pop("decoder_caps", None)
    for key in ("video_width", "video_height"):
        if key in kwargs:
            try:
                kwargs[key] = int(kwargs[key] or 0)
            except (TypeError, ValueError):
                kwargs[key] = 0
    return kwargs


def extract_device_id(status: Dict[str, Any], fallback: str) -> str:
    """Pick the device identifier out of a status payload, falling back to `fallback`."""
    for key in ("deviceId", "androidId", "android_id"):
        value = str(status.get(key, "") or "").strip()
        if value:
            return value
    return fallback


async def probe_player_status(ip: str, timeout: float = PROBE_TIMEOUT_SEC) -> Optional[Dict[str, Any]]:
    """GET http://<ip>:8080/status. Returns the parsed dict, or None if unreachable/invalid."""
    if not ip or ip == "unknown":
        return None

    url = f"http://{ip}:{PLAYER_HTTP_PORT}/status"
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
