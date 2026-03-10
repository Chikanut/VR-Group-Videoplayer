import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("vrclassroom.device_ws")

REGISTER_TIMEOUT = 10  # seconds to wait for register message after WS connect


class DeviceWSManager:
    """Manages WebSocket connections from player devices (separate from frontend WS)."""

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}  # device_id -> WebSocket
        self._lock = asyncio.Lock()

    async def register(self, device_id: str, ws: WebSocket):
        """Register a device WS connection. Closes old connection if exists."""
        async with self._lock:
            old_ws = self._connections.get(device_id)
            if old_ws is not None and old_ws != ws:
                logger.info("Closing old WS connection for device %s (reconnect)", device_id)
                try:
                    await old_ws.close(code=1000, reason="replaced by new connection")
                except Exception:
                    pass
            self._connections[device_id] = ws
        logger.info("Device %s registered via WebSocket (%d total)", device_id, len(self._connections))

    async def disconnect(self, device_id: str):
        """Remove a device WS connection."""
        async with self._lock:
            self._connections.pop(device_id, None)
        logger.info("Device %s WebSocket disconnected (%d remaining)", device_id, len(self._connections))

    async def send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send a command to a specific device via WS. Returns True if sent."""
        async with self._lock:
            ws = self._connections.get(device_id)
        if ws is None:
            return False
        try:
            await ws.send_text(json.dumps(command))
            return True
        except Exception as e:
            logger.warning("Failed to send command to %s via WS: %s", device_id, e)
            return False

    async def broadcast_command(self, command: dict[str, Any]):
        """Send a command to all connected devices."""
        async with self._lock:
            connections = dict(self._connections)
        dead = []
        for device_id, ws in connections.items():
            try:
                await ws.send_text(json.dumps(command))
            except Exception:
                dead.append(device_id)
        if dead:
            async with self._lock:
                for device_id in dead:
                    self._connections.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._connections

    def get_connected_ids(self) -> list[str]:
        return list(self._connections.keys())


device_ws_manager = DeviceWSManager()
