import unittest

from App.server.main import _register_kwargs


class RegisterKwargsTests(unittest.TestCase):
    def test_register_never_carries_playback_fields(self):
        msg = {
            "type": "register",
            "deviceId": "quest-1",
            "state": "idle",          # older players hardcode this in register
            "file": "",
            "time": 0,
            "duration": 0,
            "battery": 77,
            "playerVersion": "1.7.0",
            "deviceModel": "Quest 3",
        }
        kwargs = _register_kwargs(msg)
        self.assertNotIn("playback_state", kwargs)
        self.assertNotIn("current_video", kwargs)
        self.assertNotIn("playback_time", kwargs)
        self.assertNotIn("playback_duration", kwargs)
        self.assertEqual(kwargs["battery"], 77)
        self.assertEqual(kwargs["player_version"], "1.7.0")
        self.assertEqual(kwargs["device_model"], "Quest 3")

    def test_missing_version_does_not_blank_known_version(self):
        kwargs = _register_kwargs({"type": "register", "deviceId": "quest-1", "playerVersion": ""})
        self.assertNotIn("player_version", kwargs)
        kwargs = _register_kwargs({"type": "register", "deviceId": "quest-1"})
        self.assertNotIn("player_version", kwargs)


if __name__ == "__main__":
    unittest.main()
