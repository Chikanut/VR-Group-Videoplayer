import asyncio
import unittest
from unittest import mock

from App.server import playback_controller


class WakeDevicesTests(unittest.TestCase):
    def _run(self, device_ids):
        devices = [
            {"deviceId": "a", "ip": "10.0.0.1", "online": False},
            {"deviceId": "b", "ip": "10.0.0.2", "online": True},
            {"deviceId": "c", "ip": "unknown"},
        ]
        posted = []

        async def post_wake(ip, path):
            posted.append(ip)
            return {"success": ip != "10.0.0.2", "error": "timeout"}

        with mock.patch.object(playback_controller.device_manager, "get_all", return_value=devices), \
                mock.patch.object(playback_controller, "_post_watchdog", side_effect=post_wake):
            return asyncio.run(playback_controller.wake_devices(device_ids)), posted

    def test_wakes_every_known_device_including_offline(self):
        result, posted = self._run([])

        self.assertEqual(posted, ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(result["success"], [{"deviceId": "a"}])
        self.assertEqual(result["failed"], [{"deviceId": "b", "error": "timeout"}])

    def test_wakes_only_selected_devices(self):
        _, posted = self._run(["b"])

        self.assertEqual(posted, ["10.0.0.2"])

    def test_autostart_posts_on_or_off_to_the_watchdog(self):
        posted = []

        async def post(ip, path):
            posted.append((ip, path))
            return {"success": True}

        devices = [{"deviceId": "a", "ip": "10.0.0.1", "online": False}]
        with mock.patch.object(playback_controller.device_manager, "get_all", return_value=devices),                 mock.patch.object(playback_controller, "_post_watchdog", side_effect=post):
            asyncio.run(playback_controller.set_autostart(False, []))
            asyncio.run(playback_controller.set_autostart(True, ["a"]))

        self.assertEqual(posted, [("10.0.0.1", "/autostart/off"), ("10.0.0.1", "/autostart/on")])


    def test_autostart_state_of_unknown_device(self):
        with mock.patch.object(playback_controller.device_manager, "get", new=mock.AsyncMock(return_value=None)):
            self.assertEqual(asyncio.run(playback_controller.get_autostart("nope")), {"error": "Device not found"})

    def test_autostart_state_is_unknown_when_the_watchdog_does_not_answer(self):
        from types import SimpleNamespace
        device = SimpleNamespace(ip="127.0.0.1")
        with mock.patch.object(playback_controller.device_manager, "get", new=mock.AsyncMock(return_value=device)),                 mock.patch.object(playback_controller, "WAKE_PORT", 9),                 mock.patch.object(playback_controller, "REQUEST_TIMEOUT", 2):
            result = asyncio.run(playback_controller.get_autostart("a"))
        self.assertIsNone(result["autostart"])
        self.assertTrue(result["error"])

if __name__ == "__main__":
    unittest.main()
