import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import json

from fastapi import WebSocketDisconnect
from fastapi.responses import FileResponse

from App.server import content_sync, main, requirements_manager
from App.server.device_manager import device_manager


def _config(library: str):
    return {
        "videoLibraryPath": library,
        "headsetSettings": "global/captive_portal_mode=0",
        "requirementVideos": [
            {"id": "v1", "name": "One", "filename": "one.mp4"},
            {"id": "v2", "name": "Two", "filename": "two.mp4"},
        ],
    }


class FakeWebSocket:
    """Feeds the given messages to the device session, collects what the server sends."""

    def __init__(self, messages):
        self.incoming = [json.dumps(m) for m in messages]
        self.sent = []

    async def accept(self):
        pass

    async def receive_text(self):
        if not self.incoming:
            raise WebSocketDisconnect()
        return self.incoming.pop(0)

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def close(self, code=1000, reason=""):
        pass


class AgentLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "one.mp4"), "wb") as f:
            f.write(b"0123456789")
        config = _config(self.tmp.name)
        self.patches = [
            patch.object(content_sync, "get_config", return_value=config),
            patch.object(requirements_manager, "get_config", return_value=config),
            patch("App.server.headset_settings.get_config", return_value=config),
            patch("App.server.websocket_manager.ws_manager.broadcast", new=AsyncMock()),
        ]
        for p in self.patches:
            p.start()
        asyncio.run(device_manager.remove("quest-a"))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        asyncio.run(device_manager.remove("quest-a"))
        self.tmp.cleanup()

    def test_agent_session_tracks_player_and_files(self):
        ws = FakeWebSocket([
            {"type": "register", "agent": True, "deviceId": "quest-a", "ip": "10.0.0.5", "deviceName": "7",
             "playerRunning": False, "state": "closed", "autostart": True,
             "files": [{"name": "one.mp4", "size": 4}]},  # partial/old copy: wrong size
            {"type": "status", "deviceId": "quest-a", "ip": "10.0.0.5", "playerRunning": True, "state": "idle",
             "storageFreeMb": 9000, "files": [{"name": "one.mp4", "size": 10}]},
        ])
        seen = {}

        async def run():
            original = device_manager.add_or_update

            async def spy(device_id, ip, **kwargs):
                device = await original(device_id, ip, **kwargs)
                if kwargs.get("agent_connected") and "player_connected" in kwargs:
                    seen.setdefault("player", []).append(kwargs["player_connected"])
                return device
            with patch.object(device_manager, "add_or_update", new=spy),                  patch.object(main.device_manager, "schedule_ws_disconnect_check"):
                await main._device_session(ws, agent=True)
            return await device_manager.get("quest-a")

        device = asyncio.run(run())
        self.assertEqual(ws.sent[0]["action"], "apply_settings")
        self.assertEqual(seen["player"], [False, True])
        self.assertTrue(device.agent_connected)
        self.assertTrue(device.player_connected)
        self.assertEqual(device.autostart, True)
        self.assertEqual(device.storage_free_mb, 9000)
        detail = {r["filename"]: r for r in device.requirements_detail}
        self.assertTrue(detail["one.mp4"]["present"])
        self.assertFalse(detail["two.mp4"]["present"])
        self.assertFalse(device.requirements_met)

    def test_outdated_copy_is_not_present(self):
        async def run():
            await device_manager.add_or_update("quest-a", "10.0.0.5", agent_connected=True)
            await requirements_manager.apply_agent_files("quest-a", [{"name": "one.mp4", "size": 4}])
            return await device_manager.get("quest-a")
        device = asyncio.run(run())
        one = next(r for r in device.requirements_detail if r["filename"] == "one.mp4")
        self.assertFalse(one["present"])
        self.assertTrue(one["outdated"])

    def test_library_never_leaves_its_folder(self):
        for name in ["../config.json", "..\\x.mp4", ".partial-one.mp4", "", "a/b.mp4"]:
            self.assertIsNone(content_sync.library_file(name), name)
        self.assertIsNotNone(content_sync.library_file("one.mp4"))

    def test_sync_sends_library_files_to_agents(self):
        async def run():
            await device_manager.add_or_update("quest-a", "10.0.0.5", agent_connected=True)
            with patch.object(content_sync.device_ws_manager, "is_connected", return_value=True), \
                 patch.object(content_sync.device_ws_manager, "send_command", new=AsyncMock(return_value=True)) as send:
                result = await content_sync.sync_content([])
            return result, send
        result, send = asyncio.run(run())
        self.assertEqual(result["missingInLibrary"], ["two.mp4"])
        command = send.call_args.args[1]
        self.assertEqual(command["action"], "sync_content")
        self.assertEqual(command["files"], [{"name": "one.mp4", "size": 10, "url": "/api/content/files/one.mp4"}])

    def test_content_endpoint_serves_only_library_files(self):
        self.assertIsInstance(asyncio.run(main.content_file("one.mp4")), FileResponse)  # FileResponse handles Range
        self.assertEqual(asyncio.run(main.content_file("../config.json")).status_code, 404)

if __name__ == "__main__":
    unittest.main()
