import io
import unittest
from PIL import Image
from dsr_mw2.weapon_textures import bc4, bc5_from_packed, dds_header, iwi_blocks


class TextureTests(unittest.TestCase):
    def test_bc5_reload_preserves_packed_normal_channels(self):
        import struct
        source = Image.new("RGBA", (4, 4), (0, 150, 0, 100))
        data = dds_header(4, 4, b"DX10", 16, 1) + struct.pack("<5I", 83, 3, 0, 1, 0) + bc5_from_packed(source)
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.getpixel((0, 0))[:2], (100, 150))

    def test_bc4_endpoint_and_sample_count(self):
        self.assertEqual(bc4([128] * 16), bytes([128, 128]) + bytes(6))
        with self.assertRaises(ValueError):
            bc4([0])

    def test_rectangular_mip_chain_and_truncated_data(self):
        import struct
        header = bytearray(32)
        header[:4] = b"IWi\x08"
        struct.pack_into("<BBHHH", header, 8, 11, 0, 8, 4, 1)
        struct.pack_into("<4I", header, 16, 72, 56, 48, 40)
        source = bytes(header) + bytes(40)
        fmt, levels = iwi_blocks(source)
        self.assertEqual(fmt, 11)
        self.assertEqual([(w, h, len(data)) for w, h, data in levels], [(8, 4, 16), (4, 2, 8), (2, 1, 8), (1, 1, 8)])
        with self.assertRaisesRegex(ValueError, "payload size"):
            iwi_blocks(source[:-1])
