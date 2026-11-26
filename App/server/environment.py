"""Waiting-room environment of the player: default (logo model + maroon sky) or custom.

Custom = a solid background colour plus an optional PNG picture placed instead of the
logo model (position / size / rotation in metres and degrees, from the viewer's start
point: X right, Y up, Z forward). Settings holds it in config `environment`; the PNG is
stored next to config.json. Agents (player 1.9.0+) get WS `set_environment` on every
registration and on every change, download the PNG and hand both to the player.
"""
import hashlib
import logging
import struct
from typing import Any, Dict, List, Optional

from . import config as cfg
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.environment")

LOGO_URL = "/api/environment/logo"
MAX_LOGO_BYTES = 16 * 1024 * 1024
MAX_LOGO_SIDE = 4096  # Quest texture memory: 4096² RGBA with mips is ~85 MB

DEFAULT_ENVIRONMENT: Dict[str, Any] = {
    "custom": False,
    "background": "#1a1a1a",
    "logoSha256": "",
    "logoPosition": [0.0, 0.0, 10.5],  # where the logo model stands
    "logoSize": 4.0,                    # picture width in metres
    "logoRotation": [0.0, 0.0, 0.0],
}


def logo_path():
    return cfg.CONFIG_PATH.parent / "environment-logo.png"


def _vector(value: Any, default: List[float]) -> List[float]:
    try:
        vector = [float(v) for v in value]
        return vector if len(vector) == 3 else list(default)
    except (TypeError, ValueError):
        return list(default)


def _colour(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text[0] == "#":
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            pass
    return default


def normalize_environment(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    env = dict(DEFAULT_ENVIRONMENT)
    env["custom"] = bool(raw.get("custom", False))
    env["background"] = _colour(raw.get("background"), DEFAULT_ENVIRONMENT["background"])
    env["logoSha256"] = str(raw.get("logoSha256") or "")
    env["logoPosition"] = _vector(raw.get("logoPosition"), DEFAULT_ENVIRONMENT["logoPosition"])
    env["logoRotation"] = _vector(raw.get("logoRotation"), DEFAULT_ENVIRONMENT["logoRotation"])
    try:
        env["logoSize"] = min(max(float(raw.get("logoSize", 4.0)), 0.05), 100.0)
    except (TypeError, ValueError):
        env["logoSize"] = DEFAULT_ENVIRONMENT["logoSize"]
    return env


def validate_png(data: bytes) -> Optional[str]:
    """Error text, or None when `data` is a PNG the headset can load."""
    if len(data) > MAX_LOGO_BYTES:
        return f"File is larger than {MAX_LOGO_BYTES // (1024 * 1024)} MB"
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return "Not a PNG file"
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height or max(width, height) > MAX_LOGO_SIDE:
        return f"Picture must be at most {MAX_LOGO_SIDE}x{MAX_LOGO_SIDE} pixels (got {width}x{height})"
    return None


def save_logo(data: bytes) -> str:
    path = logo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def delete_logo() -> None:
    logo_path().unlink(missing_ok=True)


def environment_command() -> Dict[str, Any]:
    env = normalize_environment(cfg.get_config().get("environment"))
    if env["logoSha256"] and not logo_path().is_file():
        env["logoSha256"] = ""
    return {
        "type": "command",
        "action": "set_environment",
        "environment": env,
        "logoUrl": LOGO_URL if env["logoSha256"] else "",
    }


async def push_environment(device_ids: Optional[List[str]] = None) -> int:
    """Send the environment to the given connected devices (default: all)."""
    command = environment_command()
    sent = 0
    for device_id in device_ids or device_ws_manager.get_connected_ids():
        if await device_ws_manager.send_command(device_id, dict(command)):
            sent += 1
    logger.info("Environment (%s) sent to %d device(s)", "custom" if command["environment"]["custom"] else "default", sent)
    return sent
