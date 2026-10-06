from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import shutil
import unittest
from unittest.mock import patch

from dsr_mw2 import install_private as installer


class PrivateInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bottle, self.stock, self.candidate = installer.layout(self.root)
        self.hashes = {}
        self.records = []
        self.package = self.root / "converted/packages/m9-sidearm"
        for index, relative in enumerate(installer.STOCK_HASHES):
            original = f"original-{index}".encode()
            replacement = f"candidate-{index}".encode()
            self.hashes[relative] = hashlib.sha256(original).hexdigest()
            for folder, data in [(self.stock, original), (self.candidate, original), (self.package / "mod", replacement)]:
                p = folder / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            self.records.append({"path": "mod/" + relative, "bytes": len(replacement), "sha256": hashlib.sha256(replacement).hexdigest()})
        self.manifest = self.package / "manifest.json"
        self.loadout = json.loads((installer.WORKSPACE / "loadouts/m9-sidearm.json").read_text())
        definitions = self.root / "loadouts"
        definitions.mkdir()
        (definitions / "m9-sidearm.json").write_text(json.dumps(self.loadout))
        self.model = {"attachment": "base M9", "source": {"model_asset_name": "weapon_beretta"},
                      "authentic_asset_provenance_verified": True, "output_sha256": self.records[-1]["sha256"]}
        model_folder = self.root / "converted/dsr/m9-model-candidate"
        model_folder.mkdir(parents=True)
        (model_folder / "model-report.json").write_text(json.dumps(self.model))
        parameters = self.root / "converted/dsr/m9-sidearm/build-report.json"
        parameters.parent.mkdir()
        parameters.write_text(json.dumps({"loadout": self.loadout, "output_sha256": self.records[0]["sha256"],
                                          "source_sha256": self.hashes["param/GameParam/GameParam.parambnd.dcx"]}))
        texts = model_folder / "equipment-text/text-report.json"
        texts.parent.mkdir()
        texts.write_text(json.dumps({"model_candidate_sha256": self.model["output_sha256"],
                                     "output_sha256": self.records[1]["sha256"],
                                     "source_sha256": self.hashes["msg/ENGLISH/item.msgbnd.dcx"]}))
        self.save_manifest()
        self.patcher = patch.object(installer, "STOCK_HASHES", self.hashes)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.ownership = patch.object(installer, "bottle_processes", return_value=[])
        self.ownership.start()
        self.addCleanup(self.ownership.stop)

    def save_manifest(self):
        self.manifest.write_text(json.dumps({"authentic_mw2_model_present": True, "files": self.records,
                                            "loadout": self.loadout, "model_attachment": self.model["attachment"],
                                            "model_provenance": self.model["source"]}))

    def test_install_preserves_stock_and_repeated_install_is_idempotent(self):
        installer.install(self.root, "m9-sidearm", clone=False)
        installer.install(self.root, "m9-sidearm", clone=False)
        result = installer.inspect_install(self.root)
        self.assertTrue(result["installed"])
        self.assertTrue(result["stock_baseline_preserved"])
        self.assertFalse(result["runtime_verified"])

    def test_revision_switch_preserves_legacy_and_chooser_keeps_revision(self):
        revised = self.root / 'converted/packages/upright-v1/m9-sidearm'
        shutil.copytree(self.package, revised)
        model = self.root / 'converted/dsr/m9-upright-v1/base'
        shutil.copytree(self.root / 'converted/dsr/m9-model-candidate', model)
        relative = 'parts/WP_A_1401.partsbnd.dcx'
        payload = b'upright model'
        digest = hashlib.sha256(payload).hexdigest()
        (revised / 'mod' / relative).write_bytes(payload)
        manifest = json.loads((revised / 'manifest.json').read_text())
        manifest['files'][-1].update(bytes=len(payload), sha256=digest)
        (revised / 'manifest.json').write_text(json.dumps(manifest))
        record = json.loads((model / 'model-report.json').read_text())
        record['output_sha256'] = digest
        (model / 'model-report.json').write_text(json.dumps(record))
        text = json.loads((model / 'equipment-text/text-report.json').read_text())
        text['model_candidate_sha256'] = digest
        (model / 'equipment-text/text-report.json').write_text(json.dumps(text))
        installer.install(self.root, 'm9-sidearm', clone=False)
        installer.install(self.root, 'm9-sidearm', clone=False, revision='upright-v1')
        installer.install(self.root, 'm9-sidearm', clone=False)
        self.assertEqual(installer.inspect_install(self.root)['revision'], 'upright-v1')
        self.assertEqual((self.candidate / relative).read_bytes(), payload)
        installer.install(self.root, 'm9-sidearm', clone=False, revision='legacy')
        self.assertEqual((self.candidate / relative).read_bytes(), b'candidate-2')
        self.assertEqual({p: installer.sha(self.stock / p) for p in self.hashes}, self.hashes)

    def test_unknown_revision_is_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'revision'):
            installer.install(self.root, 'm9-sidearm', clone=False, revision='../outside')
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)

    def test_winding_revision_keeps_its_records_and_can_restore_legacy(self):
        revised = self.root / 'converted/packages/winding-v2/m9-sidearm'
        shutil.copytree(self.package, revised)
        model = self.root / 'converted/dsr/m9-winding-v2/base'
        shutil.copytree(self.root / 'converted/dsr/m9-model-candidate', model)
        installer.install(self.root, 'm9-sidearm', clone=False, revision='winding-v2')
        installer.install(self.root, 'm9-sidearm', clone=False)
        self.assertEqual(installer.inspect_install(self.root)['revision'], 'winding-v2')
        self.assertEqual({p: installer.sha(self.stock / p) for p in self.hashes}, self.hashes)
        (model / 'model-report.json').write_text('{}')
        self.assertFalse(installer.inspect_install(self.root)['installed'])
        installer.install(self.root, 'm9-sidearm', clone=False, revision='legacy')
        self.assertTrue(installer.inspect_install(self.root)['installed'])

    def test_refuses_changed_candidate_without_overwriting_it(self):
        relative = next(iter(self.hashes))
        target = self.candidate / relative
        target.write_bytes(b"someone else's work")
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual(target.read_bytes(), b"someone else's work")

    def test_rejects_extra_payload_before_any_write(self):
        self.records.append({"path": "../../outside", "sha256": "fake", "bytes": 0})
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "exactly"):
            installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)

    def test_rejects_external_symlink(self):
        relative = next(iter(self.hashes))
        p = self.candidate / relative
        outside = self.root / "outside"
        outside.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual(installer.sha(outside), self.hashes[relative])

    def test_rollback_on_mid_install_write_failure(self):
        real_write = installer.atomic_write
        calls = 0

        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated full disk")
            real_write(path, data)

        with patch.object(installer, "atomic_write", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "full disk"):
                installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)
        self.assertFalse((self.bottle / ".dsr-mw2-native-install.json").exists())

    def test_receipt_cannot_bless_unrelated_changed_bytes(self):
        installer.install(self.root, "m9-sidearm", clone=False)
        state = self.bottle / ".dsr-mw2-native-install.json"
        report = json.loads(state.read_text())
        relative = next(iter(self.hashes))
        (self.candidate / relative).write_bytes(b"wrong native data")
        report["installed_hashes"][relative] = installer.sha(self.candidate / relative)
        state.write_text(json.dumps(report))
        check = installer.inspect_install(self.root)
        self.assertFalse(check["installed"])
        self.assertIn("differs from the selected package", check["error"])

    def test_mislabeled_loadout_is_refused_before_writes(self):
        self.loadout["physical_damage"] = 70
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "identity"):
            installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)

    def test_wrong_model_cannot_pass_with_updated_package_hash(self):
        record = self.records[-1]
        payload = b"a different attachment"
        (self.package / record["path"]).write_bytes(payload)
        record.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "selected setup"):
            installer.checked_package(self.root, "m9-sidearm")

    def test_wrong_parameter_payload_cannot_pass_with_updated_manifest_hash(self):
        record = self.records[0]
        payload = b"parameters from another preset"
        (self.package / record["path"]).write_bytes(payload)
        record.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "selected setup"):
            installer.checked_package(self.root, "m9-sidearm")

    def test_corrupt_or_external_receipt_fails_as_a_report(self):
        state = self.bottle / ".dsr-mw2-native-install.json"
        for payload in ("{broken", "null", "{}", '{"installed_hashes": {}}'):
            state.write_text(payload)
            result = installer.inspect_install(self.root)
            self.assertFalse(result["installed"])
            self.assertIn("error", result)
        state.unlink()
        state.symlink_to(self.manifest)
        self.assertIn("escapes", installer.inspect_install(self.root)["error"])

    def test_direct_installer_refuses_a_live_private_process(self):
        with patch.object(installer, "bottle_processes", return_value=[999]):
            with self.assertRaisesRegex(ValueError, "process owns"):
                installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)

    def test_installer_respects_launcher_session_lock(self):
        with (self.bottle / ".dsr-mw2-session.lock").open("a+") as lock:
            installer.fcntl.flock(lock, installer.fcntl.LOCK_EX | installer.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                installer.install(self.root, "m9-sidearm", clone=False)
        self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)

    def test_bad_manifest_shapes_fail_cleanly_before_writes(self):
        good = json.loads(self.manifest.read_text())
        for payload in (None, [], {**good, "files": None}, {**good, "files": [{"path": []}]}):
            self.manifest.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                installer.install(self.root, "m9-sidearm", clone=False)
            self.assertEqual({p: installer.sha(self.candidate / p) for p in self.hashes}, self.hashes)


if __name__ == "__main__":
    unittest.main()
