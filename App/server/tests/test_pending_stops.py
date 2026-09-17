import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import pending_stops as pending_stops_module
from App.server import playback_controller
from App.server.pending_stops import STOP_RESEND_SEC, PendingStops


class PendingStopsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stops = PendingStops()
        self.deliver = AsyncMock(return_value=True)
        self.stops._deliver_stop = self.deliver

    async def test_device_waking_with_open_video_gets_stop_again(self):
        self.stops.mark(["quest-1"], now=100.0)

        # Came back from sleep 2 minutes later still showing the paused video.
        resent = await self.stops.reconcile("quest-1", "192.168.1.20", "paused", now=220.0)

        self.assertTrue(resent)
        self.deliver.assert_awaited_once_with("quest-1", "192.168.1.20")
        self.assertTrue(self.stops.is_pending("quest-1"))

    async def test_heartbeat_right_after_stop_does_not_resend(self):
        self.stops.mark(["quest-1"], now=100.0)

        resent = await self.stops.reconcile("quest-1", "ip", "playing", now=100.0 + STOP_RESEND_SEC - 1)

        self.assertFalse(resent)
        self.deliver.assert_not_awaited()

    async def test_resend_is_throttled(self):
        self.stops.mark(["quest-1"], now=0.0)
        await self.stops.reconcile("quest-1", "ip", "paused", now=60.0)
        await self.stops.reconcile("quest-1", "ip", "paused", now=62.0)
        await self.stops.reconcile("quest-1", "ip", "paused", now=66.0)

        self.assertEqual(self.deliver.await_count, 2)

    async def test_idle_report_confirms_stop(self):
        self.stops.mark(["quest-1"], now=0.0)

        await self.stops.reconcile("quest-1", "ip", "idle", now=60.0)
        resent = await self.stops.reconcile("quest-1", "ip", "playing", now=120.0)

        self.assertFalse(self.stops.is_pending("quest-1"))
        self.assertFalse(resent)
        self.deliver.assert_not_awaited()

    async def test_devices_without_pending_stop_are_untouched(self):
        resent = await self.stops.reconcile("quest-2", "ip", "playing", now=60.0)
        self.assertFalse(resent)
        self.deliver.assert_not_awaited()

    async def test_missing_state_is_ignored(self):
        self.stops.mark(["quest-1"], now=0.0)
        resent = await self.stops.reconcile("quest-1", "ip", None, now=60.0)
        self.assertFalse(resent)
        self.assertTrue(self.stops.is_pending("quest-1"))


class PlaybackControllerPendingStopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stops = PendingStops()
        patcher = patch.object(playback_controller, "pending_stops", self.stops)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_global_stop_marks_offline_devices_too(self):
        with patch.object(
            playback_controller.device_manager, "get_all_ids", new=AsyncMock(return_value=["awake", "asleep"])
        ), patch.object(
            playback_controller, "_resolve_devices", new=AsyncMock(return_value=[])
        ):
            await playback_controller.send_command("stop", [])

        self.assertTrue(self.stops.is_pending("awake"))
        self.assertTrue(self.stops.is_pending("asleep"))

    async def test_targeted_stop_marks_only_targets(self):
        with patch.object(playback_controller, "_resolve_devices", new=AsyncMock(return_value=[])):
            await playback_controller.send_command("stop", ["quest-1"])

        self.assertTrue(self.stops.is_pending("quest-1"))
        self.assertFalse(self.stops.is_pending("quest-2"))

    async def test_pause_does_not_mark(self):
        with patch.object(playback_controller, "_resolve_devices", new=AsyncMock(return_value=[])):
            await playback_controller.send_command("pause", ["quest-1"])

        self.assertFalse(self.stops.is_pending("quest-1"))

    async def test_successful_open_clears_pending_stop(self):
        self.stops.mark(["reached", "asleep"])
        devices = [
            SimpleNamespace(device_id="reached", name="reached", requirements_detail=[]),
            SimpleNamespace(device_id="asleep", name="asleep", requirements_detail=[]),
        ]

        async def fake_send(device, command, path, payload=None):
            return {"success": device.device_id == "reached"}

        config = {"requirementVideos": [{"id": "v1", "filename": "a.mp4"}]}
        with patch.object(playback_controller, "get_config", return_value=config), patch.object(
            playback_controller, "_resolve_devices", new=AsyncMock(return_value=devices)
        ), patch.object(playback_controller, "_send_command_to_device", side_effect=fake_send):
            await playback_controller.open_video("v1", [])

        self.assertFalse(self.stops.is_pending("reached"))
        self.assertTrue(self.stops.is_pending("asleep"))


class DeliverStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivers_via_websocket_when_connected(self):
        stops = PendingStops()
        ws = SimpleNamespace(is_connected=lambda _id: True, send_command=AsyncMock(return_value=True))
        with patch.object(pending_stops_module, "device_ws_manager", ws):
            delivered = await stops._deliver_stop("quest-1", "192.168.1.20")

        self.assertTrue(delivered)
        ws.send_command.assert_awaited_once_with("quest-1", {"type": "command", "action": "stop"})


if __name__ == "__main__":
    unittest.main()
