from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from dsr_mw2 import runtime_paths


class RuntimePathTests(unittest.TestCase):
    def test_location_receipt_cannot_redirect_to_another_profile(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "profiles").mkdir()
            receipt = root / "profiles/runtime-location.json"
            receipt.write_text(json.dumps({"bottle": str(root / "some-other-bottle")}))
            with patch.object(runtime_paths, "WORKSPACE", root):
                with self.assertRaisesRegex(ValueError, "fixed private profile"):
                    runtime_paths.bottle_path(root)

    def test_fixed_task_location_is_accepted_without_following_redirects(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "workspace"
            local = Path(tmp).resolve() / "local-runtime"
            local.mkdir()
            (root / "profiles").mkdir(parents=True)
            (root / "profiles/runtime-location.json").write_text(json.dumps({"bottle": str(local)}))
            with patch.object(runtime_paths, "WORKSPACE", root), patch.object(runtime_paths, "LOCAL_BOTTLE", local):
                self.assertEqual(runtime_paths.bottle_path(root), local)


if __name__ == "__main__":
    unittest.main()
