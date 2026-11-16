import asyncio
import unittest
from unittest import mock

from App.server import config, headset_settings


class HeadsetSettingsTests(unittest.TestCase):
    def test_profile_is_sent_as_apply_settings_command(self):
        sent = []

        async def send(device_id, command):
            sent.append((device_id, command))
            return device_id != "gone"

        with mock.patch.object(headset_settings, "get_config", return_value={"headsetSettings": "global/a=1"}), \
                mock.patch.object(headset_settings.device_ws_manager, "get_connected_ids", return_value=["x", "gone"]), \
                mock.patch.object(headset_settings.device_ws_manager, "send_command", side_effect=send):
            count = asyncio.run(headset_settings.push_headset_settings())

        self.assertEqual(count, 1)
        self.assertEqual(sent[0], ("x", {"type": "command", "action": "apply_settings", "settings": "global/a=1"}))

    def test_missing_key_gets_default_but_empty_profile_is_kept(self):
        # An empty profile means "restore the headsets' own values" and must survive a save.
        self.assertEqual(config._normalize_config({})["headsetSettings"], "global/captive_portal_mode=0")
        self.assertEqual(config._normalize_config({"headsetSettings": ""})["headsetSettings"], "")
        self.assertEqual(
            config._normalize_config({"headsetSettings": " global/a=1\r\nsecure/b=2\n"})["headsetSettings"],
            "global/a=1\nsecure/b=2",
        )


if __name__ == "__main__":
    unittest.main()
