import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import playback_controller


class PlaybackControllerOpenTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_video_sends_filename_mode_and_placement(self):
        device = SimpleNamespace(
            device_id="quest-1",
            name="Quest 1",
            online=True,
            player_connected=True,
            requirements_detail=[{"type": "video", "id": "video-1", "present": True}],
        )

        with patch.object(
            playback_controller,
            "get_config",
            return_value={
                "requirementVideos": [
                    {
                        "id": "video-1",
                        "name": "Lesson 01",
                        "filename": "lesson_01.mp4",
                        "videoType": "2d",
                        "placementMode": "free",
                        "loop": True,
                    }
                ]
            },
        ), patch.object(
            playback_controller,
            "_resolve_devices",
            new=AsyncMock(return_value=[device]),
        ), patch.object(
            playback_controller,
            "_send_command_to_device",
            new=AsyncMock(return_value={"success": True}),
        ) as send_mock:
            result = await playback_controller.open_video("video-1", [])

        self.assertEqual(result["failed"], [])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["success"], [{"deviceId": "quest-1"}])

        payload = send_mock.await_args.args[3]
        self.assertEqual(payload["file"], "lesson_01.mp4")
        self.assertEqual(payload["mode"], "2d")
        self.assertEqual(payload["placementMode"], "free")
        self.assertEqual(payload["loop"], True)


if __name__ == "__main__":
    unittest.main()
