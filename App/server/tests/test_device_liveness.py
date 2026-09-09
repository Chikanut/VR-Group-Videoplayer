import time
import unittest
from unittest.mock import AsyncMock, patch

from App.server import device_manager as dm_module
from App.server.device_manager import DeviceManager
from App.server.device_ws_manager import DeviceWSManager


class _FakeWS:
    def __init__(self):
        self.closed = False

    async def close(self, code=1000, reason=""):
        self.closed = True


class DeviceWSManagerReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_socket_cleanup_keeps_new_registration(self):
        manager = DeviceWSManager()
        old_ws = _FakeWS()
        new_ws = _FakeWS()

        await manager.register("quest-1", old_ws)
        await manager.register("quest-1", new_ws)
        self.assertTrue(old_ws.closed)

        # The old handler finishes after the new socket replaced it.
        gone = await manager.disconnect("quest-1", old_ws)
        self.assertFalse(gone)
        self.assertTrue(manager.is_connected("quest-1"))

        gone = await manager.disconnect("quest-1", new_ws)
        self.assertTrue(gone)
        self.assertFalse(manager.is_connected("quest-1"))


class AddOrUpdateSeenSemanticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.broadcast = patch("App.server.device_manager.ws_manager.broadcast", new=AsyncMock())
        self.broadcast.start()

    async def asyncTearDown(self):
        self.broadcast.stop()

    async def test_bookkeeping_update_does_not_resurrect_offline_device(self):
        manager = DeviceManager()
        await manager.add_or_update("quest-1", "192.168.1.20", player_connected=True)
        await manager.add_or_update(
            "quest-1", "192.168.1.20", seen=False, online=False, player_connected=False
        )
        device = await manager.get("quest-1")
        old_last_seen = device.last_seen

        await manager.add_or_update("quest-1", "192.168.1.20", seen=False, effective_volume=0.5)

        device = await manager.get("quest-1")
        self.assertFalse(device.online)
        self.assertFalse(device.player_connected)
        self.assertEqual(device.last_seen, old_last_seen)
        self.assertEqual(device.effective_volume, 0.5)

    async def test_bookkeeping_for_unknown_device_creates_nothing(self):
        manager = DeviceManager()
        result = await manager.add_or_update("ghost", "192.168.1.99", seen=False, playback_time=3.0)
        self.assertIsNone(result)
        self.assertEqual(await manager.get_all(), [])

    async def test_ip_change_drops_stale_index_and_new_device_takes_old_ip(self):
        manager = DeviceManager()
        await manager.add_or_update("quest-a", "192.168.1.20", player_connected=True)
        # Device A moves to a new address.
        await manager.add_or_update("quest-a", "192.168.1.21", player_connected=True)
        self.assertIsNone(manager.get_device_id_by_ip("192.168.1.20"))
        self.assertEqual(manager.get_device_id_by_ip("192.168.1.21"), "quest-a")

        # A different headset later gets the old lease: it must NOT be merged into A.
        device_a = await manager.get("quest-a")
        device_a.last_seen = time.time() - dm_module.IP_ALIAS_WINDOW_SEC - 5
        manager._ip_to_device["192.168.1.20"] = "quest-a"  # simulate a stale entry
        result = await manager.add_or_update("quest-b", "192.168.1.20", player_connected=True)
        self.assertEqual(result.device_id, "quest-b")
        self.assertEqual(len(await manager.get_all()), 2)

    async def test_ip_fallback_id_aliases_to_known_device(self):
        manager = DeviceManager()
        await manager.add_or_update("quest-a", "192.168.1.20", player_connected=True)
        device_a = await manager.get("quest-a")
        device_a.last_seen = time.time() - dm_module.IP_ALIAS_WINDOW_SEC - 5

        # Status payload without an ID: caller falls back to the IP -> same device.
        result = await manager.add_or_update("192.168.1.20", "192.168.1.20", player_connected=True)
        self.assertEqual(result.device_id, "quest-a")
        self.assertEqual(len(await manager.get_all()), 1)


class LivenessPassTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = [
            patch("App.server.device_manager.ws_manager.broadcast", new=AsyncMock()),
            patch("App.server.device_manager.get_config", return_value={"deviceOfflineTimeout": 30}),
        ]
        for p in self.patches:
            p.start()
        self.manager = DeviceManager()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def _add_quiet_device(self, device_id, ip, silent_for):
        await self.manager.add_or_update(device_id, ip, player_connected=True)
        device = await self.manager.get(device_id)
        device.last_seen = time.time() - silent_for
        return device

    async def test_fresh_device_is_not_probed(self):
        await self.manager.add_or_update("quest-1", "192.168.1.20", player_connected=True)
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=None)) as probe:
            await self.manager.run_liveness_pass()
        probe.assert_not_awaited()

    async def test_stalled_heartbeat_but_http_alive_stays_online_and_refreshes_status(self):
        await self._add_quiet_device("quest-1", "192.168.1.20", silent_for=40)
        status = {"deviceId": "quest-1", "state": "playing", "time": 42.0, "duration": 100.0}
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=status)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=False):
            await self.manager.run_liveness_pass()

        device = await self.manager.get("quest-1")
        self.assertTrue(device.online)
        self.assertTrue(device.player_connected)
        self.assertEqual(device.playback_time, 42.0)
        self.assertLess(time.time() - device.last_seen, 5)

    async def test_ws_alive_keeps_device_online_even_if_http_fails(self):
        await self._add_quiet_device("quest-1", "192.168.1.20", silent_for=120)
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=None)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=True):
            await self.manager.run_liveness_pass()

        device = await self.manager.get("quest-1")
        self.assertTrue(device.online)
        self.assertTrue(device.player_connected)

    async def test_no_ws_and_http_down_within_timeout_is_still_online(self):
        await self._add_quiet_device("quest-1", "192.168.1.20", silent_for=15)
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=None)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=False):
            await self.manager.run_liveness_pass()

        device = await self.manager.get("quest-1")
        self.assertTrue(device.online)

    async def test_no_ws_and_http_down_past_timeout_goes_offline(self):
        await self._add_quiet_device("quest-1", "192.168.1.20", silent_for=45)
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=None)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=False):
            await self.manager.run_liveness_pass()

        device = await self.manager.get("quest-1")
        self.assertFalse(device.online)
        self.assertFalse(device.player_connected)

    async def test_offline_device_is_reprobed_and_comes_back(self):
        await self._add_quiet_device("quest-1", "192.168.1.20", silent_for=45)
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=None)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=False):
            await self.manager.run_liveness_pass()
        self.assertFalse((await self.manager.get("quest-1")).online)

        status = {"deviceId": "quest-1", "state": "idle"}
        self.manager._liveness_pass_count = dm_module.OFFLINE_PROBE_EVERY - 1
        with patch.object(dm_module, "probe_player_status", new=AsyncMock(return_value=status)), \
             patch.object(dm_module.device_ws_manager, "is_connected", return_value=False):
            await self.manager.run_liveness_pass()

        device = await self.manager.get("quest-1")
        self.assertTrue(device.online)
        self.assertTrue(device.player_connected)


if __name__ == "__main__":
    unittest.main()
