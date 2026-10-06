import unittest
from dsr_mw2.animation_pose import RigBone, Transform
from dsr_mw2.weapon_articulation import relative_part_pose


class WeaponArticulationTests(unittest.TestCase):
    def rig(self):
        root=Transform((0,0,0,1),(0,0,0));part=Transform((0,0,0,1),(2,3,4))
        return (RigBone('j_gun',-1,root,root),RigBone('j_bolt',0,part,part))

    def test_translation_is_offset_from_pivot_and_unmapped_root_stays_bound(self):
        components={'j_gun':{'rotation':None,'translation':(99,99,99)},
                    'j_bolt':{'rotation':None,'translation':(-1,0,0)}}
        local,world=relative_part_pose(self.rig(),components,{'j_bolt'})
        self.assertEqual(local[0],self.rig()[0].local_bind)
        self.assertEqual(world[1].translation,(1,3,4))

    def test_missing_component_retains_bind_and_bad_modes_fail(self):
        rig=self.rig()
        self.assertEqual(relative_part_pose(rig,{}, {'j_bolt'})[0][1],rig[1].local_bind)
        with self.assertRaises(ValueError):relative_part_pose(rig,{}, {'unknown'})
        changed=Transform((0,0,1,0),(2,3,4))
        with self.assertRaises(ValueError):
            relative_part_pose((rig[0],RigBone('j_bolt',0,changed,changed)),{}, {'j_bolt'})
        for translation in ((float('nan'),0,0),(0,0)):
            with self.assertRaises(ValueError):
                relative_part_pose(rig,{'j_bolt':{'rotation':None,'translation':translation}}, {'j_bolt'})
