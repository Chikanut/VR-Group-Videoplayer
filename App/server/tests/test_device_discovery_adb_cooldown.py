import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from App.server import device_discovery


class DeviceDiscoveryProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_discovered_ip_updates_player_device(self):
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            device_discovery,
            "_probe_player_http",
            new=AsyncMock(return_value={
                "deviceId": "quest-1",
                "deviceName": "Quest Front Row",
                "battery": 74,
                "state": "idle",
            }),
        ), patch.object(
            device_discovery.device_manager,
            "add_or_update",
            new=AsyncMock(),
        ) as add_or_update_mock, patch.object(
            device_discovery.device_manager,
            "mark_discovery_seen",
            new=AsyncMock(),
        ) as mark_seen_mock, patch.object(
            device_discovery.device_manager,
            "apply_device_name_from_device",
            new=AsyncMock(),
        ) as apply_name_mock, patch(
            "App.server.requirements_manager.check_requirements",
            new=AsyncMock(),
        ) as requirements_mock, patch.object(
            device_discovery.device_ws_manager,
            "is_connected",
            return_value=True,
        ):
            await device_discovery.process_discovered_ip("192.168.1.10", semaphore)

        add_or_update_mock.assert_awaited_once()
        self.assertEqual(add_or_update_mock.await_args.kwargs["player_connected"], True)
        self.assertEqual(add_or_update_mock.await_args.args[0], "quest-1")
        self.assertEqual(add_or_update_mock.await_args.args[1], "192.168.1.10")
        mark_seen_mock.assert_awaited_once_with("quest-1")
        apply_name_mock.assert_awaited_once_with("quest-1", "Quest Front Row")
        requirements_mock.assert_awaited_once_with("quest-1")


if __name__ == "__main__":
    unittest.main()
