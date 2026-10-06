from pathlib import Path
import tempfile
import unittest

from dsr_mw2.steam_mode import configure, mode_text


class SteamModeTests(unittest.TestCase):
    EXAMPLE = '"users"\r\n{\r\n"test-account" { "RememberPassword" "1"\r\n"WantsOfflineMode" "0"\r\n"SkipOfflineModeWarning" "0" }\r\n}\r\n'

    def test_only_mode_flags_change_and_round_trip(self):
        changed = mode_text(self.EXAMPLE, True)
        self.assertIn('"RememberPassword" "1"', changed)
        self.assertIn('"WantsOfflineMode" "1"', changed)
        self.assertEqual(mode_text(changed, False), self.EXAMPLE)

    def test_ambiguous_accounts_are_preserved(self):
        with self.assertRaises(ValueError):
            mode_text(self.EXAMPLE * 2, True)
        with self.assertRaises(ValueError):
            mode_text('"users" {}', True)

    def test_atomic_file_update_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "loginusers.vdf"
            path.write_bytes(self.EXAMPLE.encode())
            configure(path, True)
            self.assertEqual(path.read_bytes(), mode_text(self.EXAMPLE, True).encode())
            self.assertEqual(list(Path(temp).iterdir()), [path])
