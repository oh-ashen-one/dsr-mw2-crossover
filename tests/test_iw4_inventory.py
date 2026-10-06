from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from dsr_mw2.iw4_inventory import inventory


class InventoryTests(unittest.TestCase):
    def test_lists_names_without_exporting_content(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with ZipFile(directory / "iw_03.iwd", "w") as archive:
                archive.writestr("images/weapon_m9beretta.iwi", b"retail-fixture")
                archive.writestr("images/other.iwi", b"other")
            matches = inventory(directory)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["entry"], "images/weapon_m9beretta.iwi")
            self.assertEqual(sorted(path.name for path in directory.iterdir()), ["iw_03.iwd"])


if __name__ == "__main__":
    unittest.main()
