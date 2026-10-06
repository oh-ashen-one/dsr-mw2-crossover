import math
import unittest
from dsr_mw2.animation_pose import (Transform, compose, inverse, multiply, quaternion_from_columns,
    read_rig, relative, retarget_rotation, rotate, sample_track, slerp)
from dsr_mw2.xanim import Track


class PoseTests(unittest.TestCase):
    def close(self, a, b):
        self.assertEqual(len(a), len(b))
        for left, right in zip(a, b): self.assertAlmostEqual(left, right, places=6)

    def test_column_basis_direction_and_inverse(self):
        q = quaternion_from_columns(((0, 1, 0), (-1, 0, 0), (0, 0, 1)))
        self.close(rotate(q, (1, 0, 0)), (0, 1, 0))
        self.close(rotate(inverse(q), (0, 1, 0)), (1, 0, 0))
        self.close(multiply(q, inverse(q)), (0, 0, 0, 1))

    def test_rejects_reflection_scale_nonfinite(self):
        for matrix in (((-1,0,0),(0,1,0),(0,0,1)), ((2,0,0),(0,1,0),(0,0,1)), ((math.nan,0,0),(0,1,0),(0,0,1))):
            with self.assertRaises(ValueError): quaternion_from_columns(matrix)
        with self.assertRaises(ValueError): quaternion_from_columns(((1,0,0),(0,1,0),(0,0,1)), tolerance=.1)

    def test_half_turn_branches(self):
        for axis in range(3):
            columns = tuple(tuple((1 if i == axis else -1) if i == j else 0 for j in range(3)) for i in range(3))
            q = quaternion_from_columns(columns)
            self.assertAlmostEqual(abs(q[axis]), 1)
            self.assertAlmostEqual(q[3], 0)

    def test_slerp_shortest_arc_and_midpoint(self):
        self.close(slerp((0,0,0,1), (0,0,0,-1), .5), (0,0,0,1))
        q = slerp((0,0,0,1), (0,0,1,0), .5)
        self.close(rotate(q, (1,0,0)), (0,1,0))
        with self.assertRaises(ValueError): slerp((0,0,0,0), (0,0,0,1), .5)

    def test_global_to_local_recomposes(self):
        a = Transform((0,0,math.sqrt(.5),math.sqrt(.5)), (10,20,30))
        b = Transform((0,0,0,1), (11,23,35))
        c = compose(a, relative(a, b))
        self.close(c.rotation, b.rotation); self.close(c.translation, b.translation)

    def test_sparse_key_sampling_and_absence(self):
        t = Track((0, 10), ((0, 0, 0), (10, 20, 30)))
        self.close(sample_track(t, 2.5, rotation=False), (2.5,5,7.5))
        self.close(sample_track(t, 30, rotation=False), (10,20,30))
        self.assertIsNone(sample_track(Track((), ()), 0, rotation=True))
        with self.assertRaises(ValueError): sample_track(Track((0,0), ((0,0,0),(1,1,1))), 0, rotation=False)
        with self.assertRaises(ValueError): sample_track(t, math.nan, rotation=False)

    def test_rest_pose_is_preserved_by_retarget(self):
        src = (0,0,math.sqrt(.5),math.sqrt(.5))
        target = (0,math.sqrt(.5),0,math.sqrt(.5))
        self.close(retarget_rotation(src, src, target, (1,0,0,0)), target)

    def test_explicit_basis_maps_twist_axis(self):
        # +90 around Z maps X-source rotation to Y-target rotation.
        q = retarget_rotation((0,0,0,1), (1,0,0,0), (0,0,0,1), (0,0,math.sqrt(.5),math.sqrt(.5)))
        self.close(rotate(q, (0,0,1)), (0,0,-1))
        self.assertAlmostEqual(abs(q[1]), 1)

    def rig(self):
        return 'MODEL\nVERSION 6\nNUMBONES 2\nBONE 0 -1 "root"\nBONE 1 0 "child"\n' + ''.join(
            f'BONE {i}\nOFFSET {i}, 0, 0\nSCALE 1, 1, 1\nX 1, 0, 0\nY 0, 1, 0\nZ 0, 0, 1\n' for i in range(2))

    def test_rig_hierarchy_and_truncation(self):
        bones = read_rig(self.rig())
        self.assertEqual(bones[1].parent, 0)
        self.close(bones[1].local_bind.translation, (1,0,0))
        with self.assertRaises(ValueError): read_rig(self.rig().replace('BONE 1 0 "child"', 'BONE 1 1 "child"'))
        with self.assertRaises(ValueError): read_rig(self.rig().replace('SCALE 1, 1, 1', 'SCALE 2, 1, 1'))
        with self.assertRaises(ValueError): read_rig(self.rig()[:-30])


if __name__ == '__main__': unittest.main()
