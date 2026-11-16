"""Headset system settings profile, applied by the player itself (no cable).

Settings → "Headset system settings" holds lines like `global/captive_portal_mode=0`.
Every player gets the profile when its WebSocket registers and again when the profile
changes. The player (PlayerSystem.java applySettings) remembers each key's original value
and restores it when the line is removed, so an empty profile undoes everything. It needs
WRITE_SECURE_SETTINGS, granted once over USB by tools/quest_deploy.py setup_player();
the result comes back in the status field `settingsProfile`.
"""
import logging
from typing import List, Optional

from .config import get_config
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.headset_settings")


async def push_headset_settings(device_ids: Optional[List[str]] = None) -> int:
    """Send the profile to the given connected players (default: all). Returns how many got it."""
    command = {
        "type": "command",
        "action": "apply_settings",
        "settings": str(get_config().get("headsetSettings", "")),
    }
    sent = 0
    for device_id in device_ids or device_ws_manager.get_connected_ids():
        if await device_ws_manager.send_command(device_id, dict(command)):
            sent += 1
    logger.info("Headset settings profile sent to %d device(s)", sent)
    return sent
