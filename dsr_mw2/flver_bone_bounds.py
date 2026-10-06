"""Preserve bounds omitted by pinned Soulstruct's FLVERBone object reader.

Narrow native DSR 0x2000C little-endian layout only. This reads raw fixed bone
records, independently of the object adapter that silently defaults the AABB.
"""
import math
import struct


def read_bounds(data: bytes):
    if not 128 <= len(data) <= 32 * 1024 * 1024 or data[:8] != b'FLVER\0L\0':
        raise ValueError('Expected bounded native little-endian FLVER2')
    version, vertex_offset = struct.unpack_from('<II', data, 8)
    dummies, materials, bones = struct.unpack_from('<III', data, 20)
    if version != 0x2000C or not 1 <= bones <= 512 or dummies > 4096 or materials > 2048:
        raise ValueError('Unsupported native FLVER2 header')
    bone_start = 128 + dummies * 64 + materials * 32
    if not bone_start + bones * 128 <= vertex_offset <= len(data):
        raise ValueError('FLVER bone headers exceed fixed section')
    result = []
    for i in range(bones):
        at = bone_start + i * 128
        low = struct.unpack_from('<3f', data, at + 48)
        high = struct.unpack_from('<3f', data, at + 64)
        if not all(math.isfinite(v) for v in low + high):
            raise ValueError('Nonfinite native bone bounds')
        # Inverted finite extrema represent unused bones and must survive too.
        result.append((low, high))
    return tuple(result)
