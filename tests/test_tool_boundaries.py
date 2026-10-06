from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from dsr_mw2.soulstruct_tools import configure, COMMIT
from dsr_mw2.stage_runtime import write_local


class ToolBoundaryTests(unittest.TestCase):
    def test_unadapted_package_is_refused_before_soulstruct_import(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tooling-local").mkdir()
            (root / "tooling-local/soulstruct-install.json").write_text(json.dumps({"commit": COMMIT, "version": "2.6.0"}))
            config = root / ".venv/soulstruct/config.py"
            config.parent.mkdir(parents=True)
            config.write_text('_SOULSTRUCT_APPDATA = Path("~/AppData/Roaming/soulstruct").expanduser()')
            class Distribution:
                version = "2.6.0"
                def locate_file(self, _):
                    return config
            with patch("dsr_mw2.soulstruct_tools.WORKSPACE", root), patch("importlib.metadata.distribution", return_value=Distribution()):
                with self.assertRaisesRegex(ValueError, "adapter missing"):
                    configure()

    def test_stager_preserves_differing_files_and_refuses_external_links(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bottle = root / "bottle"
            bottle.mkdir()
            file = bottle / "existing"
            file.write_bytes(b"preserve")
            outside = root / "outside"
            outside.mkdir()
            (bottle / "link").symlink_to(outside, target_is_directory=True)
            with patch("dsr_mw2.stage_runtime.BOTTLE", bottle):
                with self.assertRaises(ValueError):
                    write_local(file, b"replacement")
                with self.assertRaises(ValueError):
                    write_local(bottle / "link/new", b"blocked")
            self.assertEqual(file.read_bytes(), b"preserve")
            self.assertFalse((outside / "new").exists())
