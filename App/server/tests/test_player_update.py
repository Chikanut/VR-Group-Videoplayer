import asyncio
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from App.server import player_update


class PlayerUpdateTests(unittest.TestCase):
    def setUp(self):
        handle, self.apk = tempfile.mkstemp(suffix=".apk")
        os.write(handle, b"fake apk bytes")
        os.close(handle)
        self.addCleanup(os.remove, self.apk)

    def _run(self, apk_path, connected):
        sent = []

        async def send_command(device_id, command):
            sent.append((device_id, command))
            return device_id != "broken"

        with mock.patch.object(player_update, "get_config", return_value={"playerApkPath": apk_path}), \
                mock.patch.object(player_update.device_ws_manager, "get_connected_ids", return_value=connected), \
                mock.patch.object(player_update.device_ws_manager, "send_command", side_effect=send_command):
            return asyncio.run(player_update.update_players()), sent

    def test_sends_update_with_apk_sha_to_connected_devices(self):
        result, sent = self._run(f'"{self.apk}"', ["a", "broken"])

        expected_sha = hashlib.sha256(b"fake apk bytes").hexdigest()
        self.assertTrue(result["success"])
        self.assertEqual(result["sha256"], expected_sha)
        self.assertEqual(result["deviceIds"], ["a"])
        self.assertEqual(sent[0][1], {
            "type": "command", "action": "update", "url": "/api/player/apk", "sha256": expected_sha,
        })

    def test_missing_apk_sends_nothing(self):
        result, sent = self._run(self.apk + ".missing", ["a"])

        self.assertFalse(result["success"])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
