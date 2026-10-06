import math
import unittest
from dsr_mw2.animation_pose import rotate, multiply
from dsr_mw2.hand_contact import palm_rotation
from dsr_mw2.pose_ik import normalized


class HandContactTests(unittest.TestCase):
    def test_anatomical_frame_recovers_full_rotation_with_scaled_landmarks(self):
        index=(.08,.02,-.015);thumb=(.02,.02,.008)
        q=multiply((0,math.sin(.6),0,math.cos(.6)),(math.sin(.4),0,0,math.cos(.4)))
        desired=[rotate(q,tuple(v*1.3 for v in p)) for p in (index,thumb)]
        result=palm_rotation(index,thumb,*desired)
        for axis in ((1,0,0),(0,1,0),(0,0,1)):
            self.assertLess(math.dist(rotate(result,axis),rotate(q,axis)),1e-8)

    def test_reverse_palm_not_confused_with_correct_wrist_position(self):
        result=palm_rotation((1,0,0),(0,1,0),(0,0,-2),(0,1,0))
        self.assertLess(math.dist(rotate(result,(1,0,0)),(0,0,-1)),1e-8)
        self.assertLess(math.dist(rotate(result,(0,1,0)),(0,1,0)),1e-8)

    def test_degenerate_or_nonfinite_landmarks_refused(self):
        for index,thumb in (((0,0,0),(0,1,0)),((1,0,0),(2,0,0)),((math.nan,0,0),(0,1,0))):
            with self.assertRaises(ValueError):palm_rotation(index,thumb,(1,0,0),(0,1,0))
