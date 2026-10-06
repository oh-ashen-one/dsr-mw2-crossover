import unittest
from dsr_mw2.obj_geometry import parse

TRIANGLE = """mtllib ../../unread.mtl
v 0 0 0
v 1 0 0
v 0 1 0
vt 0 0
vt 1 0
vt 0 1
vn 0 0 1
usemtl mc/mtl_weapon_beretta
f 1/1/1 2/2/1 3/3/1
"""


class ObjTests(unittest.TestCase):
    def test_parses_indexed_triangle_without_opening_mtl(self):
        data = parse(TRIANGLE)
        self.assertEqual(len(data["groups"]["mc/mtl_weapon_beretta"]), 1)

    def test_rejects_invalid_index_and_nonfinite_or_nontriangle_geometry(self):
        for text in (TRIANGLE.replace("3/3/1", "4/3/1"), TRIANGLE.replace("v 0 0 0", "v nan 0 0"), TRIANGLE.replace("3/3/1", "3/3/1 1/1/1")):
            with self.assertRaises(ValueError):
                parse(text)
