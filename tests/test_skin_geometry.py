import math
import unittest

from dsr_mw2.animation_pose import Transform, compose
from dsr_mw2.skin_geometry import IDENTITY, dummy_position, point, skin, world_transforms


class SkinGeometryTests(unittest.TestCase):
    def close(self, left, right):
        for a, b in zip(left, right, strict=True):
            self.assertAlmostEqual(a, b, places=7)

    def test_bind_inverse_and_parent_rotation_with_real_vertex_blend(self):
        q = (0, 0, math.sqrt(.5), math.sqrt(.5))
        binds = world_transforms((-1, 0), (IDENTITY, Transform(q, (2, 0, 0))))
        posed = world_transforms((-1, 0), (IDENTITY, Transform(q, (2, 3, 0))))
        vertices = ((3, 1, 0),)
        weights = (((0, .25), (1, .75)),)
        self.close(skin(vertices, weights, binds, binds)[0], vertices[0])
        self.close(skin(vertices, weights, binds, posed)[0], (3, 3.25, 0))

    def test_world_space_equivariance_includes_nonidentity_bind(self):
        bind = (Transform((0, 0, 1, 0), (3, 2, 1)),)
        delta = Transform((0, math.sqrt(.5), 0, math.sqrt(.5)), (10, 20, 30))
        pose = (compose(delta, bind[0]),)
        vertex = (1, 2, 3)
        self.close(skin((vertex,), (((0, 1.0),),), bind, pose)[0], point(delta, vertex))

    def test_animation_reference_need_not_equal_mesh_bind(self):
        # The animation skeleton and an armor mesh have distinct authored rest
        # transforms. Only mesh-bind -> mesh-bind must produce identity skinning.
        mesh_bind = (Transform((0, 0, 0, 1), (0, 1, 0)),)
        hkx_reference = (Transform((0, 0, 0, 1), (0, 1.006, 0)),)
        vertex = ((.1, 1.2, 0),)
        influence = (((0, 1.0),),)
        self.close(skin(vertex, influence, mesh_bind, mesh_bind)[0], vertex[0])
        self.close(skin(vertex, influence, mesh_bind, hkx_reference)[0], (.1, 1.206, 0))

    def test_dummy_parent_space_is_not_attach_space_or_double_transform(self):
        binds = (IDENTITY, Transform((0, 0, 0, 1), (0, -2, 0)), IDENTITY)
        poses = (IDENTITY, Transform((0, 0, 0, 1), (0, 3, 0)), IDENTITY)
        self.close(dummy_position((1, 2, 3), 2, 1, True, binds, poses), (1, 7, 3))
        self.close(dummy_position((1, 2, 3), 2, 1, False, binds, poses), (1, 2, 3))

    def test_separate_root_motion_exposes_weighting_mismatch(self):
        binds = (IDENTITY, IDENTITY)
        poses = (IDENTITY, Transform((0, 0, 0, 1), (0, .1, 0)))
        vertex = ((0, 0, 0),)
        wrong = skin(vertex, (((0, 1.0),),), binds, poses)[0]
        correct = skin(vertex, (((1, 1.0),),), binds, poses)[0]
        self.assertAlmostEqual(math.dist(wrong, correct), .1)

    def test_rejects_bad_hierarchy_and_skin_data(self):
        for parents in ((1, 0), (-2, -1), (0, -1), (3, -1)):
            with self.assertRaises(ValueError):
                world_transforms(parents, (IDENTITY, IDENTITY))
        for weights in ((), ((2, 1),), ((0, .5),), ((0, -1),), ((0, math.nan),), ((0, .5), (0, .5))):
            with self.assertRaises(ValueError):
                skin(((0, 0, 0),), (weights,), (IDENTITY,), (IDENTITY,))
        with self.assertRaises(ValueError):
            skin(((math.nan, 0, 0),), (((0, 1),),), (IDENTITY,), (IDENTITY,))


if __name__ == '__main__':
    unittest.main()
