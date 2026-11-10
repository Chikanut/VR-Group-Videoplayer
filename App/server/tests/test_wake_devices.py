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

        async def post_wake(ip):
            posted.append(ip)
            return {"success": ip != "10.0.0.2", "error": "timeout"}

        with mock.patch.object(playback_controller.device_manager, "get_all", return_value=devices), \
                mock.patch.object(playback_controller, "_post_wake", side_effect=post_wake):
            return asyncio.run(playback_controller.wake_devices(device_ids)), posted

    def test_wakes_every_known_device_including_offline(self):
        result, posted = self._run([])

        self.assertEqual(posted, ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(result["success"], [{"deviceId": "a"}])
        self.assertEqual(result["failed"], [{"deviceId": "b", "error": "timeout"}])

    def test_wakes_only_selected_devices(self):
        _, posted = self._run(["b"])

        self.assertEqual(posted, ["10.0.0.2"])


if __name__ == "__main__":
    unittest.main()
