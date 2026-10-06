"""Prepare authentic M9 DDS materials offline; normal channel mapping is a candidate.

Diffuse/specular BC blocks are preserved losslessly with their full mip chains.
MW2's packed normal A/G channels are converted to DSR's measured BC5 normal
container. This channel interpretation still needs model/material and runtime QA.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
from zipfile import ZipFile

from PIL import Image


def dds_header(width: int, height: int, fourcc: bytes, top_size: int, mip_count: int) -> bytes:
    fields = [124, 0xA1007, height, width, top_size, 0, mip_count]
    fields += [0] * 11
    fields += [32, 4, int.from_bytes(fourcc, "little"), 0, 0, 0, 0, 0]
    fields += [0x401008 if mip_count > 1 else 0x1000, 0, 0, 0, 0]
    return b"DDS " + struct.pack("<31I", *fields)


def iwi_blocks(data: bytes) -> tuple[int, list[tuple[int, int, bytes]]]:
    if len(data) < 32 or data[:4] != b"IWi\x08":
        raise ValueError("Expected MW2 IWI v8")
    fmt, flags, width, height = struct.unpack_from("<BBHH", data, 8)
    if fmt not in (11, 13) or flags != 0 or any(value & (value - 1) or not 4 <= value <= 4096 for value in (width, height)):
        raise ValueError("Only power-of-two BC1/BC3 mip chains are supported")
    block_size = 8 if fmt == 11 else 16
    sizes = []
    w, h = width, height
    while True:
        sizes.append((w, h, ((w + 3) // 4) * ((h + 3) // 4) * block_size))
        if w == h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    if 32 + sum(s for _, _, s in sizes) != len(data):
        raise ValueError("Unexpected IWI mip payload size")
    mip1, mip2, _, _ = struct.unpack_from("<4I", data, 16)
    if mip1 != len(data) or mip2 != len(data) - sizes[0][2]:
        raise ValueError("IWI offset table differs from measured layout")
    chunks = []
    start = 32
    for w, h, size in reversed(sizes):
        chunks.append((w, h, data[start:start + size]))
        start += size
    return fmt, list(reversed(chunks))


def bc4(values: list[int]) -> bytes:
    if len(values) != 16:
        raise ValueError("BC4 block must contain 16 samples")
    high, low = max(values), min(values)
    palette = [high, low]
    if high > low:
        palette += [((7 - i) * high + i * low) // 7 for i in range(1, 7)]
    else:
        palette += [high] * 4 + [0, 255]
    bits = 0
    for i, value in enumerate(values):
        index = min(range(8), key=lambda j: abs(palette[j] - value))
        bits |= index << (3 * i)
    return bytes((high, low)) + bits.to_bytes(6, "little")


def bc5_from_packed(image: Image.Image) -> bytes:
    image = image.convert("RGBA")
    pixels = image.load()
    data = bytearray()
    for y in range(0, image.height, 4):
        for x in range(0, image.width, 4):
            block = [pixels[min(image.width - 1, x + dx), min(image.height - 1, y + dy)] for dy in range(4) for dx in range(4)]
            data += bc4([p[3] for p in block])  # proposed MW2 normal X: alpha
            data += bc4([p[1] for p in block])  # proposed MW2 normal Y: green
    return bytes(data)


def convert(main_dir: Path, output: Path) -> list[dict]:
    output.mkdir(parents=True, exist_ok=True)
    entries = [
        ("iw_03.iwd", "images/weapon_beretta_c.iwi", "m9_diffuse.dds", 0),
        ("iw_03.iwd", "images/weapon_beretta_n.iwi", "m9_normal.dds", 36),
        ("iw_05.iwd", "images/~weapon_beretta_s-rgb&weapon_~be02a881.iwi", "m9_specular.dds", 5),
        ("iw_03.iwd", "images/weapon_suppressor_01_col.iwi", "suppressor_diffuse.dds", 0),
        ("iw_03.iwd", "images/weapon_suppressor_01_nml.iwi", "suppressor_normal.dds", 36),
        ("iw_05.iwd", "images/~weapon_suppressor_01_spc-rgb~c8037795.iwi", "suppressor_specular.dds", 5),
    ]
    report = []
    for archive_name, entry_name, filename, tpf_format in entries:
        with ZipFile(main_dir / archive_name) as archive:
            if archive.getinfo(entry_name).file_size > 64 * 1024 * 1024:
                raise ValueError("Oversized source image")
            original = archive.read(entry_name)
        fmt, mips = iwi_blocks(original)
        width, height, top = mips[0]
        fourcc = b"DXT1" if fmt == 11 else b"DXT5"
        if tpf_format == 36:
            payload = []
            for w, h, blocks in mips:
                with Image.open(io.BytesIO(dds_header(w, h, fourcc, len(blocks), 1) + blocks)) as im:
                    payload.append(bc5_from_packed(im))
            converted = dds_header(width, height, b"DX10", len(payload[0]), len(mips))
            converted += struct.pack("<5I", 83, 3, 0, 1, 0) + b"".join(payload)
        else:
            converted = dds_header(width, height, fourcc, len(top), len(mips)) + b"".join(blocks for _, _, blocks in mips)
        with Image.open(io.BytesIO(converted)) as checked:
            if checked.size != (width, height):
                raise ValueError("DDS reload differs")
        (output / filename).write_bytes(converted)
        report.append({
            "archive": archive_name, "entry": entry_name, "source_sha256": hashlib.sha256(original).hexdigest(),
            "dds": filename, "dds_sha256": hashlib.sha256(converted).hexdigest(), "width": width, "height": height,
            "mip_count": len(mips), "tpf_format": tpf_format,
            "lossless_blocks": tpf_format != 36, "normal_mapping": "candidate A->R, G->G" if tpf_format == 36 else None,
            "material_association_verified": False, "runtime_verified": False,
        })
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "converted/mw2-2009/m9/dds")
    args = parser.parse_args()
    result = convert(args.main_dir, args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
