"""Write an original IW4 fixture with 64-bit fields and 32-bit block offsets.

This contains no retail bytes. The rawfile name aliases a script string in the
virtual block, exercising the installed format's mixed pointer/address widths.
It does not execute an extractor or install anything into a game.
"""

import argparse
from pathlib import Path
import struct
import zlib


def fixture() -> bytes:
    following = (1 << 64) - 1
    name = b"native64fixture.txt\0"
    text = b"generated format fixture\0"
    # Index 0 is null; index 1 follows its 16-byte native pointer table.
    strings = struct.pack("<QQ", 0, following) + name
    assets = struct.pack("<I4xQI4xQ", 36, following, 11, following)
    # Block 3, byte 16, plus 1 to keep block-0/offset-0 distinct from null.
    rawfile = struct.pack("<QiiQ", 0x30000011, 0, len(text) - 1, following)
    root = struct.pack("<I4xQI4xQ", 2, following, 2, following)
    alias = 0x30000011
    sound_list = struct.pack("<QQI4x", alias, following, 1)
    sound = bytearray(136)
    struct.pack_into("<Q", sound, 0, alias)
    struct.pack_into("<Q", sound, 40, following)
    struct.pack_into("<Q", sound, 128, following)
    sound_file = struct.pack("<BB6xQQ", 1, 1, following, 0)
    pcm = struct.pack("<3h", 0, 100, -100)
    loaded_sound = bytearray(64)
    struct.pack_into("<Q", loaded_sound, 0, alias)
    struct.pack_into("<HHIIHH", loaded_sound, 8, 1, 1, 48000, 96000, 2, 16)
    struct.pack_into("<I", loaded_sound, 32, len(pcm))
    struct.pack_into("<Q", loaded_sound, 56, following)
    speaker_map = struct.pack("<B7xQ", 1, alias)
    # Exercise dynamic counts above the old fixed six-speaker limit.
    counts = (2, 6, 4, 12)
    speaker_map += b"".join(struct.pack("<I4xQ", count, following) for count in counts)
    levels = b"".join(struct.pack("<If", i, .5) for count in counts for i in range(count))
    body = root + strings + assets + rawfile + text + sound_list + sound + sound_file + loaded_sound + pcm + speaker_map + levels
    sizes = struct.pack("<10I", len(body), 0, 4096, 0, 0, 4096, 0, 0, 0, 0)
    header = b"IWffu100" + struct.pack("<I", 276) + b"\x01" + bytes(8)
    return header + zlib.compress(sizes + body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(fixture())
