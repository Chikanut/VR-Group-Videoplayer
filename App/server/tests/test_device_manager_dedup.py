import unittest
from unittest.mock import AsyncMock, patch

from App.server.device_manager import DeviceManager


class DeviceManagerDedupTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_or_update_reuses_existing_device_when_ip_matches(self):
        manager = DeviceManager()

        with patch("App.server.device_manager.ws_manager.broadcast", new=AsyncMock()):
            first = await manager.add_or_update("ws-device-id", "192.168.1.20", player_connected=True)
            second = await manager.add_or_update("http-device-id", "192.168.1.20", player_connected=True)

        self.assertEqual(first.device_id, "ws-device-id")
        self.assertEqual(second.device_id, "ws-device-id")

        all_devices = await manager.get_all()
        self.assertEqual(len(all_devices), 1)
        self.assertEqual(all_devices[0]["deviceId"], "ws-device-id")
        self.assertTrue(all_devices[0]["playerConnected"])


if __name__ == "__main__":
    unittest.main()
