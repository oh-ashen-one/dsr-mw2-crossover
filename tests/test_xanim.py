import math
import struct
import unittest
from dsr_mw2.xanim import read


def fixture(frames=3, half=False, sign=False):
    # Original one-bone fixture, no retail animation data.
    header = struct.pack("<HHHBBH", 17, frames+1, 1, 0, 1, 30)
    data = header + bytes([int(sign), int(half)]) + b"test_bone\0"
    data += struct.pack("<H", 1) + struct.pack("<h" if half else "<hhh", *((16384,) if half else (0, 0, 0)))
    data += struct.pack("<Hfff", 1, 1., 2., 3.)
    data += b"\x01reload\0" + struct.pack("<H", frames)
    return data


class XAnimTests(unittest.TestCase):
    def test_constant_pose_and_event_time(self):
        a = read(fixture())
        self.assertEqual((a.frames, a.fps, a.seconds), (3, 30, .1))
        self.assertEqual(a.bones[0].rotation.values, ((0., 0., 0., 1.),))
        self.assertEqual(a.bones[0].translation.values, ((1., 2., 3.),))
        self.assertEqual(a.events, (("reload", 3),))

    def test_half_rotation_and_flip_sign(self):
        q = read(fixture(half=True, sign=True)).bones[0].rotation.values[0]
        self.assertLess(q[2], 0)
        self.assertLess(q[3], 0)
        self.assertAlmostEqual(sum(x*x for x in q), 1.)

    def test_sparse_short_indices_and_compressed_translation(self):
        b = struct.pack("<HHHBBH", 17, 301, 1, 0, 1, 60) + b"\0\0joint\0"
        b += struct.pack("<H", 0)  # identity rotation
        b += struct.pack("<HHHBffffff", 2, 0, 300, 1, 1., 2., 3., 255., 255., 255.)
        b += bytes([0, 0, 0, 255, 128, 64]) + b"\0"
        a = read(b)
        self.assertEqual(a.bones[0].translation.indices, (0, 300))
        self.assertAlmostEqual(a.bones[0].translation.values[1][0], 256., places=4)
        self.assertAlmostEqual(a.bones[0].translation.values[1][1], 130., places=4)

    def test_sequential_track_omits_indices(self):
        b = struct.pack("<HHHBBH", 17, 2, 1, 0, 1, 30) + b"\0\x01joint\0"
        b += struct.pack("<HhhH", 2, 0, 32767, 0) + b"\0"
        a = read(b)
        self.assertEqual(a.bones[0].rotation.indices, (0, 1))
        self.assertEqual(a.bones[0].rotation.values[-1], (0., 0., 1., 0.))

    def test_every_truncation_and_trailing_data_are_rejected(self):
        b = fixture()
        for i in range(len(b)):
            with self.subTest(offset=i), self.assertRaises(ValueError):
                read(b[:i])
        with self.assertRaisesRegex(ValueError, "Unconsumed"):
            read(b+b"\0")

    def test_unsupported_delta_bad_limits_and_nonfinite_values(self):
        b = bytearray(fixture())
        for offset, fmt, value in ((6, "B", 2), (8, "H", 0), (4, "H", 65535)):
            bad = b.copy(); struct.pack_into("<"+fmt, bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): read(bytes(bad))
        bad = b.replace(struct.pack("<fff", 1., 2., 3.), struct.pack("<fff", math.nan, 2., 3.))
        with self.assertRaisesRegex(ValueError, "Non-finite"): read(bytes(bad))
        bad = b.copy(); struct.pack_into("<H", bad, len(bad)-2, 4)
        with self.assertRaisesRegex(ValueError, "event outside"): read(bytes(bad))
