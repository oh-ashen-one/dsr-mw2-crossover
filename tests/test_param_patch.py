import struct
import unittest

from dsr_mw2.param_patch import append_fixed_row, patch_row


def fixture(ids=(7, 8, 8)):
    data = bytearray(48 + 12 * len(ids) + 4 * len(ids) + 20)
    struct.pack_into("<H", data, 10, len(ids))
    for i, row_id in enumerate(ids):
        offset = 48 + 12 * len(ids) + i * 4
        struct.pack_into("<iII", data, 48 + i * 12, row_id, offset, 0)
        data[offset:offset + 4] = bytes([i + 1]) * 4
    return bytes(data)


class ParamPatchTests(unittest.TestCase):
    def append_fixture(self):
        data = bytearray(fixture((7, 8)))
        data[45] = 2
        struct.pack_into("<I", data, 0, 80)
        struct.pack_into("<H", data, 4, 72)
        struct.pack_into("<I", data, 56, 80)
        data[80:84] = b"abc\0"
        return bytes(data)

    def test_append_preserves_existing_row_and_name_bytes(self):
        old = self.append_fixture()
        new = append_fixed_row(old, 9, b"new!")
        self.assertEqual(new[84:92], old[72:80])
        self.assertEqual(new[92:96], b"new!")
        self.assertEqual(new[96:], old[80:])
        self.assertEqual(struct.unpack_from("<iII", new, 48), (7, 84, 96))
        self.assertEqual(struct.unpack_from("<iII", new, 72), (9, 92, 0))
        self.assertEqual(struct.unpack_from("<H", new, 10)[0], 3)

    def test_append_refuses_duplicate_or_unknown_layout(self):
        with self.assertRaises(ValueError):
            append_fixed_row(self.append_fixture(), 8, b"new!")
        with self.assertRaises(ValueError):
            append_fixed_row(self.append_fixture(), 9, b"wrongsize")
        with self.assertRaises(ValueError):
            append_fixed_row(fixture(), 9, b"new!")
        data = bytearray(self.append_fixture())
        struct.pack_into("<I", data, 56, 72)
        with self.assertRaises(ValueError):
            append_fixed_row(bytes(data), 9, b"new!")

    def test_append_preserves_name_header_gap_and_all_string_pointers(self):
        data = bytearray(self.append_fixture())
        struct.pack_into("<I", data, 0, 84)
        struct.pack_into("<I", data, 68, 84)
        data[84:88] = b"def\0"
        new = append_fixed_row(bytes(data), 9, b"new!")
        self.assertEqual(struct.unpack_from("<I", new, 0)[0], 100)
        self.assertEqual(struct.unpack_from("<I", new, 68)[0], 100)
        self.assertEqual(new[96:], data[80:])

    def test_append_keeps_native_unsorted_shop_order(self):
        data=bytearray(self.append_fixture())
        struct.pack_into('<i',data,48,8)
        struct.pack_into('<i',data,60,7)
        new=append_fixed_row(bytes(data),9,b'new!')
        self.assertEqual([struct.unpack_from('<i',new,48+i*12)[0] for i in range(3)],[8,7,9])
        self.assertEqual(new[84:92],data[72:80])

    def test_preserves_duplicate_untouched_rows_and_nonrow_bytes(self):
        original = fixture()
        result, offset = patch_row(original, 7, b"\x01" * 4, b"\x09" * 4)
        self.assertEqual(result[:offset], original[:offset])
        self.assertEqual(result[offset + 4:], original[offset + 4:])
        self.assertEqual(len(result), len(original))

    def test_refuses_ambiguous_target_or_wrong_source_bytes(self):
        with self.assertRaises(ValueError):
            patch_row(fixture(), 8, b"\x02" * 4, b"\x09" * 4)
        with self.assertRaises(ValueError):
            patch_row(fixture(), 7, b"bad!", b"new!")

    def test_refuses_unknown_layout_and_out_of_bounds_pointer(self):
        data = bytearray(fixture())
        data[44] = 255
        with self.assertRaises(ValueError):
            patch_row(bytes(data), 7, b"\x01" * 4, b"\x09" * 4)
        data = bytearray(fixture())
        struct.pack_into("<I", data, 52, 3)
        with self.assertRaises(ValueError):
            patch_row(bytes(data), 7, b"\x01" * 4, b"\x09" * 4)
