import unittest

from App.server import player_probe
from App.server.models import DeviceState


class StatusToKwargsCompatibilityTests(unittest.TestCase):
    def test_old_player_status_derives_projection_from_mode(self):
        kwargs = player_probe.status_to_kwargs({"state": "playing", "file": "a.mp4", "mode": "360"})

        self.assertEqual(kwargs["current_mode"], "360")
        self.assertEqual(kwargs["current_projection"], "360")
        self.assertEqual(kwargs["current_stereo"], "mono")
        self.assertIs(kwargs["stereo_capable"], False)
        self.assertNotIn("decoder_caps", kwargs)

    def test_old_player_2d_mode(self):
        kwargs = player_probe.status_to_kwargs({"mode": "2d"})
        self.assertEqual(kwargs["current_projection"], "flat")
        self.assertEqual(kwargs["current_stereo"], "mono")

    def test_new_player_status_fields(self):
        status = {
            "state": "playing",
            "mode": "360",           # legacy value kept for old servers
            "projection": "180",
            "stereo": "sbs",
            "swapEyes": True,
            "videoWidth": 8192,
            "videoHeight": 4096,
            "backend": "unity",
            "decoderCaps": {"hevcMaxWidth": 8192, "hevcMaxHeight": 8192, "hevcMain10": True},
        }
        kwargs = player_probe.status_to_kwargs(status)

        self.assertEqual(kwargs["current_mode"], "360")
        self.assertEqual(kwargs["current_projection"], "180")
        self.assertEqual(kwargs["current_stereo"], "sbs")
        self.assertIs(kwargs["swap_eyes"], True)
        self.assertEqual(kwargs["video_width"], 8192)
        self.assertEqual(kwargs["video_height"], 4096)
        self.assertEqual(kwargs["backend"], "unity")
        self.assertEqual(kwargs["decoder_caps"]["hevcMaxWidth"], 8192)
        self.assertIs(kwargs["stereo_capable"], True)

    def test_invalid_new_fields_fall_back_safely(self):
        kwargs = player_probe.status_to_kwargs({"mode": "2d", "projection": "weird", "stereo": "3d", "decoderCaps": "nope", "videoWidth": "x"})
        self.assertEqual(kwargs["current_projection"], "flat")
        self.assertEqual(kwargs["current_stereo"], "mono")
        self.assertNotIn("decoder_caps", kwargs)
        self.assertEqual(kwargs["video_width"], 0)

    def test_kwargs_apply_to_device_state_and_serialize(self):
        device = DeviceState("quest-1", "192.168.1.5")
        for key, value in player_probe.status_to_kwargs({"mode": "360", "projection": "360", "stereo": "tb"}).items():
            setattr(device, key, value)
        data = device.to_dict()
        self.assertEqual(data["currentMode"], "360")
        self.assertEqual(data["currentProjection"], "360")
        self.assertEqual(data["currentStereo"], "tb")
        self.assertIs(data["stereoCapable"], True)
        self.assertEqual(data["decoderCaps"], {})


if __name__ == "__main__":
    unittest.main()
