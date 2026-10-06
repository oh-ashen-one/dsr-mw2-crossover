import unittest
from dsr_mw2.havok_study import single_block_layout, make_spline_study


class SplineStudyTests(unittest.TestCase):
    def test_rate_scales_time_without_changing_block_storage(self):
        a=single_block_layout(99,26,30);b=single_block_layout(99,26,60)
        self.assertEqual(a['maskAndQuantizationSize'],104)
        self.assertEqual(a['blockOffsets'],[0])
        self.assertEqual(a['blockDuration'],2*b['blockDuration'])
        self.assertAlmostEqual(b['blockDuration']*b['blockInverseDuration'],1)
        self.assertEqual(b['frameDuration'],1/60)

    def test_unsupported_shapes_fail_before_optional_imports(self):
        for frames,tracks,rate in ((1,26,60),(257,26,60),(99,62,60),(99,0,60),(99,26,float('nan')),(99,26,0)):
            with self.assertRaises(ValueError):single_block_layout(frames,tracks,rate)
        with self.assertRaises(ValueError):make_spline_study([[None],[None]],[61],['bad'],60)
        with self.assertRaises(ValueError):make_spline_study([[None,None],[None,None]],[1,1],['a','b'],60)
