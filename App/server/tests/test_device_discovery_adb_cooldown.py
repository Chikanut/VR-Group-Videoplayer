import unittest
from unittest.mock import AsyncMock, patch

from App.server import device_discovery


class DeviceDiscoveryAdbCooldownTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        device_discovery._adb_connect_attempt_ts.clear()

    async def test_skips_connect_when_already_connected(self):
        with patch.object(device_discovery.adb_executor, "is_connected", new=AsyncMock(return_value=True)) as is_connected_mock, \
             patch.object(device_discovery.adb_executor, "connect", new=AsyncMock(return_value=True)) as connect_mock:
            connected = await device_discovery._ensure_adb_connected("192.168.1.10")

        self.assertTrue(connected)
        is_connected_mock.assert_awaited_once_with("192.168.1.10")
        connect_mock.assert_not_awaited()

    async def test_applies_connect_cooldown_for_failed_attempts(self):
        with patch.object(device_discovery.adb_executor, "is_connected", new=AsyncMock(return_value=False)), \
             patch.object(device_discovery.adb_executor, "connect", new=AsyncMock(return_value=False)) as connect_mock:
            first = await device_discovery._ensure_adb_connected("192.168.1.11")
            second = await device_discovery._ensure_adb_connected("192.168.1.11")

        self.assertFalse(first)
        self.assertFalse(second)
        connect_mock.assert_awaited_once_with("192.168.1.11")


if __name__ == "__main__":
    unittest.main()
