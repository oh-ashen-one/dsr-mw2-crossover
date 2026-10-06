from pathlib import Path
import tomllib
import unittest


class OfflineConfigTests(unittest.TestCase):
    def test_external_code_and_crash_uploads_are_disabled(self):
        config = tomllib.loads((Path(__file__).parents[1] / "config_dsr_offline.toml").read_text())
        self.assertFalse(config["modengine"]["crash_reporting"])
        self.assertFalse(config["modengine"]["external_dll_discovery"])
        self.assertEqual(config["modengine"]["external_dlls"], [])
        self.assertFalse(config["extension"]["scylla_hide"]["enabled"])
        self.assertTrue(config["extension"]["mod_loader"]["enabled"])
        self.assertEqual(config["extension"]["mod_loader"]["mods"][0]["path"], "mod")


if __name__ == "__main__":
    unittest.main()
