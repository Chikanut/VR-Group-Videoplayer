import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import playback_controller
from App.server.format_compat import check_video_on_device


def _device(**overrides):
    base = dict(
        device_id="quest-1",
        name="Quest 1",
        online=True,
        player_connected=True,
        requirements_detail=[{"type": "video", "id": "video-1", "present": True}],
        stereo_capable=None,
        decoder_caps={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class BuildOpenPayloadTests(unittest.TestCase):
    def test_legacy_video_type_sends_mode_and_new_fields(self):
        payload = playback_controller.build_open_payload({"filename": "a.mp4", "videoType": "360"})
        self.assertEqual(payload["mode"], "360")
        self.assertEqual(payload["format"], "360")
        self.assertEqual(payload["projection"], "360")
        self.assertEqual(payload["stereo"], "mono")
        self.assertIs(payload["swapEyes"], False)
        self.assertEqual(payload["forwardYaw"], 0.0)

    def test_180_sbs_keeps_legacy_mode_360_for_old_players(self):
        payload = playback_controller.build_open_payload({"filename": "a.mp4", "videoType": "180_sbs", "swapEyes": True, "forwardYaw": 90})
        self.assertEqual(payload["mode"], "360")
        self.assertEqual(payload["projection"], "180")
        self.assertEqual(payload["stereo"], "sbs")
        self.assertIs(payload["swapEyes"], True)
        self.assertEqual(payload["forwardYaw"], 90.0)

    def test_2d_stays_2d(self):
        payload = playback_controller.build_open_payload({"filename": "a.mp4", "videoType": "2d"})
        self.assertEqual(payload["mode"], "2d")
        self.assertEqual(payload["projection"], "flat")

    def test_auto_uses_cached_detection(self):
        payload = playback_controller.build_open_payload({"filename": "a.mp4", "videoType": "auto", "detectedType": "360_tb"})
        self.assertEqual(payload["format"], "360_tb")
        self.assertEqual(payload["mode"], "360")
        self.assertEqual(payload["stereo"], "tb")

    def test_auto_falls_back_to_filename_then_default(self):
        payload = playback_controller.build_open_payload({"filename": "reef_180_LR.mp4", "videoType": "auto"})
        self.assertEqual(payload["format"], "180_sbs")

        payload = playback_controller.build_open_payload({"filename": "lesson01.mp4", "videoType": "auto"})
        self.assertEqual(payload["format"], "360")
        self.assertEqual(payload["mode"], "360")

    def test_manual_type_beats_cached_detection(self):
        payload = playback_controller.build_open_payload({"filename": "a_180_LR.mp4", "videoType": "360", "detectedType": "180_sbs"})
        self.assertEqual(payload["format"], "360")


class OpenVideoStereoTests(unittest.IsolatedAsyncioTestCase):
    async def _open(self, video, device):
        with patch.object(
            playback_controller, "get_config", return_value={"requirementVideos": [video]}
        ), patch.object(
            playback_controller, "_resolve_devices", new=AsyncMock(return_value=[device])
        ), patch.object(
            playback_controller, "_send_command_to_device", new=AsyncMock(return_value={"success": True})
        ) as send_mock:
            result = await playback_controller.open_video("video-1", [])
        return result, send_mock

    async def test_open_sends_stereo_fields_and_legacy_mode(self):
        video = {"id": "video-1", "filename": "clip_180_LR.mp4", "videoType": "180_sbs", "loop": False}
        result, send_mock = await self._open(video, _device(stereo_capable=True))

        payload = send_mock.await_args.args[3]
        self.assertEqual(payload["file"], "clip_180_LR.mp4")
        self.assertEqual(payload["mode"], "360")
        self.assertEqual(payload["projection"], "180")
        self.assertEqual(payload["stereo"], "sbs")
        self.assertEqual(result["format"], "180_sbs")
        self.assertEqual(result["warnings"], [])

    async def test_open_warns_when_player_predates_stereo(self):
        video = {"id": "video-1", "filename": "clip_180_LR.mp4", "videoType": "180_sbs"}
        result, _ = await self._open(video, _device(stereo_capable=False))

        self.assertEqual(result["success"], [{"deviceId": "quest-1"}])  # still plays
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["warnings"][0]["deviceId"], "quest-1")
        self.assertIn("mono 360", result["warnings"][0]["warnings"][0])

    async def test_open_warns_when_decoder_cannot_handle_file(self):
        video = {
            "id": "video-1",
            "filename": "clip_180_LR.mp4",
            "videoType": "180_sbs",
            "probe": {"width": 8192, "height": 4096, "codec": "hevc", "bitDepth": 10, "fps": 59.94, "sizeBytes": 7_000_000_000},
        }
        device = _device(stereo_capable=True, decoder_caps={"hevcMaxWidth": 4096, "hevcMaxHeight": 4096, "hevcMain10": False, "storageFreeBytes": 5_000_000_000})
        result, _ = await self._open(video, device)

        warnings = result["warnings"][0]["warnings"]
        joined = " ".join(warnings)
        self.assertIn("width 8192", joined)
        self.assertIn("Main10", joined)
        self.assertIn("free storage", joined)


class FormatCompatTests(unittest.TestCase):
    def test_no_caps_no_probe_no_warnings(self):
        self.assertEqual(check_video_on_device({"videoType": "360_tb"}, _device()), [])

    def test_old_player_180_mono_warning(self):
        warnings = check_video_on_device({"videoType": "180"}, _device(stereo_capable=False))
        self.assertEqual(len(warnings), 1)
        self.assertIn("180", warnings[0])

    def test_fps_limit_at_8k(self):
        video = {"videoType": "180_sbs", "probe": {"width": 8192, "height": 4096, "codec": "hevc", "fps": 59.94}}
        device = _device(stereo_capable=True, decoder_caps={"hevcMaxWidth": 8192, "hevcMaxHeight": 8192, "hevcMaxFrameRateAt8K": 30})
        warnings = check_video_on_device(video, device)
        self.assertEqual(len(warnings), 1)
        self.assertIn("fps", warnings[0])


if __name__ == "__main__":
    unittest.main()
