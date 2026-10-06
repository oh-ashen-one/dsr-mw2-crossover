import struct
import unittest

from dsr_mw2.iwi_texture import decode_iwi


class IWITextureTests(unittest.TestCase):
    def test_version8_bgra_top_mip(self):
        header = b"IWi\x08" + b"\x00" * 4
        info = struct.pack("<BBHH", 1, 0, 1, 1) + b"\x00\x00"
        mips = struct.pack("<4I", 36, 36, 36, 36)
        image = decode_iwi(header + info + mips + b"\x11\x22\x33\x44")
        self.assertEqual(image.getpixel((0, 0)), (0x33, 0x22, 0x11, 0x44))

    def test_bad_top_mip_is_rejected(self):
        header = b"IWi\x08" + b"\x00" * 4
        info = struct.pack("<BBHH", 1, 0, 1, 1) + b"\x00\x00"
        mips = struct.pack("<4I", 36, 36, 36, 36)
        with self.assertRaises(ValueError):
            decode_iwi(header + info + mips + b"\x11\x22\x33")


if __name__ == "__main__":
    unittest.main()
