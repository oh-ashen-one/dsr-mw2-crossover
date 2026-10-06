import hashlib
import struct
import sys
import unittest
from unittest.mock import patch

from dsr_mw2 import save_inspect as inspect


def character():
    data = bytearray(4 + inspect.PAYLOAD_SIZE)
    struct.pack_into('<I', data, 0, inspect.PAYLOAD_SIZE)
    for index, ident, quantity in ((64, 900000, 1), (65, 212000, 1),
                                    (66, 900000, 1), (67, 1250000, 1), (68, 2100000, 99)):
        struct.pack_into('<7i', data, 0x360+28*index, 0, ident, quantity, 0, 1, 150, 0)
    for index, index_offset, id_offset, ident in (
        (64, 0x298, 0x304, 900000), (65, 0x29C, 0x308, 212000),
        (66, 0x2A0, 0x30C, 900000), (67, 0x2A4, 0x310, 1250000),
    ):
        struct.pack_into('<i', data, index_offset, index)
        struct.pack_into('<i', data, id_offset, ident)
    return data


class SaveInspectionTests(unittest.TestCase):
    def test_owner_guidance_uses_saved_selection(self):
        from dsr_mw2.owner_launch import equipment_message
        data = character()
        self.assertIn('Switch weapon once', equipment_message({'characters': [inspect.equipment(data)]}))
        struct.pack_into('<i', data, 0x2F0, 1)
        self.assertIn('has the M9 selected', equipment_message({'characters': [inspect.equipment(data)]}))
        self.assertIn('Existing characters keep', equipment_message({'characters': []}))

    def test_distinguishes_owned_equipped_and_selected(self):
        data = character()
        result = inspect.equipment(data)
        self.assertEqual(result['m9_equipped_slots'], ['right_2'])
        self.assertEqual(result['selected_right_item'], 212000)
        self.assertEqual(result['m9_and_bolts_in_inventory'][1]['quantity'], 99)
        struct.pack_into('<i', data, 0x2F0, 1)
        self.assertEqual(inspect.equipment(data)['selected_right_item'], 1250000)

    def test_rejects_cached_id_without_matching_active_inventory(self):
        for offset, value in ((0x360+28*67+4, 212000), (0x360+28*67+16, 0),
                              (0x2A4, 2048), (0x2F0, 2)):
            with self.subTest(offset=offset):
                data = character()
                struct.pack_into('<i', data, offset, value)
                with self.assertRaises(ValueError):
                    inspect.equipment(data)

    def test_container_rejects_corruption_before_decryption(self):
        raw = bytearray(inspect.FILE_SIZE)
        raw[:4] = b'BND4'
        struct.pack_into('<I', raw, 12, 11)
        raw[64:72] = bytes.fromhex('50000000ffffffff')
        struct.pack_into('<Q', raw, 72, inspect.ENTRY_SIZE)
        struct.pack_into('<I', raw, 80, 0x2C0)
        start, end = 0x2C0, 0x2C0+inspect.ENTRY_SIZE
        raw[start:start+16] = hashlib.md5(raw[start+16:end]).digest()
        plain = bytes(character()) + b'\x0c'*12
        with patch.object(inspect, 'aes_cbc', return_value=plain) as decrypt:
            self.assertEqual(inspect.entry_plaintext(raw, 0), plain[:-12])
            decrypt.reset_mock()
            raw[end-1] ^= 1
            with self.assertRaisesRegex(ValueError, 'checksum'):
                inspect.entry_plaintext(raw, 0)
            decrypt.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'Uses macOS system CommonCrypto')
    def test_system_aes_against_nist_sp800_38a_vector(self):
        self.assertEqual(inspect.aes_cbc(
            bytes.fromhex('7649abac8119b246cee98e9b12e9197d'),
            bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c'),
            bytes.fromhex('000102030405060708090a0b0c0d0e0f')),
            bytes.fromhex('6bc1bee22e409f96e93d7e117393172a'))


if __name__ == '__main__':
    unittest.main()
