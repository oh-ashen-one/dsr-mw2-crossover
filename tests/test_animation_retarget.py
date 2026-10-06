import math
import unittest
from dsr_mw2.animation_pose import RigBone, Transform, quaternion_from_columns, rotate
from dsr_mw2.animation_retarget import OrthogonalBasis, iw4_viewhand_pose, retarget_global_rotations, retarget_local_rotation, forearm_twist_rotation
from dsr_mw2.skin_geometry import world_transforms

I = (0, 0, 0, 1)
Z90 = (0, 0, math.sqrt(.5), math.sqrt(.5))


class RetargetTests(unittest.TestCase):
    def test_forearm_twist_preserves_anchor_and_elbow_to_wrist_axis(self):
        x30=(math.sin(math.pi/12),0,0,math.cos(math.pi/12))
        for a,b in zip(forearm_twist_rotation(I,I,I,I,x30),x30):self.assertAlmostEqual(a,b)
        # Arbitrary hand swing cannot make the foretwist point off the arm.
        q=forearm_twist_rotation(Z90,(.3,.5,.2,.7),I,I,x30)
        for a,b in zip(rotate(q,(1,0,0)),rotate(Z90,(1,0,0))):self.assertAlmostEqual(a,b)

    def test_local_joint_change_uses_bone_axes_and_preserves_anchor(self):
        basis=OrthogonalBasis(((1,0,0),(0,1,0),(0,0,1)))
        self.assertEqual(retarget_local_rotation(I,I,Z90,I,I,basis),Z90)
        # A source X bend with its bone rotated around Z becomes a target Y bend.
        q=retarget_local_rotation(I,(1,0,0,0),I,Z90,I,basis)
        for a,b in zip(rotate(q,(0,0,1)),(0,0,-1)):self.assertAlmostEqual(a,b)
        self.assertAlmostEqual(abs(q[1]),1)

    def test_reflection_conjugates_rotation_without_becoming_a_quaternion(self):
        basis=OrthogonalBasis(((0,0,-1),(1,0,0),(0,1,0)))
        self.assertAlmostEqual(basis.determinant,-1)
        vector=(1,2,3)
        for q in (Z90,(1,0,0,0),(0,math.sqrt(.5),0,math.sqrt(.5))):
            a=basis.vector(rotate(q,vector));b=rotate(basis.rotation(q),basis.vector(vector))
            for left,right in zip(a,b):self.assertAlmostEqual(left,right)
        with self.assertRaises(ValueError):OrthogonalBasis(((2,0,0),(0,1,0),(0,0,1)))

    def test_different_hierarchy_keeps_global_delta_without_double_rotation(self):
        source = (Transform(I, (0, 0, 0)), Transform(I, (0, 1, 0)))
        posed = tuple(Transform(Z90, t.translation) for t in source)
        target = (Transform(I, (5, 0, 0)), Transform(I, (2, 0, 0)), Transform(I, (1, 0, 0)))
        out = retarget_global_rotations(source, posed, target, [-1, 0, 1], {0: 0, 2: 1}, I)
        world = world_transforms([-1, 0, 1], out)
        for i in (0, 2):
            for a, b in zip(rotate(world[i].rotation, (1, 0, 0)), (0, 1, 0)):
                self.assertAlmostEqual(a, b)
        self.assertEqual(out[1], target[1])
        self.assertEqual([p.translation for p in out], [p.translation for p in target])
        self.assertAlmostEqual(abs(out[2].rotation[3]), 1)

    def test_rest_and_explicit_world_basis(self):
        source = (Transform(Z90, (0, 0, 0)),)
        target = (Transform((0, 1, 0, 0), (2, 3, 4)),)
        basis = quaternion_from_columns(((0, 0, 1), (1, 0, 0), (0, 1, 0)))
        out = retarget_global_rotations(source, source, target, [-1], {0: 0}, basis)
        for a, b in zip(out[0].rotation, target[0].rotation): self.assertAlmostEqual(a, b)
        self.assertEqual(out[0].translation, (2, 3, 4))
        posed = (Transform((0, 0, 1, 0), (0, 0, 0)),)
        out = retarget_global_rotations(source, posed, (Transform(I, (0, 0, 0)),), [-1], {0: 0}, basis)
        # Source Z-axis quarter turn maps to target Y-axis quarter turn.
        for a, b in zip(rotate(out[0].rotation, (0, 0, 1)), (1, 0, 0)): self.assertAlmostEqual(a, b)

    def test_rejects_invalid_mapping_and_hierarchy(self):
        pose = (Transform(I, (0, 0, 0)), Transform(I, (1, 0, 0)))
        for mapping in ({}, {0: 0, 1: 0}, {2: 0}, {0: 2}):
            with self.assertRaises(ValueError): retarget_global_rotations(pose, pose, pose, [-1, 0], mapping, I)
        with self.assertRaises(ValueError): retarget_global_rotations(pose, pose, pose, [1, 0], {0: 0}, I)

    def test_zero_rotation_track_differs_from_absent_bone(self):
        bind = Transform(Z90, (1, 2, 3))
        rig = (RigBone("hand", -1, bind, bind),)
        self.assertEqual(iw4_viewhand_pose(rig, {})[0], bind)
        reset = iw4_viewhand_pose(rig, {"hand": {"rotation": None, "translation": None}})[0]
        self.assertEqual(reset.rotation, I)
        self.assertEqual(reset.translation, bind.translation)
        with self.assertRaises(ValueError):
            iw4_viewhand_pose((RigBone("j_gun", -1, bind, bind),), {})
