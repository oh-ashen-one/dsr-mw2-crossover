import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dsr_mw2.profile import save_path_guard


class SavePathTests(unittest.TestCase):
    def fixture(self, root, personal=r"C:\users\crossover\Documents"):
        sections = [
            (r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders", personal, ""),
            (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", r"%USERPROFILE%\Documents", "str(2):"),
        ]
        (root / "user.reg").write_text("\n".join(
            "[" + name.replace("\\", "\\\\") + "]\n\"Personal\"=" + kind + json.dumps(value)
            for name, value, kind in sections))
        save = root / "drive_c/users/crossover/Documents/NBGI/DARK SOULS REMASTERED"
        save.mkdir(parents=True)
        return save

    def test_verified_selectors_and_local_saves_pass_without_writes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            save = self.fixture(root)
            sample = save / "disposable.sl2"
            sample.write_bytes(b"synthetic save fixture")
            self.assertEqual(save_path_guard(root), [])
            self.assertEqual(sample.read_bytes(), b"synthetic save fixture")

    def test_local_documents_cannot_hide_registry_redirect(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, r"Z:\Users\owner\Documents")
            self.assertTrue(save_path_guard(root))

    def test_per_account_or_file_redirect_is_refused(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            save = self.fixture(root)
            external = root / "external-saves"
            external.mkdir()
            (save / "account-fixture").symlink_to(external, target_is_directory=True)
            self.assertTrue(save_path_guard(root))

    def test_missing_registry_selector_does_not_guess_windows_defaults(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "user.reg").write_text("WINE REGISTRY Version 2\n")
            self.assertTrue(save_path_guard(root))
