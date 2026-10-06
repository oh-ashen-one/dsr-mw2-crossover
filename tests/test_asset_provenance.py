from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import unittest

from dsr_mw2.asset_provenance import inspect_export, verify
from dsr_mw2.model_candidate import read, PARTS


class ProvenanceTests(unittest.TestCase):
    def fixture(self, root, stack):
        # Generated triangle and arbitrary byte fixtures. No retail asset or
        # native extractor is used or executed by these tests.
        copies = root / "copies"
        copies.mkdir()
        fastfile = copies / "common.ff"
        fastfile.write_bytes(b"IW4 input format fixture")
        extractor = root / "extractor-fixture"
        extractor.write_bytes(b"not an executable")
        folder = root / "converted/export/model_export"
        folder.mkdir(parents=True)
        obj = folder / "weapon_beretta_lod0.obj"
        obj.write_text(
            "# Game Origin: iw4\n# Zone Origin: common\nmtllib weapon_beretta.mtl\n"
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 0 1\n"
            "usemtl mtl_weapon_beretta\nf 1/1/1 2/2/1 3/3/1\n"
        )
        obj.with_name("weapon_beretta.mtl").write_text(
            "newmtl mtl_weapon_beretta\nmap_Kd ../images/weapon_beretta_c.dds\n"
            "map_bump ../images/weapon_beretta_n.dds\n"
            "map_Ks ../images/~weapon_beretta_s-rgb&weapon_~be02a881.dds\n"
        )
        for name, value in (("WORKSPACE", root), ("COPIES", copies), ("EXTRACTOR", extractor), ("EXTRACTOR_SHA", hashlib.sha256(extractor.read_bytes()).hexdigest())):
            stack.enter_context(patch("dsr_mw2.asset_provenance." + name, value))
        stack.enter_context(patch("dsr_mw2.model_candidate.WORKSPACE", root))
        return obj, fastfile

    def test_proof_binds_source_obj_and_material_relationships(self):
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            obj, fastfile = self.fixture(Path(tmp), stack)
            proof = inspect_export(obj, fastfile)
            self.assertEqual(verify(obj, proof), proof)
            fastfile.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "provenance differs"):
                verify(obj, proof)

    def test_wrong_origin_or_texture_and_external_reference_are_refused(self):
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            obj, fastfile = self.fixture(root, stack)
            original = obj.read_text()
            obj.write_text(original.replace("Zone Origin: common", "Zone Origin: other"))
            with self.assertRaises(ValueError):
                inspect_export(obj, fastfile)
            obj.write_text(original)
            mtl = obj.with_name("weapon_beretta.mtl")
            original_mtl = mtl.read_text()
            mtl.write_text(original_mtl.replace("weapon_beretta_c.dds", "lookalike.dds"))
            with self.assertRaises(ValueError):
                inspect_export(obj, fastfile)
            mtl.unlink()
            outside = root / "outside.mtl"
            outside.write_text(original_mtl)
            mtl.symlink_to(outside)
            with self.assertRaises(ValueError):
                inspect_export(obj, fastfile)

    def test_model_candidate_hash_and_export_are_both_checked(self):
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            obj, fastfile = self.fixture(root, stack)
            model = root / "converted/model"
            file = model / PARTS
            file.parent.mkdir(parents=True)
            data = b"model binder format fixture"
            file.write_bytes(data)
            report = {
                "source": inspect_export(obj, fastfile),
                "export_obj_relative_path": str(obj.relative_to(root / "converted")),
                "output_sha256": hashlib.sha256(data).hexdigest(),
                "authentic_asset_provenance_verified": True, "activated": False, "runtime_verified": False,
            }
            (model / "model-report.json").write_text(json.dumps(report))
            self.assertEqual(read(model)[1], data)
            file.write_bytes(b"changed binder")
            with self.assertRaisesRegex(ValueError, "model binder differs"):
                read(model)

    def test_grip_export_is_bound_and_nonfinite_or_wrong_bones_are_refused(self):
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            obj, fastfile = self.fixture(Path(tmp), stack)
            bones = obj.with_suffix(".xmodel_export")
            original = '// Game Origin: IW4\n// Zone Origin: common\n'
            for index, parent, name, x in ((1, 0, "j_pistol_grip", -10.), (3, 2, "tag_flash_silenced", 2.), (5, 1, "tag_flash", -3.)):
                original += f'BONE {index} {parent} "{name}"\nBONE {index}\nOFFSET {x}, 0.0, 1.0\n'
            bones.write_text(original)
            proof = inspect_export(obj, fastfile)
            self.assertEqual(proof["attachment_points"]["grip_obj"], [-10., 1., -0.])
            bones.write_text(original.replace("-10.0", "nan"))
            with self.assertRaisesRegex(ValueError, "Invalid M9 attachment"):
                verify(obj, proof)
            bones.write_text(original.replace("j_pistol_grip", "other_grip"))
            with self.assertRaisesRegex(ValueError, "bone identity"):
                verify(obj, proof)


if __name__ == "__main__":
    unittest.main()
