"""python -m unittest tools.test_quest_deploy (з кореня репозиторію)."""
import unittest

from tools import quest_deploy as qd


class FakeADB(qd.ADB):
    def __init__(self, installed=True, networks=""):
        super().__init__("adb")
        self.calls = []
        self.installed = installed
        self.networks = networks

    def run(self, *args, serial=None, timeout=30):
        self.calls.append(" ".join(args))
        joined = " ".join(args)
        if joined.startswith("shell pm list packages"):
            return 0, f"package:{qd.PLAYER_PACKAGE}" if self.installed else "", ""
        if joined.startswith("uninstall"):
            return 0, "Success", ""
        if joined.startswith("shell pm enable"):
            return 0, f"Package {args[-1]} new state: enabled", ""
        if joined == "shell cmd wifi list-networks":
            return 0, self.networks, ""
        return 0, "", ""


class RollbackTests(unittest.TestCase):
    def test_default_rollback_undoes_setup_player(self):
        adb = FakeADB()
        steps = adb.rollback("S1", qd.PLAYER_PACKAGE)
        self.assertTrue(all(ok for ok, _ in steps), steps)
        calls = adb.calls
        self.assertIn(f"uninstall {qd.PLAYER_PACKAGE}", calls)
        self.assertIn(f"shell pm clear {qd.PLAYER_PACKAGE}", calls)  # before uninstall: stale /sdcard data
        for package in qd.META_BLOCKING_DIALOGS:
            self.assertIn(f"shell pm enable {package}", calls)
        self.assertIn("shell settings delete global captive_portal_mode", calls)
        self.assertFalse(any("rm -f /sdcard/Movies" in c for c in calls))
        self.assertFalse(any("forget-network" in c for c in calls))

    def test_optional_steps(self):
        networks = ("Network Id      SSID                         Security type\n"
                    "0               Class AP                     wpa2-psk\n"
                    "1               Other                        open\n")
        adb = FakeADB(installed=False, networks=networks)
        steps = adb.rollback("S1", qd.PLAYER_PACKAGE, video_paths=["/sdcard/Movies/a.mp4"], wifi_ssids=["Class AP"])
        self.assertIn("shell rm -f /sdcard/Movies/a.mp4", adb.calls)
        self.assertIn("shell cmd wifi forget-network 0", adb.calls)
        self.assertNotIn("shell cmd wifi forget-network 1", adb.calls)
        self.assertNotIn(f"uninstall {qd.PLAYER_PACKAGE}", adb.calls)
        self.assertTrue(any("Class AP" in text for _, text in steps))

    def test_swap_script_and_versions(self):
        self.assertGreater(qd.parse_version("1.10.0"), qd.parse_version("1.9.2"))
        script = qd.swap_script("C:/x/QDM.new.exe", "C:/x/QDM.exe")
        self.assertLess(script.index("move /y"), script.index('start ""'))


if __name__ == "__main__":
    unittest.main()
