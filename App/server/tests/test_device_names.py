import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from App.server import device_manager as dm_module
from App.server.device_manager import DeviceManager


class _NameStore:
    """In-memory replacement for the device_names.json helpers in config.py."""

    def __init__(self):
        self.names = {}

    def get(self, device_id):
        return self.names.get(device_id)

    def set(self, device_id, name):
        if name:
            self.names[device_id] = name
        else:
            self.names.pop(device_id, None)


class DeviceNameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = _NameStore()
        self.broadcast = AsyncMock()
        self.ws_send = AsyncMock(return_value=True)
        self.ws_connected = set()
        self.patches = [
            patch("App.server.device_manager.ws_manager.broadcast", new=self.broadcast),
            patch("App.server.device_manager.get_device_name", side_effect=self.store.get),
            patch("App.server.device_manager.set_device_name", side_effect=self.store.set),
            patch.object(dm_module.device_ws_manager, "send_command", new=self.ws_send),
            patch.object(dm_module.device_ws_manager, "is_connected", side_effect=lambda d: d in self.ws_connected),
        ]
        for p in self.patches:
            p.start()
        self.manager = DeviceManager()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def _status(self, device_id="quest-1", ip="192.168.1.20", **extra):
        status = {"deviceId": device_id, "state": "idle"}
        status.update(extra)
        return await self.manager.apply_player_status(device_id, ip, status)

    def _name_changes(self):
        return [
            call.args[0]["changes"].get("name")
            for call in self.broadcast.await_args_list
            if "changes" in call.args[0] and "name" in call.args[0]["changes"]
        ]

    # --- priority ---------------------------------------------------------

    async def test_device_reported_name_wins_over_server_fallback(self):
        self.store.set("quest-1", "Old server name")
        await self._status(deviceName="12")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "12")
        self.assertEqual(device.name_source, "device")
        self.assertEqual(device.reported_name, "12")

    async def test_server_fallback_used_when_player_does_not_report_names(self):
        self.store.set("quest-1", "Row 3")
        await self._status()  # no deviceName key at all (older player)
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "Row 3")
        self.assertEqual(device.name_source, "server")

    async def test_id_used_when_nothing_known(self):
        await self._status(deviceName="")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "quest-1")
        self.assertEqual(device.name_source, "id")

    async def test_reinstalled_app_gets_fallback_name_pushed(self):
        self.store.set("quest-1", "7")
        self.ws_connected.add("quest-1")
        await self._status(deviceName="")  # fresh install: no name on device yet
        self.ws_send.assert_awaited_once()
        cmd = self.ws_send.await_args.args[1]
        self.assertEqual(cmd["action"], "set_name")
        self.assertEqual(cmd["name"], "7")

    # --- instructor assignment --------------------------------------------

    async def test_update_name_pushes_via_ws_and_confirms_on_report(self):
        await self._status(deviceName="")
        self.ws_connected.add("quest-1")

        result = await self.manager.update_name("quest-1", "15")
        self.assertTrue(result["pushed"])
        self.assertEqual(result["via"], "ws")
        self.assertFalse(result["pending"])
        self.assertEqual(self.store.names["quest-1"], "15")

        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "15")
        self.assertEqual(device.name_source, "pending")

        # The headset saves the name and reports it back -> confirmed.
        await self._status(deviceName="15")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name_source, "device")
        self.assertEqual(device.pending_name, "")

    async def test_update_name_on_offline_device_is_queued_and_pushed_on_return(self):
        await self._status(deviceName="")
        await self.manager.add_or_update("quest-1", "192.168.1.20", seen=False, online=False, player_connected=False)

        result = await self.manager.update_name("quest-1", "3")
        self.assertFalse(result["pushed"])
        self.assertTrue(result["pending"])
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "3")  # shown immediately

        # Device comes back reporting its old (empty) name -> server pushes the pending one.
        self.ws_connected.add("quest-1")
        await self._status(deviceName="")
        self.ws_send.assert_awaited_once()
        self.assertEqual(self.ws_send.await_args.args[1]["name"], "3")

        # Still pending until confirmed; a stale report must not overwrite the assignment.
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "3")
        self.assertEqual(device.name_source, "pending")

    async def test_stale_report_does_not_flip_name_back_after_rename(self):
        await self._status(deviceName="A")
        self.ws_connected.add("quest-1")
        await self.manager.update_name("quest-1", "B")

        # A heartbeat that was already in flight still says "A".
        await self._status(deviceName="A")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "B")

        await self._status(deviceName="B")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "B")
        self.assertEqual(device.name_source, "device")

    async def test_clearing_name_removes_fallback_and_shows_id(self):
        self.store.set("quest-1", "9")
        self.ws_connected.add("quest-1")
        await self._status(deviceName="9")

        result = await self.manager.update_name("quest-1", "")
        self.assertTrue(result["pushed"])
        self.assertNotIn("quest-1", self.store.names)
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "quest-1")

        await self._status(deviceName="")
        device = await self.manager.get("quest-1")
        self.assertEqual(device.name, "quest-1")
        self.assertEqual(device.name_source, "id")
        # Nothing to push any more (fallback removed).
        self.assertEqual(self.ws_send.await_count, 1)

    async def test_name_push_is_throttled(self):
        await self._status(deviceName="")
        self.ws_connected.add("quest-1")
        await self.manager.update_name("quest-1", "4")
        self.assertEqual(self.ws_send.await_count, 1)

        # Repeated stale reports within the retry window do not spam the device.
        await self._status(deviceName="")
        await self._status(deviceName="")
        self.assertEqual(self.ws_send.await_count, 1)

        self.manager._last_name_push["quest-1"] = 0.0
        await self._status(deviceName="")
        self.assertEqual(self.ws_send.await_count, 2)

    async def test_http_fallback_when_ws_not_connected(self):
        await self._status(deviceName="")

        class _Resp:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _Session:
            calls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def put(self, url, **kwargs):
                _Session.calls.append((url, kwargs))
                return _Resp()

        with patch.object(dm_module.aiohttp, "ClientSession", _Session):
            result = await self.manager.update_name("quest-1", "21")

        self.assertTrue(result["pushed"])
        self.assertEqual(result["via"], "http")
        self.ws_send.assert_not_awaited()
        self.assertEqual(_Session.calls[0][0], "http://192.168.1.20:8080/name")
        self.assertEqual(_Session.calls[0][1]["json"], {"name": "21"})

    async def test_broadcasts_name_change_once(self):
        await self._status(deviceName="1")
        self.broadcast.reset_mock()
        await self._status(deviceName="1")
        await self._status(deviceName="1")
        self.assertEqual(self._name_changes(), [])
        await self._status(deviceName="2")
        self.assertEqual(self._name_changes(), ["2"])


class WsDisconnectGraceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.broadcast = AsyncMock()
        self.ws_connected = set()
        self.patches = [
            patch("App.server.device_manager.ws_manager.broadcast", new=self.broadcast),
            patch("App.server.device_manager.get_device_name", return_value=None),
            patch.object(dm_module.device_ws_manager, "is_connected", side_effect=lambda d: d in self.ws_connected),
            patch.object(dm_module, "WS_DISCONNECT_GRACE_SEC", 0.02),
        ]
        for p in self.patches:
            p.start()
        self.manager = DeviceManager()
        await self.manager.add_or_update("quest-1", "192.168.1.20", player_connected=True, ws_connected=True)

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def test_quick_reconnect_does_not_flip_ws_badge(self):
        self.broadcast.reset_mock()
        self.manager.schedule_ws_disconnect_check("quest-1")
        # Player reconnects before the grace period ends.
        self.manager.cancel_ws_disconnect_grace("quest-1")
        self.ws_connected.add("quest-1")
        await asyncio.sleep(0.05)

        device = await self.manager.get("quest-1")
        self.assertTrue(device.ws_connected)
        self.broadcast.assert_not_awaited()

    async def test_reconnect_within_grace_without_cancel_is_detected(self):
        self.manager.schedule_ws_disconnect_check("quest-1")
        self.ws_connected.add("quest-1")
        await asyncio.sleep(0.05)
        device = await self.manager.get("quest-1")
        self.assertTrue(device.ws_connected)

    async def test_ws_badge_drops_after_grace_if_still_gone(self):
        self.manager.schedule_ws_disconnect_check("quest-1")
        await asyncio.sleep(0.05)
        device = await self.manager.get("quest-1")
        self.assertFalse(device.ws_connected)
        # HTTP API may still be up: the liveness loop decides about player_connected/online.
        self.assertTrue(device.player_connected)
        self.assertTrue(device.online)


class ApplyPlayerStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = [
            patch("App.server.device_manager.ws_manager.broadcast", new=AsyncMock()),
            patch("App.server.device_manager.get_device_name", return_value=None),
        ]
        for p in self.patches:
            p.start()
        self.manager = DeviceManager()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def test_status_without_id_and_without_hint_is_ignored(self):
        result = await self.manager.apply_player_status("", "192.168.1.30", {})
        self.assertIsNone(result)
        self.assertEqual(await self.manager.get_all(), [])

    async def test_empty_status_for_known_device_keeps_it_alive_without_renaming(self):
        await self.manager.apply_player_status("quest-1", "192.168.1.30", {"deviceId": "quest-1", "deviceName": "5"})
        device = await self.manager.get("quest-1")
        device.last_seen = 0
        await self.manager.apply_player_status("quest-1", "192.168.1.30", {})
        device = await self.manager.get("quest-1")
        self.assertGreater(device.last_seen, 0)
        self.assertEqual(device.name, "5")
        self.assertEqual(len(await self.manager.get_all()), 1)


if __name__ == "__main__":
    unittest.main()
