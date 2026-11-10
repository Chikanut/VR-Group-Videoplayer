"""Silent player self-update: the server serves the player APK, headsets download it.

The instructor sets `playerApkPath` in Settings. "Update players" sends every connected
headset {"action": "update", "url": APK_URL_PATH, "sha256": ...}; a headset whose
installed APK already has that sha256 skips the update.
"""
import asyncio
import hashlib
import logging
import os
from typing import Any, Dict, Optional

from .config import get_config
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.player_update")

APK_URL_PATH = "/api/player/apk"

_sha_cache: Dict[tuple, str] = {}


def get_player_apk_path() -> Optional[str]:
    path = str(get_config().get("playerApkPath", "")).strip().strip('"')
    return path if path and os.path.isfile(path) else None


def sha256_file(path: str) -> str:
    stat = os.stat(path)
    key = (path, stat.st_size, stat.st_mtime)
    if key not in _sha_cache:
        digest = hashlib.sha256()
        with open(path, "rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1 << 20), b""):
                digest.update(chunk)
        _sha_cache.clear()
        _sha_cache[key] = digest.hexdigest()
    return _sha_cache[key]


async def update_players() -> Dict[str, Any]:
    path = get_player_apk_path()
    if not path:
        return {"success": False, "error": "Player APK not found: set its path in Settings"}

    sha256 = await asyncio.to_thread(sha256_file, path)
    command = {"type": "command", "action": "update", "url": APK_URL_PATH, "sha256": sha256}

    sent = []
    for device_id in device_ws_manager.get_connected_ids():
        if await device_ws_manager.send_command(device_id, dict(command)):
            sent.append(device_id)

    logger.info("Player update %s sent to %d device(s)", sha256[:12], len(sent))
    return {"success": True, "sent": len(sent), "deviceIds": sent, "sha256": sha256}
