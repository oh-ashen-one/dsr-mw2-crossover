import struct
import unittest
from dsr_mw2.pe_image import PEImage


def fixture():
    b = bytearray(0x800)
    b[:2] = b"MZ"
    struct.pack_into("<I", b, 0x3c, 0x80)
    b[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHI", b, 0x84, 0x8664, 2, 1)
    struct.pack_into("<H", b, 0x94, 0xf0)
    o = 0x98
    struct.pack_into("<H", b, o, 0x20b)
    struct.pack_into("<Q", b, o + 24, 0x140000000)
    struct.pack_into("<I", b, o + 56, 0x3000)
    struct.pack_into("<I", b, o + 108, 16)
    struct.pack_into("<II", b, o + 136, 0x2000, 12)
    for i, (name, va, off, flags) in enumerate(((b".text", 0x1000, 0x400, 0x60000020), (b".pdata", 0x2000, 0x600, 0x40000040))):
        s = o + 0xf0 + i * 40
        b[s:s+8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", b, s+8, 0x200, va, 0x200, off)
        struct.pack_into("<I", b, s+36, flags)
    b[0x400:0x407] = bytes.fromhex("48 8b 05 f9 0f 00 00")
    struct.pack_into("<III", b, 0x600, 0x1000, 0x1080, 0x2020)
    return b


class PEImageTests(unittest.TestCase):
    def test_unique_code_pointer_and_function(self):
        p = PEImage(bytes(fixture()))
        self.assertEqual(p.unique("48 8b 05 ? ? ? ?"), 0x1000)
        self.assertEqual(p.rip_target(0x1000, 3, 7), 0x2000)
        self.assertEqual(p.function_at(0x1020), (0x1000, 0x1080, 0x2020))

    def test_data_patterns_do_not_count_but_duplicate_code_does(self):
        b = fixture()
        b[0x640:0x647] = b[0x400:0x407]
        self.assertEqual(PEImage(bytes(b)).unique("48 8b 05 ?? ?? ?? ??"), 0x1000)
        b[0x440:0x447] = b[0x400:0x407]
        with self.assertRaisesRegex(ValueError, "got 2"):
            PEImage(bytes(b)).unique("48 8b 05 ?? ?? ?? ??")

    def test_overlapping_matches_count(self):
        b = fixture()
        b[0x450:0x453] = b"\xaa" * 3
        self.assertEqual(PEImage(bytes(b)).find("aa aa"), [0x1050, 0x1051])

    def test_truncation_bad_range_and_unbacked_rva_are_rejected(self):
        for length in (0, 60, 100, 0x190, 0x610):
            with self.subTest(length=length), self.assertRaises(ValueError):
                PEImage(bytes(fixture()[:length]))
        b = fixture()
        struct.pack_into("<I", b, 0x604, 0x4000)
        with self.assertRaises(ValueError):
            PEImage(bytes(b)).functions()
        b = fixture()
        struct.pack_into("<I", b, 0x98 + 0xf0 + 8, 0x300)
        with self.assertRaisesRegex(ValueError, "zero-fill"):
            PEImage(bytes(b)).at(0x1200, 4)

    def test_invalid_and_empty_patterns_fail(self):
        for pattern in ("", "?? ?", "gg", "100", "a"):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                PEImage(bytes(fixture())).find(pattern)

    def test_overlapping_sections_are_rejected(self):
        b = fixture()
        struct.pack_into("<I", b, 0x98 + 0xf0 + 40 + 12, 0x1100)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            PEImage(bytes(b))
