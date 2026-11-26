import asyncio
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from App.server import config as cfg
from App.server import environment as env_store
from App.server import main
from App.server.models import ConfigModel


def _png(width=2, height=1):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0" * (width * 4 + 1) * height)) + chunk(b"IEND", b"")


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sent = []

        async def send(device_id, command):
            self.sent.append((device_id, command))
            return True

        self.patches = [
            patch.object(cfg, "CONFIG_PATH", Path(self.tmp.name) / "config.json"),
            patch.object(cfg, "_config", cfg._normalize_config({})),
            patch.object(env_store.device_ws_manager, "get_connected_ids", return_value=["h1"]),
            patch.object(env_store.device_ws_manager, "send_command", side_effect=send),
            patch("App.server.websocket_manager.ws_manager.broadcast", new=AsyncMock()),
            patch.object(main, "refresh_all_requirements", new=AsyncMock()),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _upload(self, data):
        request = SimpleNamespace(body=AsyncMock(return_value=data))
        return asyncio.run(main.upload_environment_logo(request))

    def test_png_checks(self):
        self.assertIsNone(env_store.validate_png(_png()))
        self.assertTrue(env_store.validate_png(b"GIF89a" + b"\0" * 30))
        self.assertIn("4096", env_store.validate_png(_png(5000, 10)))

    def test_upload_sends_the_picture_to_the_headsets(self):
        result = self._upload(_png())

        env = result["environment"]
        self.assertTrue(env["custom"])
        self.assertEqual(len(env["logoSha256"]), 64)
        self.assertTrue(env_store.logo_path().is_file())
        command = self.sent[-1][1]
        self.assertEqual(command["action"], "set_environment")
        self.assertEqual(command["logoUrl"], env_store.LOGO_URL)
        self.assertEqual(command["environment"]["logoSha256"], env["logoSha256"])

    def test_rejected_upload_changes_nothing(self):
        response = self._upload(b"not a png")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(env_store.logo_path().exists())
        self.assertEqual(self.sent, [])

    def test_stale_settings_save_keeps_the_picture(self):
        sha = self._upload(_png())["environment"]["logoSha256"]
        stale = ConfigModel(environment={"custom": True, "background": "#112233", "logoSha256": ""})

        new_config = asyncio.run(main.update_config_endpoint(stale))

        self.assertEqual(new_config["environment"]["logoSha256"], sha)
        self.assertEqual(new_config["environment"]["background"], "#112233")
        self.assertEqual(self.sent[-1][1]["environment"]["background"], "#112233")

    def test_reset_restores_the_default_and_deletes_the_picture(self):
        self._upload(_png())

        result = asyncio.run(main.reset_environment())

        self.assertFalse(result["environment"]["custom"])
        self.assertFalse(env_store.logo_path().exists())
        self.assertFalse(self.sent[-1][1]["environment"]["custom"])
        self.assertEqual(self.sent[-1][1]["logoUrl"], "")

    def test_bad_values_are_normalized(self):
        env = env_store.normalize_environment({"custom": 1, "background": "red", "logoPosition": [1, "x"], "logoSize": -3})
        self.assertEqual(env["background"], env_store.DEFAULT_ENVIRONMENT["background"])
        self.assertEqual(env["logoPosition"], env_store.DEFAULT_ENVIRONMENT["logoPosition"])
        self.assertEqual(env["logoSize"], 0.05)


if __name__ == "__main__":
    unittest.main()
