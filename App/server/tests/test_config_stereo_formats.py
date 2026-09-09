import unittest

from App.server import config


class ConfigStereoFormatTests(unittest.TestCase):
    def _video(self, **overrides):
        base = {"name": "Lesson", "filename": "lesson_180_LR.mp4"}
        base.update(overrides)
        return config._normalize_config({"requirementVideos": [base]})["requirementVideos"][0]

    def test_legacy_config_keeps_working_with_defaults(self):
        video = self._video(videoType="360")
        self.assertEqual(video["videoType"], "360")
        self.assertIs(video["swapEyes"], False)
        self.assertEqual(video["forwardYaw"], 0.0)
        self.assertNotIn("detectedType", video)
        self.assertNotIn("probe", video)

    def test_new_format_ids_are_accepted(self):
        for format_id in ("360_sbs", "360_tb", "180", "180_sbs", "180_tb", "auto", "2d"):
            self.assertEqual(self._video(videoType=format_id)["videoType"], format_id)

    def test_aliases_are_normalized(self):
        self.assertEqual(self._video(videoType="180_LR")["videoType"], "180_sbs")
        self.assertEqual(self._video(videoType="360_OU")["videoType"], "360_tb")
        self.assertEqual(self._video(videoType="sphere")["videoType"], "360")
        self.assertEqual(self._video(videoType="flat")["videoType"], "2d")

    def test_unknown_type_falls_back_to_360(self):
        self.assertEqual(self._video(videoType="cubemap")["videoType"], "360")
        self.assertEqual(self._video()["videoType"], "360")

    def test_stereo_extras_are_normalized(self):
        video = self._video(videoType="180_sbs", swapEyes=1, forwardYaw="45.5")
        self.assertIs(video["swapEyes"], True)
        self.assertEqual(video["forwardYaw"], 45.5)

        video = self._video(forwardYaw="not-a-number")
        self.assertEqual(video["forwardYaw"], 0.0)

        video = self._video(forwardYaw=720)
        self.assertEqual(video["forwardYaw"], 360.0)

    def test_detection_cache_is_kept(self):
        probe = {"width": 8192, "height": 4096, "codec": "hevc"}
        video = self._video(videoType="auto", detectedType="180_LR", detectionSource="filename", probe=probe)
        self.assertEqual(video["videoType"], "auto")
        self.assertEqual(video["detectedType"], "180_sbs")
        self.assertEqual(video["detectionSource"], "filename")
        self.assertEqual(video["probe"], probe)

    def test_invalid_detection_cache_is_dropped(self):
        video = self._video(detectedType="garbage", probe="nope")
        self.assertNotIn("detectedType", video)
        self.assertNotIn("probe", video)


if __name__ == "__main__":
    unittest.main()
