"""Replace known DSR PARAM row bytes without rebuilding tables or losing duplicates."""

from __future__ import annotations

import struct


def patch_row(raw: bytes, row_id: int, original: bytes, replacement: bytes) -> tuple[bytes, int]:
    """Accept only the measured little-endian, 32-bit DSR PARAM layout.

    Soulstruct's table serializer merges duplicate row IDs in some stock tables.
    This operation preserves headers, pointers, names and every other row exactly.
    The original typed row must match the source bytes before anything changes.
    """
    if len(raw) < 48 or raw[44] != 0 or raw[45] not in (0, 2):
        raise ValueError("Unsupported PARAM header; expected DSR little-endian 32-bit offsets")
    if not original or len(original) != len(replacement):
        raise ValueError("Replacement must retain the original row size")
    count = struct.unpack_from("<H", raw, 10)[0]
    pointers_end = 48 + count * 12
    if pointers_end > len(raw):
        raise ValueError("Truncated PARAM row pointers")
    pointers = [struct.unpack_from("<iII", raw, 48 + i * 12) for i in range(count)]
    matches = [p for p in pointers if p[0] == row_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one source row {row_id}, found {len(matches)}")
    offset = matches[0][1]
    end = offset + len(original)
    if offset < pointers_end or end > len(raw):
        raise ValueError("PARAM row points outside its data area")
    if any(offset < other_offset < end for _, other_offset, _ in pointers):
        raise ValueError("Replacement overlaps another PARAM row")
    if raw[offset:end] != original:
        raise ValueError(f"Typed row {row_id} differs from source bytes; refusing lossy patch")
    return raw[:offset] + replacement + raw[end:], offset


def append_fixed_row(raw: bytes, row_id: int, row: bytes) -> bytes:
    """Append a largest-ID unnamed row to measured contiguous DSR PARAM data.

    Unlike reserializing a table, this retains every existing row/pad/name byte.
    Supports the measured contiguous Goods/Weapon/Shop layout. The header's
    first named string can follow the data end; retain that name prefix/gap.
    """
    if len(raw) < 48 or raw[44:48] != b"\x00\x02\x00\x00" or not row:
        raise ValueError("Unsupported contiguous DSR PARAM layout")
    count = struct.unpack_from("<H", raw, 10)[0]
    if not count or count >= 65535 or not -2147483648 <= row_id <= 2147483647:
        raise ValueError("Invalid row count or ID")
    pointer_end = 48 + count * 12
    if pointer_end > len(raw):
        raise ValueError("Truncated row pointers")
    pointers = [struct.unpack_from("<iII", raw, 48 + i * 12) for i in range(count)]
    data_start = pointers[0][1]
    data_end = data_start + count * len(row)
    name_start = struct.unpack_from("<I", raw)[0]
    if (data_start != pointer_end or not data_end <= name_start <= len(raw) or data_end > len(raw) or
            data_start != struct.unpack_from("<H", raw, 4)[0] or data_start + 12 > 65535):
        raise ValueError("Noncontiguous or unexpected PARAM data/name layout")
    ids = [p[0] for p in pointers]
    if len(set(ids))!=len(ids) or row_id <= max(ids):
        raise ValueError("New ID must exceed unique existing IDs; native row order is preserved")
    for i, (_, offset, name) in enumerate(pointers):
        if offset != data_start + i * len(row) or (name and not data_end <= name < len(raw)):
            raise ValueError("Unexpected row or name pointer")
    shift = 12 + len(row)
    header = bytearray(raw[:48])
    struct.pack_into("<I", header, 0, name_start + shift)
    struct.pack_into("<H", header, 4, data_start + 12)
    struct.pack_into("<H", header, 10, count + 1)
    table = b"".join(struct.pack("<iII", rid, offset + 12, name + shift if name else 0)
                     for rid, offset, name in pointers)
    table += struct.pack("<iII", row_id, data_end + 12, 0)
    return bytes(header) + table + raw[data_start:data_end] + row + raw[data_end:]
