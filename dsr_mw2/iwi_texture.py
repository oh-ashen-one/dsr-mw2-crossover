"""Extract selected MW2 2009 M9 textures from owned IWD archives to local PNGs.

Only IWI version 8 and the formats observed in the original M9 entries are
supported. Source archives are opened read-only; retail pixels stay ignored by
Git. Layout follows Greyhound's CoDIWITranslator.cpp at commit 22c3d17f.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


M9_ENTRIES = (
    ("iw_01.iwd", "images/hud_m9beretta.iwi"),
    ("iw_03.iwd", "images/weapon_m9beretta.iwi"),
    ("iw_03.iwd", "images/weapon_m9beretta_suppressor.iwi"),
    ("iw_03.iwd", "images/weapon_beretta_c.iwi"),
    ("iw_03.iwd", "images/weapon_beretta_n.iwi"),
    ("iw_05.iwd", "images/~weapon_beretta_s-rgb&weapon_~be02a881.iwi"),
)


def _dds(width: int, height: int, fourcc: bytes, pixels: bytes) -> bytes:
    # DDS_HEADER is 31 little-endian uint32s (124 bytes), after "DDS ".
    fields = [124, 0x81007, height, width, len(pixels), 0, 0]
    fields += [0] * 11
    fields += [32, 4, int.from_bytes(fourcc, "little"), 0, 0, 0, 0, 0]
    fields += [0x1000, 0, 0, 0, 0]
    assert len(fields) == 31
    return b"DDS " + struct.pack("<31I", *fields) + pixels


def decode_iwi(data: bytes) -> Image.Image:
    if len(data) < 32 or data[:4] != b"IWi\x08":
        raise ValueError("Expected an IWI version 8 image")
    fmt, flags, width, height = struct.unpack_from("<BBHH", data, 8)
    if not 0 < width <= 8192 or not 0 < height <= 8192 or flags & 4:
        raise ValueError("Unsupported dimensions or cubemap")
    mip1, mip2, _, mip4 = struct.unpack_from("<4I", data, 16)
    offset = 32 if mip1 in (mip2, mip4) else mip2
    if fmt == 1:
        size = width * height * 4
    elif fmt == 11:  # BC1 / DXT1
        size = ((width + 3) // 4) * ((height + 3) // 4) * 8
    elif fmt == 13:  # BC3 / DXT5
        size = ((width + 3) // 4) * ((height + 3) // 4) * 16
    else:
        raise ValueError(f"Unsupported IWI format {fmt}")
    if offset < 32 or offset + size != len(data):
        raise ValueError("Invalid or unexpected top-mip offset/length")
    pixels = data[offset:]
    if fmt == 1:
        return Image.frombytes("RGBA", (width, height), pixels, "raw", "BGRA")
    fourcc = b"DXT1" if fmt == 11 else b"DXT5"
    with Image.open(io.BytesIO(_dds(width, height, fourcc, pixels))) as image:
        return image.convert("RGBA")


def export_m9(main_dir: Path, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for archive_name, entry_name in M9_ENTRIES:
        with ZipFile(main_dir / archive_name) as archive:
            info = archive.getinfo(entry_name)
            if info.file_size > 64 * 1024 * 1024:
                raise ValueError(f"Unexpectedly large IWI: {entry_name}")
            data = archive.read(info)
        image = decode_iwi(data)
        filename = Path(entry_name).stem + ".png"
        image.save(output_dir / filename)
        manifest.append({
            "game": "Call of Duty Modern Warfare 2 (2009)",
            "steam_app_id": 10180,
            "archive": archive_name,
            "entry": entry_name,
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "source_crc32": f"{info.CRC:08x}",
            "png": filename,
            "width": image.width,
            "height": image.height,
        })
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_dir", type=Path, help="Original owned MW2 2009 main/ directory")
    parser.add_argument("--output", type=Path, default=Path("converted/mw2-2009/m9"))
    args = parser.parse_args()
    print(json.dumps(export_m9(args.main_dir, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
