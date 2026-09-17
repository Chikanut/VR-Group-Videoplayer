import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import device_discovery


class DeviceDiscoveryProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_discovered_ip_updates_player_device(self):
        semaphore = asyncio.Semaphore(1)
        status = {
            "deviceId": "quest-1",
            "deviceName": "Quest Front Row",
            "battery": 74,
            "state": "idle",
        }

        with patch.object(
            device_discovery,
            "_probe_player_http",
            new=AsyncMock(return_value=status),
        ), patch.object(
            device_discovery.device_manager,
            "apply_player_status",
            new=AsyncMock(return_value=SimpleNamespace(device_id="quest-1")),
        ) as apply_status_mock, patch(
            "App.server.requirements_manager.check_requirements",
            new=AsyncMock(),
        ) as requirements_mock, patch.object(
            device_discovery.device_ws_manager,
            "is_connected",
            return_value=True,
        ):
            await device_discovery.process_discovered_ip("192.168.1.10", semaphore)

        apply_status_mock.assert_awaited_once_with("quest-1", "192.168.1.10", status)
        requirements_mock.assert_awaited_once_with("quest-1")

    async def test_status_without_id_never_creates_ip_keyed_device(self):
        """A player answering /status with an empty body must not appear as a new
        device named after its IP (that is how headsets used to 'lose' their name)."""
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            device_discovery,
            "_probe_player_http",
            new=AsyncMock(return_value={}),
        ), patch.object(
            device_discovery.device_manager,
            "apply_player_status",
            new=AsyncMock(),
        ) as apply_status_mock, patch.object(
            device_discovery.device_manager,
            "get_device_id_by_ip",
            return_value=None,
        ), patch(
            "App.server.requirements_manager.check_requirements",
            new=AsyncMock(),
        ) as requirements_mock:
            await device_discovery.process_discovered_ip("192.168.1.10", semaphore)

        apply_status_mock.assert_not_awaited()
        requirements_mock.assert_not_awaited()

    async def test_status_without_id_refreshes_known_device_at_that_ip(self):
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            device_discovery,
            "_probe_player_http",
            new=AsyncMock(return_value={}),
        ), patch.object(
            device_discovery.device_manager,
            "apply_player_status",
            new=AsyncMock(return_value=SimpleNamespace(device_id="quest-1")),
        ) as apply_status_mock, patch.object(
            device_discovery.device_manager,
            "get_device_id_by_ip",
            return_value="quest-1",
        ), patch(
            "App.server.requirements_manager.check_requirements",
            new=AsyncMock(),
        ), patch.object(
            device_discovery.device_ws_manager,
            "is_connected",
            return_value=True,
        ):
            await device_discovery.process_discovered_ip("192.168.1.10", semaphore)

        apply_status_mock.assert_awaited_once_with("quest-1", "192.168.1.10", {})


if __name__ == "__main__":
    unittest.main()
