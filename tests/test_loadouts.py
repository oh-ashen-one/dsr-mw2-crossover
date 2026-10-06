from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from dsr_mw2.loadouts import load


class LoadoutTests(unittest.TestCase):
    def test_rejects_unbounded_collision_speed_and_path_names(self):
        base = json.loads((Path(__file__).resolve().parents[1] / "loadouts/m9-sidearm.json").read_text())
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "loadout.json"
            for field, value in (("projectile_speed", 100000), ("name", "../outside"), ("ammo_count", True), ("starter_classes", [2000, 2000])):
                data = dict(base)
                data[field] = value
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load(path)
