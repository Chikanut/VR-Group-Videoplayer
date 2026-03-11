import unittest
from unittest.mock import patch

from App.server import config


class ConfigAdbToggleTests(unittest.TestCase):
    def test_is_adb_enabled_respects_runtime_toggle(self):
        with config._config_lock:
            original = dict(config._config)
            config._config = {"adbEnabled": True}
        try:
            with patch.object(config, "ADB_AVAILABLE", True):
                self.assertTrue(config.is_adb_enabled())
                with config._config_lock:
                    config._config["adbEnabled"] = False
                self.assertFalse(config.is_adb_enabled())
        finally:
            with config._config_lock:
                config._config = original

    def test_update_config_forces_adb_enabled_false_when_unavailable(self):
        with patch.object(config, "ADB_AVAILABLE", False):
            config.load_config()
            updated = config.update_config({"adbEnabled": True})
            self.assertFalse(updated["adbEnabled"])


if __name__ == "__main__":
    unittest.main()
