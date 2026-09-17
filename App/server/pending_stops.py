import logging
import time
from typing import Dict, Iterable, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.pending_stops")

# Minimum interval between repeated stop deliveries to the same device.
STOP_RESEND_SEC = 5

# Player states that mean "a video is still open" and therefore contradict a stop.
ACTIVE_STATES = {"loading", "ready", "playing", "paused"}


class PendingStops:
    """Makes sure a stop reaches headsets that were asleep when it was sent.

    A sleeping Quest has no Wi-Fi and a paused app, so "stop all" never reaches it. When
    it wakes up it still has the old video (paused at its position) and the class is out
    of sync. Every stop therefore marks its targets as *pending*; the mark is cleared when
    the device reports a non-active state (the stop took effect) or when a new video is
    opened on it. While the mark is set, any status that still shows an open video makes
    the server send the stop again (throttled).
    """

    def __init__(self):
        self._pending: Dict[str, float] = {}    # device_id -> time the stop was requested
        self._last_push: Dict[str, float] = {}  # device_id -> time of the last delivery attempt

    def mark(self, device_ids: Iterable[str], now: Optional[float] = None):
        now = time.time() if now is None else now
        for device_id in device_ids:
            if not device_id:
                continue
            self._pending[device_id] = now
            # The stop itself is being sent right now; do not immediately re-send it
            # because of a heartbeat that was already on its way.
            self._last_push[device_id] = now

    def clear(self, device_id: str):
        self._pending.pop(device_id, None)
        self._last_push.pop(device_id, None)

    def is_pending(self, device_id: str) -> bool:
        return device_id in self._pending

    async def reconcile(self, device_id: str, ip: str, state: Optional[str], now: Optional[float] = None) -> bool:
        """Apply a playback state reported by a device. Returns True if a stop was re-sent."""
        if device_id not in self._pending or state is None:
            return False

        if str(state).strip().lower() not in ACTIVE_STATES:
            self.clear(device_id)
            logger.info("Device %s confirmed stop (state=%s)", device_id, state)
            return False

        now = time.time() if now is None else now
        if now - self._last_push.get(device_id, 0.0) < STOP_RESEND_SEC:
            return False
        self._last_push[device_id] = now

        logger.info("Device %s reports state=%s after a stop it missed (asleep?); re-sending stop", device_id, state)
        return await self._deliver_stop(device_id, ip)

    async def _deliver_stop(self, device_id: str, ip: str) -> bool:
        if device_ws_manager.is_connected(device_id):
            sent = await device_ws_manager.send_command(device_id, {"type": "command", "action": "stop"})
            if sent:
                return True

        if not ip or ip == "unknown":
            return False

        url = f"http://{ip}:{PLAYER_HTTP_PORT}/stop"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=None, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception as exc:
            logger.warning("Failed to re-send stop to device %s: %s", device_id, exc)
            return False


pending_stops = PendingStops()
