import unittest
from unittest.mock import AsyncMock, patch

from App.server import playback_controller


class PlaybackControllerADBTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_via_adb_builds_action_from_adb_prefix(self):
        with patch.object(
            playback_controller,
            "get_config",
            return_value={
                "packageId": "com.example.player",
                "adbActionPrefix": "com.vrclass.player",
            },
        ):
            with patch.object(playback_controller.adb_executor, "shell", new=AsyncMock(return_value=(True, "ok"))) as shell_mock:
                await playback_controller._send_via_adb("192.168.0.10", "PLAY")

        shell_mock.assert_awaited_once_with(
            "192.168.0.10",
            "am broadcast -a com.vrclass.player.PLAY -n com.example.player/.CommandReceiver",
        )

    async def test_send_via_adb_handles_play_stop_recenter(self):
        with patch.object(
            playback_controller,
            "get_config",
            return_value={
                "packageId": "com.demo.player",
                "adbActionPrefix": "com.vrclass.player.",
            },
        ):
            with patch.object(playback_controller.adb_executor, "shell", new=AsyncMock(return_value=(True, "ok"))) as shell_mock:
                await playback_controller._send_via_adb("10.0.0.2", "play")
                await playback_controller._send_via_adb("10.0.0.2", "STOP")
                await playback_controller._send_via_adb("10.0.0.2", "Recenter")

        built_commands = [call.args[1] for call in shell_mock.await_args_list]
        self.assertEqual(
            built_commands,
            [
                "am broadcast -a com.vrclass.player.PLAY -n com.demo.player/.CommandReceiver",
                "am broadcast -a com.vrclass.player.STOP -n com.demo.player/.CommandReceiver",
                "am broadcast -a com.vrclass.player.RECENTER -n com.demo.player/.CommandReceiver",
            ],
        )


if __name__ == "__main__":
    unittest.main()
