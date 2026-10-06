from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import tomllib
import unittest

from dsr_mw2.package_loadout import package, PARAM, TEXT
from dsr_mw2.status import package_status

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def setup_candidate(self, root):
        preset = json.loads((ROOT / "loadouts/m9-sidearm.json").read_text())
        path = root / "loadout.json"
        path.write_text(json.dumps(preset))
        (root / "config_dsr_offline.toml").write_text((ROOT / "config_dsr_offline.toml").read_text())
        source = root / "converted/dsr/m9-sidearm"
        parameter = source / "mod" / PARAM
        parameter.parent.mkdir(parents=True)
        parameter.write_bytes(b"format fixture, not retail data")
        (source / "build-report.json").write_text(json.dumps({
            "loadout": preset, "output_sha256": hashlib.sha256(parameter.read_bytes()).hexdigest(),
            "activated": False, "runtime_verified": False,
        }))
        text_source = root / "converted/dsr/prototype-text"
        text = text_source / TEXT
        text.parent.mkdir(parents=True)
        text.write_bytes(b"text fixture")
        (text_source / "text-report.json").write_text(json.dumps({
            "output_sha256": hashlib.sha256(text.read_bytes()).hexdigest(), "label": "prototype",
        }))
        return path, parameter

    def test_package_keeps_mod_disabled_and_source_unchanged(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preset, source = self.setup_candidate(root)
            original = source.read_bytes()
            with patch("dsr_mw2.package_loadout.WORKSPACE", root):
                report = package(preset)
            output = root / "converted/packages/m9-sidearm"
            config = tomllib.loads((output / "config_dsr_candidate.toml").read_text())
            self.assertFalse(config["extension"]["mod_loader"]["mods"][0]["enabled"])
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(report["activated"])

    def test_tampered_data_and_external_package_paths_are_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preset, source = self.setup_candidate(root)
            source.write_bytes(b"tampered")
            with patch("dsr_mw2.package_loadout.WORKSPACE", root):
                with self.assertRaises(ValueError):
                    package(preset)
                with self.assertRaises(ValueError):
                    package(preset, root / "outside")
            self.assertFalse((root / "converted/packages/m9-sidearm").exists())

    def test_setup_check_detects_changed_bytes_and_enabled_overrides(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preset, _ = self.setup_candidate(root)
            with patch("dsr_mw2.package_loadout.WORKSPACE", root):
                package(preset)
            output = root / "converted/packages/m9-sidearm"
            before = package_status(output)
            self.assertTrue(before["files_hash_verified"])
            self.assertTrue(before["config_disabled"])
            (output / "mod" / PARAM).write_bytes(b"changed after packaging")
            config = output / "config_dsr_candidate.toml"
            config.write_text(config.read_text().replace("enabled = false, name", "enabled = true, name"))
            after = package_status(output)
            self.assertFalse(after["files_hash_verified"])
            self.assertFalse(after["config_disabled"])

    def test_metadata_symlink_is_refused_before_package_writes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preset, _ = self.setup_candidate(root)
            output = root / "converted/packages/m9-sidearm"
            output.mkdir(parents=True)
            outside = root / "preserve.txt"
            outside.write_text("untouched")
            (output / "manifest.json").symlink_to(outside)
            with patch("dsr_mw2.package_loadout.WORKSPACE", root):
                with self.assertRaisesRegex(ValueError, "external symlink"):
                    package(preset)
            self.assertEqual(outside.read_text(), "untouched")
            self.assertFalse((output / "mod").exists())

    def test_model_package_requires_matching_text_and_keeps_override_disabled(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preset, _ = self.setup_candidate(root)
            from dsr_mw2.model_candidate import PARTS
            model_bytes = b"generated model packaging fixture, not a retail asset"
            model_report = {"output_sha256": hashlib.sha256(model_bytes).hexdigest(), "source": {"fixture": True}}
            text_root = root / "converted/model/equipment-text"
            text = text_root / TEXT
            text.parent.mkdir(parents=True)
            text.write_bytes(b"model label fixture")
            text_report = {"output_sha256": hashlib.sha256(text.read_bytes()).hexdigest(), "label": "prototype", "authentic_gun_mesh_present": True, "model_candidate_sha256": "wrong"}
            report_file = text_root / "text-report.json"
            report_file.write_text(json.dumps(text_report))
            with patch("dsr_mw2.package_loadout.WORKSPACE", root), patch("dsr_mw2.package_loadout.read_model", return_value=(model_report, model_bytes)):
                with self.assertRaisesRegex(ValueError, "text does not match"):
                    package(preset, model=root / "converted/model")
                text_report["model_candidate_sha256"] = model_report["output_sha256"]
                report_file.write_text(json.dumps(text_report))
                packaged = package(preset, model=root / "converted/model")
            output = root / "converted/packages/m9-sidearm"
            self.assertEqual((output / "mod" / PARTS).read_bytes(), model_bytes)
            self.assertFalse(packaged["config_mod_enabled"])
            self.assertFalse(packaged["runtime_verified"])
            self.assertFalse(packaged["mechanics_only"])
