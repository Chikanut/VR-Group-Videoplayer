import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import playback_controller


def _device(device_id="quest-1"):
    return SimpleNamespace(
        device_id=device_id,
        name=device_id,
        online=True,
        player_connected=True,
    )


class PlaybackControllerSeekTests(unittest.IsolatedAsyncioTestCase):
    async def test_seek_sends_action_path_and_time_payload(self):
        device = _device("quest-1")

        with patch.object(
            playback_controller,
            "_resolve_devices",
            new=AsyncMock(return_value=[device]),
        ), patch.object(
            playback_controller,
            "_send_command_to_device",
            new=AsyncMock(return_value={"success": True}),
        ) as send_mock:
            result = await playback_controller.seek_video(12.5, [])

        self.assertEqual(result["time"], 12.5)
        self.assertEqual(result["success"], [{"deviceId": "quest-1"}])
        self.assertEqual(result["failed"], [])

        args = send_mock.await_args.args
        self.assertIs(args[0], device)
        self.assertEqual(args[1], "seek")
        self.assertEqual(args[2], "/seek")
        self.assertEqual(args[3], {"time": 12.5})

    async def test_seek_targets_only_selected_device(self):
        target = _device("quest-2")

        resolve_mock = AsyncMock(return_value=[target])
        with patch.object(
            playback_controller,
            "_resolve_devices",
            new=resolve_mock,
        ), patch.object(
            playback_controller,
            "_send_command_to_device",
            new=AsyncMock(return_value={"success": True}),
        ) as send_mock:
            result = await playback_controller.seek_video(30.0, ["quest-2"])

        # Only the requested device id is resolved...
        resolve_mock.assert_awaited_once_with(["quest-2"])
        # ...and only that device receives the seek command.
        self.assertEqual(send_mock.await_count, 1)
        self.assertIs(send_mock.await_args.args[0], target)
        self.assertEqual(result["success"], [{"deviceId": "quest-2"}])

    async def test_seek_clamps_negative_time_to_zero(self):
        device = _device("quest-1")

        with patch.object(
            playback_controller,
            "_resolve_devices",
            new=AsyncMock(return_value=[device]),
        ), patch.object(
            playback_controller,
            "_send_command_to_device",
            new=AsyncMock(return_value={"success": True}),
        ) as send_mock:
            result = await playback_controller.seek_video(-5.0, [])

        self.assertEqual(result["time"], 0.0)
        self.assertEqual(send_mock.await_args.args[3], {"time": 0.0})

    async def test_seek_no_devices_returns_message(self):
        with patch.object(
            playback_controller,
            "_resolve_devices",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            playback_controller,
            "_send_command_to_device",
            new=AsyncMock(),
        ) as send_mock:
            result = await playback_controller.seek_video(10.0, [])

        self.assertEqual(result["success"], [])
        self.assertEqual(result["failed"], [])
        self.assertIn("message", result)
        send_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
