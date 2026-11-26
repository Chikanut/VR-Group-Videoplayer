import asyncio
import unittest
from pathlib import Path
from unittest import mock

from App.server import github_update as gu


class GithubUpdateTests(unittest.TestCase):
    def setUp(self):
        gu._cache.update(at=0.0, release=None, error="")
        gu._job = None

    def test_version_compare(self):
        self.assertTrue(gu.is_newer("1.10.0", "1.9.2"))
        self.assertTrue(gu.is_newer("v1.9.3", "1.9.2"))
        self.assertFalse(gu.is_newer("1.9.2", "1.9.2"))
        self.assertFalse(gu.is_newer("1.9.1 — notes", "1.9.2"))

    def test_release_parsing(self):
        release = gu._release_from_api({
            "tag_name": "1.9.3", "html_url": "https://example/r", "body": "notes",
            "assets": [{"name": gu.PLAYER_ASSET, "browser_download_url": "https://example/a.apk", "size": 5}],
        })
        self.assertEqual(release["version"], "1.9.3")
        self.assertTrue(release["hasPlayer"])
        self.assertFalse(release["hasPanel"])
        self.assertEqual(release["assets"][gu.PLAYER_ASSET]["size"], 5)

    def test_status_without_check_does_not_hit_network(self):
        with mock.patch.object(gu, "get_config", return_value={"checkUpdates": False}), \
                mock.patch.object(gu, "fetch_latest") as fetch:
            status = asyncio.run(gu.get_status())
        fetch.assert_not_called()
        self.assertIsNone(status["latest"])
        self.assertFalse(status["panelUpdateAvailable"])

    def test_start_requires_release_and_asset(self):
        self.assertFalse(gu._start("player")["success"])
        gu._cache["release"] = {"version": "1.9.3", "assets": {}}
        self.assertEqual(gu._start("player")["error"], "This release has no file for this")
        gu._cache["release"]["assets"][gu.PLAYER_ASSET] = {"url": "u", "size": 1}
        self.assertTrue(gu._start("player")["success"])
        self.assertEqual(gu._start("player")["error"], "An update is already running")

    def test_swap_script_moves_then_starts(self):
        script = gu._swap_script(Path("C:/a/VR.new.exe"), Path("C:/a/VR.exe"))
        self.assertLess(script.index("move /y"), script.index('start ""'))
        self.assertIn('"C:', script)


if __name__ == "__main__":
    unittest.main()
