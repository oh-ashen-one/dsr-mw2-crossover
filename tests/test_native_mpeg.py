import unittest
from dsr_mw2.native_mpeg import frames


class MpegFrameTests(unittest.TestCase):
    def test_skips_fsb_alignment_instead_of_feeding_it_to_decoder(self):
        a = bytes.fromhex('fffba0c0') + b'A'*518
        b = bytes.fromhex('fffba2c0') + b'B'*519
        self.assertEqual(frames(a+b), (a,b))
        self.assertEqual(frames(a+b'XY'+b+b'Z'+b'\0'*8,fsb_aligned=True),(a,b))

    def test_rejects_tags_stereo_wrong_rate_and_truncated_frames(self):
        frame = bytes.fromhex('fffba0c0')+b'A'*518
        for invalid in (b'ID3'+frame,frame[:-1],frame[:3],
                        bytes.fromhex('fffba000')+frame[4:],
                        bytes.fromhex('fffba4c0')+frame[4:]):
            with self.subTest(header=invalid[:4]):
                with self.assertRaises(ValueError):
                    frames(invalid)
        with self.assertRaises(ValueError):
            frames(frame+b'\0',fsb_aligned=True)


if __name__ == '__main__':
    unittest.main()
