"""Read only the private M9 save's equipment; never export or edit save data.

Format facts and offset conventions are documented in docs/M9-INTEGRATION-TRACE.md.
No downloaded save editor is imported or executed. Decryption uses macOS's system
CommonCrypto and keeps plaintext in memory. The output excludes names/account IDs.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import struct

from .process_ownership import bottle_processes
from .profile import guard
from .runtime_paths import bottle_path
from .save_banks import inspect as inspect_banks, paths

FILE_SIZE = 0x4204D0
ENTRY_SIZE = 0x60030
PAYLOAD_SIZE = 0x60000
M9 = 1250000
BOLT = 2100000
# Public format constant, not a user/account encryption key.
FORMAT_KEY = bytes.fromhex('0123456789abcdeffedcba9876543210')


def aes_cbc(cipher: bytes, key: bytes, iv: bytes) -> bytes:
    if not cipher or len(cipher) % 16 or len(key) != 16 or len(iv) != 16:
        raise ValueError('Invalid AES block dimensions')
    lib = ctypes.CDLL('/usr/lib/system/libcommonCrypto.dylib')
    call = lib.CCCrypt
    call.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                     ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                     ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    call.restype = ctypes.c_int
    out = ctypes.create_string_buffer(len(cipher))
    size = ctypes.c_size_t()
    # kCCDecrypt, kCCAlgorithmAES, CBC without automatic padding removal.
    if call(1, 0, 0, key, len(key), iv, cipher, len(cipher), out, len(cipher), ctypes.byref(size)):
        raise ValueError('System AES decryption failed')
    if size.value != len(cipher):
        raise ValueError('System AES returned an unexpected size')
    return out.raw[:size.value]


def entry_plaintext(raw: bytes, index: int) -> bytes:
    if len(raw) != FILE_SIZE or raw[:4] != b'BND4' or struct.unpack_from('<I', raw, 12)[0] != 11:
        raise ValueError('Unsupported native DSR save container')
    if not 0 <= index <= 10:
        raise ValueError('Invalid save entry')
    head = 64 + 32 * index
    if raw[head:head+8] != bytes.fromhex('50000000ffffffff'):
        raise ValueError('Unsupported save entry header')
    size = struct.unpack_from('<Q', raw, head+8)[0]
    offset = struct.unpack_from('<I', raw, head+16)[0]
    if size != ENTRY_SIZE or offset != 0x2C0 + ENTRY_SIZE * index:
        raise ValueError('Unsupported save entry bounds')
    entry = raw[offset:offset+size]
    if hashlib.md5(entry[16:]).digest() != entry[:16]:
        raise ValueError('Save entry checksum mismatch; preserving file')
    plain = aes_cbc(entry[32:], FORMAT_KEY, entry[16:32])
    if struct.unpack_from('<I', plain)[0] != PAYLOAD_SIZE:
        raise ValueError('Unsupported decrypted save entry length')
    padding = plain[4+PAYLOAD_SIZE:]
    if not 1 <= len(padding) <= 16 or padding != bytes([len(padding)]) * len(padding):
        raise ValueError('Save entry padding mismatch')
    # Keep the four-byte length prefix; offsets below use this exact convention.
    return plain[:4+PAYLOAD_SIZE]


def equipment(plain: bytes) -> dict:
    if len(plain) != 4 + PAYLOAD_SIZE or struct.unpack_from('<I', plain)[0] != PAYLOAD_SIZE:
        raise ValueError('Unsupported character payload')
    records = [struct.unpack_from('<7i', plain, 0x360 + 28*i) for i in range(2048)]
    hands = {}
    for label, index_offset, id_offset in (
        ('left_1', 0x298, 0x304), ('right_1', 0x29C, 0x308),
        ('left_2', 0x2A0, 0x30C), ('right_2', 0x2A4, 0x310),
    ):
        index = struct.unpack_from('<i', plain, index_offset)[0]
        item_id = struct.unpack_from('<i', plain, id_offset)[0]
        if index == -1 and item_id == -1:
            hands[label] = {'item_id': -1, 'inventory_index': -1}
            continue
        if not 0 <= index < len(records):
            raise ValueError('Equipment points outside inventory')
        category, ident, quantity, _, active, _, _ = records[index]
        if category != 0 or ident != item_id or quantity != 1 or active != 1:
            raise ValueError('Equipment and active inventory disagree')
        hands[label] = {'item_id': item_id, 'inventory_index': index}
    left, right = struct.unpack_from('<2i', plain, 0x2EC)
    if left not in (0, 1) or right not in (0, 1):
        raise ValueError('Invalid selected hand slot')
    relevant = [{'item_id': ident, 'quantity': quantity, 'inventory_index': index}
                for index, (category, ident, quantity, _, active, _, _) in enumerate(records)
                if category == 0 and ident in (M9, BOLT) and active == 1 and quantity > 0]
    return {'hands': hands, 'selected_right_slot': right + 1,
            'selected_right_item': hands[f'right_{right+1}']['item_id'],
            'm9_equipped_slots': [name for name, item in hands.items() if item['item_id'] == M9],
            'm9_and_bolts_in_inventory': relevant}


def inspect_private() -> dict:
    bottle = bottle_path()
    if guard(bottle):
        raise ValueError('Private profile guard failed; save inspection stopped')
    if bottle_processes(bottle):
        raise ValueError('Private session is active; save inspection stopped')
    lock_path = bottle / '.dsr-mw2-session.lock'
    if lock_path.is_symlink():
        raise ValueError('Private lock is redirected')
    with lock_path.open('r') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if inspect_banks(bottle) != {'initialized': True, 'active': 'm9'}:
            raise ValueError('Only the active private M9 save may be inspected')
        candidates = list(paths(bottle)[0].rglob('DRAKS0005.sl2'))
        if len(candidates) != 1:
            raise ValueError('Expected exactly one private M9 save')
        source = candidates[0]
        if source.stat().st_size != FILE_SIZE:
            raise ValueError('Unexpected private save size')
        raw = source.read_bytes()
        meta = entry_plaintext(raw, 10)
        occupancy = meta[180:190]
        if any(value not in (0, 1) for value in occupancy):
            raise ValueError('Invalid native character occupancy flags')
        characters = [{'slot': index, **equipment(entry_plaintext(raw, index))}
                      for index, value in enumerate(occupancy) if value]
        if source.read_bytes() != raw:
            raise ValueError('Save changed during read; discard diagnostic')
    return {'schema': 1, 'source': 'active-private-m9-save',
            'save_sha256': hashlib.sha256(raw).hexdigest(), 'save_unchanged': True,
            'characters': characters, 'game_launched': False, 'save_written': False,
            'rendered_model_verified': False}


if __name__ == '__main__':
    print(json.dumps(inspect_private(), indent=2))
