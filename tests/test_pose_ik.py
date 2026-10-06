import math
import unittest
from dsr_mw2.animation_pose import Transform,rotate
from dsr_mw2.pose_ik import two_bone,swing
from dsr_mw2.skin_geometry import world_transforms


class PoseIKTests(unittest.TestCase):
    def test_two_bone_reaches_with_unchanged_lengths_and_orientation(self):
        p=[Transform((0,0,0,1),(0,0,0)),Transform((0,0,0,1),(1,0,0)),Transform((0,0,0,1),(1,0,0))]
        q=(0,0,math.sin(.4),math.cos(.4))
        r,proof=two_bone(p,[-1,0,1],0,1,2,(1,.5,.5),(0,0,2),q)
        w=world_transforms([-1,0,1],r)
        self.assertLess(math.dist(w[2].translation,(1,.5,.5)),1e-6)
        self.assertAlmostEqual(abs(sum(a*b for a,b in zip(w[2].rotation,q))),1)
        self.assertEqual([x.translation for x in p],[x.translation for x in r])
        self.assertEqual(proof['target_clamp_m'],0)

    def test_unreachable_reports_clamp_and_preserves_chain(self):
        p=[Transform((0,0,0,1),(0,0,0)),Transform((0,0,0,1),(1,0,0)),Transform((0,0,0,1),(1,0,0))]
        r,proof=two_bone(p,[-1,0,1],0,1,2,(4,0,0),(0,0,2),(0,0,0,1))
        self.assertAlmostEqual(proof['target_clamp_m'],2.00001)
        w=world_transforms([-1,0,1],r)
        self.assertAlmostEqual(math.dist(w[1].translation,w[2].translation),1)

    def test_opposite_and_degenerate_vectors(self):
        self.assertLess(math.dist(rotate(swing((1,0,0),(-1,0,0)),(1,0,0)),(-1,0,0)),1e-8)
        with self.assertRaises(ValueError):swing((0,0,0),(1,0,0))
