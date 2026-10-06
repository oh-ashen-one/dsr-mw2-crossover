import struct
import unittest

from dsr_mw2.flver_bone_bounds import read_bounds


def fixture():
    data = bytearray(480)
    data[:8] = b'FLVER\0L\0'
    struct.pack_into('<II', data, 8, 0x2000C, 480)
    struct.pack_into('<III', data, 20, 1, 1, 2)
    start = 128 + 64 + 32
    for i in range(2):
        struct.pack_into('<3f', data, start + i * 128 + 48, -1.0 - i, 2.0, -3.0)
        struct.pack_into('<3f', data, start + i * 128 + 64, 4.0, 5.0, 6.0 + i)
    return bytes(data)


class FlverBoundsTests(unittest.TestCase):
    def test_actual_fixed_records_preserve_different_nonzero_bounds(self):
        self.assertEqual(read_bounds(fixture()), (((-1, 2, -3), (4, 5, 6)), ((-2, 2, -3), (4, 5, 7))))

    def test_unused_bone_extrema_are_preserved_and_bad_layout_rejected(self):
        data = bytearray(fixture())
        struct.pack_into('<3f', data, 224 + 48, *([3.4028234663852886e38] * 3))
        struct.pack_into('<3f', data, 224 + 64, *([-3.4028234663852886e38] * 3))
        low, high = read_bounds(bytes(data))[0]
        self.assertGreater(low[0], high[0])
        for at, value in ((8, 0x20010), (12, 200), (28, 513), (20, 4097)):
            bad = bytearray(fixture())
            struct.pack_into('<I', bad, at, value)
            with self.assertRaises(ValueError):
                read_bounds(bytes(bad))
        with self.assertRaises(ValueError):
            read_bounds(fixture()[:-1])


if __name__ == '__main__':
    unittest.main()
