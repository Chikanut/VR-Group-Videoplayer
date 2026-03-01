import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("vrclassroom.ws")


class WebSocketManager:
    def __init__(self):
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self._clients))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(self._clients))

    async def broadcast(self, message: dict[str, Any]):
        data = json.dumps(message)
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._clients:
                        self._clients.remove(ws)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass

    @property
    def client_count(self) -> int:
        return len(self._clients)


ws_manager = WebSocketManager()
