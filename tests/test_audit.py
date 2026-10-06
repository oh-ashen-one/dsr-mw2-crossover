from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from dsr_mw2.audit import inspect


class AuditTests(unittest.TestCase):
    def test_refuses_unfinished_dsr_and_home_linked_documents(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            steamapps = root / "steamapps"
            steamapps.mkdir()
            (steamapps / "appmanifest_570940.acf").write_text(
                '"appid" "570940"\n"name" "DARK SOULS REMASTERED"\n"StateFlags" "2"\n'
            )
            (steamapps / "appmanifest_10180.acf").write_text(
                '"appid" "10180"\n"name" "Call of Duty"\n"StateFlags" "4"\n'
            )
            mw2 = steamapps / "common" / "Call of Duty Modern Warfare 2"
            mw2.mkdir(parents=True)
            (mw2 / "iw4sp.exe").touch()
            home_docs = root / "outside" / "Documents"
            home_docs.mkdir(parents=True)
            bottle_docs = root / "workspace" / "bottle" / "drive_c" / "users" / "crossover" / "Documents"
            bottle_docs.parent.mkdir(parents=True)
            bottle_docs.symlink_to(home_docs, target_is_directory=True)
            result = inspect(steamapps, root / "workspace" / "bottle", root / "workspace")
            self.assertFalse(result["games"]["dsr"]["installed"])
            self.assertTrue(result["games"]["mw2_2009"]["installed"])
            self.assertFalse(result["profile"]["filesystem_isolated"])
            self.assertFalse(result["safe_for_runtime_investigation"])

    def test_ready_only_with_both_exes_and_local_documents(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            steamapps = root / "steamapps"
            for appid, directory, exe in (
                ("570940", "DARK SOULS REMASTERED", "DarkSoulsRemastered.exe"),
                ("10180", "Call of Duty Modern Warfare 2", "iw4sp.exe"),
            ):
                (steamapps / f"appmanifest_{appid}.acf").parent.mkdir(exist_ok=True)
                (steamapps / f"appmanifest_{appid}.acf").write_text(
                    f'"appid" "{appid}"\n"installdir" "{directory}"\n"StateFlags" "4"\n'
                )
                game = steamapps / "common" / directory
                game.mkdir(parents=True)
                (game / exe).touch()
            workspace = root / "workspace"
            bottle = workspace / "bottle"
            (bottle / "drive_c" / "users" / "crossover" / "Documents").mkdir(parents=True)
            (bottle / "dosdevices").mkdir()
            (bottle / "dosdevices" / "c:").symlink_to("../drive_c", target_is_directory=True)
            result = inspect(steamapps, bottle, workspace)
            self.assertTrue(result["safe_for_runtime_investigation"])
            self.assertFalse(result["profile"]["game_save_write_verified"])
            self.assertFalse(result["playable_verified"])
            (bottle / ".dsr-mw2-isolation.json").write_text(json.dumps({
                "external_mapping_recreated": True, "drive_mapping_persistence_verified": False,
            }))
            self.assertFalse(inspect(steamapps, bottle, workspace)["safe_for_runtime_investigation"])

    def test_local_documents_do_not_hide_host_drive_access(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            bottle = workspace / "bottle"
            (bottle / "drive_c/users/crossover/Documents").mkdir(parents=True)
            (bottle / "dosdevices").mkdir()
            (bottle / "dosdevices/z:").symlink_to("/", target_is_directory=True)
            result = inspect(Path(tmp) / "steamapps", bottle, workspace)
            self.assertFalse(result["profile"]["filesystem_isolated"])
            self.assertIn("z:", result["profile"]["external_drive_mappings"])
            self.assertFalse(result["profile"]["os_sandbox_verified"])

    def test_shared_bottle_cannot_pass_with_external_documents_linked_in(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            docs = workspace / "Documents"
            docs.mkdir(parents=True)
            bottle = root / "shared" / "bottle"
            link = bottle / "drive_c" / "users" / "crossover" / "Documents"
            link.parent.mkdir(parents=True)
            link.symlink_to(docs, target_is_directory=True)
            result = inspect(root / "steamapps", bottle, workspace)
            self.assertFalse(result["profile"]["bottle_is_task_owned"])
            self.assertFalse(result["profile"]["filesystem_isolated"])


if __name__ == "__main__":
    unittest.main()
