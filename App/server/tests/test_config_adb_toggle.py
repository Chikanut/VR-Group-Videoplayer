import unittest

from App.server import config


class ConfigNormalizationTests(unittest.TestCase):
    def test_normalize_config_migrates_legacy_video_paths_to_filenames(self):
        normalized = config._normalize_config({
            "playerAppUrl": "https://example.com/player.apk",
            "apkDownloadUrl": "https://example.com/mobile-control.apk",
            "requirementVideos": [
                {
                    "name": "Lesson 01",
                    "localPath": r"C:\videos\lesson_01.mp4",
                    "videoType": "flat",
                    "placementMode": "locked",
                }
            ],
        })

        self.assertEqual(normalized["mobileAppUrl"], "https://example.com/mobile-control.apk")
        self.assertEqual(normalized["playerAppUrl"], "https://example.com/player.apk")
        self.assertEqual(normalized["requirementVideos"][0]["filename"], "lesson_01.mp4")
        self.assertEqual(normalized["requirementVideos"][0]["videoType"], "2d")
        self.assertEqual(normalized["requirementVideos"][0]["placementMode"], "locked")

    def test_normalize_config_rejects_unknown_placement_mode(self):
        normalized = config._normalize_config({
            "requirementVideos": [
                {
                    "filename": "lesson_02.mp4",
                    "placementMode": "sideways",
                }
            ]
        })

        self.assertEqual(normalized["requirementVideos"][0]["placementMode"], "default")


if __name__ == "__main__":
    unittest.main()
