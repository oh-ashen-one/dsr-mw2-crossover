"""Pack prepared M9 material candidates into DSR's native TPF container, offline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from .audit import is_within
from .soulstruct_tools import WORKSPACE, configure


def pack(tpf, texture_root: Path, include_suppressor: bool = False) -> tuple[bytes, dict]:
    from soulstruct.containers import TPF
    records = json.loads((texture_root / "manifest.json").read_text())
    expected = {
        "diffuse": ("iw_03.iwd", "images/weapon_beretta_c.iwi", 0),
        "normal": ("iw_03.iwd", "images/weapon_beretta_n.iwi", 36),
        "specular": ("iw_05.iwd", "images/~weapon_beretta_s-rgb&weapon_~be02a881.iwi", 5),
    }
    suppressor_expected = {
        "diffuse": ("iw_03.iwd", "images/weapon_suppressor_01_col.iwi", 0),
        "normal": ("iw_03.iwd", "images/weapon_suppressor_01_nml.iwi", 36),
        "specular": ("iw_05.iwd", "images/~weapon_suppressor_01_spc-rgb~c8037795.iwi", 5),
    }
    if include_suppressor:
        extras = []
        for texture in tpf.textures:
            clone = copy.deepcopy(texture)
            suffix = "_n" if texture.stem.endswith("_n") else "_s" if texture.stem.endswith("_s") else ""
            clone.stem = "WP_A_1401_suppressor" + suffix
            extras.append(clone)
        tpf.textures.extend(extras)
    for texture in tpf.textures:
        suppressor = "_suppressor" in texture.stem
        prefix = "suppressor" if suppressor else "m9"
        suffix = "normal" if texture.stem.endswith("_n") else "specular" if texture.stem.endswith("_s") else "diffuse"
        matches = [x for x in records if x["dds"] == f"{prefix}_{suffix}.dds"]
        if len(matches) != 1:
            raise ValueError("Expected one material candidate per channel")
        record = matches[0]
        if (record["archive"], record["entry"], record["tpf_format"]) != (suppressor_expected if suppressor else expected)[suffix]:
            raise ValueError("M9 material identity differs from the measured source")
        texture.data = (texture_root / record["dds"]).read_bytes()
        if hashlib.sha256(texture.data).hexdigest() != record["dds_sha256"]:
            raise ValueError("DDS file differs from its local manifest")
        texture.format = record["tpf_format"]
        texture.mipmap_count = record["mip_count"]
    encoded = bytes(tpf)
    check = TPF.from_bytes(encoded)
    for before, after in zip(tpf.textures, check.textures, strict=True):
        if (before.stem, before.format, before.mipmap_count, before.data) != (after.stem, after.format, after.mipmap_count, after.data):
            raise ValueError("Texture container round trip differs")
    return encoded, {
        "textures": len(check.textures), "mip_levels": sum(t.mipmap_count for t in check.textures),
        "native_dsr_container_roundtrip": True, "dds_data_unchanged": True,
        "tpf_sha256": hashlib.sha256(encoded).hexdigest(),
        "normal_channel_mapping": "candidate A/G, not runtime verified", "activated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORKSPACE / "converted/dsr/m9-texture-roundtrip")
    args = parser.parse_args()
    if not is_within(args.output, WORKSPACE / "converted"):
        raise ValueError("Output must stay in this task's converted directory")
    configure()
    from soulstruct.containers import Binder, TPF
    binder = Binder.from_path(WORKSPACE / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx")
    entry = next(e for e in binder.entries if e.path.endswith(".tpf"))
    encoded, report = pack(TPF.from_bytes(entry.get_uncompressed_data()), WORKSPACE / "converted/mw2-2009/m9/dds")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "m9.tpf").write_bytes(encoded)
    (WORKSPACE / "evidence/m9-texture-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
