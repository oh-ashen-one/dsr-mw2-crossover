"""Bind an offline M9 export to copied IW4 fastfile and pinned extractor bytes.

This module never executes an extractor. Approval and observed execution remain
separate from the file/provenance checks performed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from .audit import is_within
from .obj_geometry import parse

WORKSPACE = Path(__file__).resolve().parents[1]
EXTRACTOR_SHA = "f7ee888b026a4f7d47a7e74b83c3e08022d61e0a2776efaa51c168741c78a94a"
SOURCE_COMMIT = "7d027e8f89118196713e955b0e11f8404149c54d"
SOURCE_PATCH_SHA = "fbc898d1320f418e8d9191f0b6a5a14118691bc32882eced466b6985e84ec241"
COPIES = WORKSPACE / "profiles/dsr-mw2/drive_c/Assets/mw2-2009/zone/english"
EXTRACTOR = WORKSPACE / "tooling-local/OpenAssetTools-v0.33.0-mw2-native64/Unlinker"
FASTFILES = {"common.ff", "common_mp.ff", "af_caves.ff"}
MAPS = {
    "map_Kd": "weapon_beretta_c.dds",
    "map_bump": "weapon_beretta_n.dds",
    "map_Ks": "~weapon_beretta_s-rgb&weapon_~be02a881.dds",
}
MATERIAL_MAPS = {
    "mc/mtl_weapon_beretta": MAPS,
    "mtl_weapon_beretta": MAPS,
    "mc/mtl_weapon_suppressor_b": {
        "map_Kd": "weapon_suppressor_01_col.dds",
        "map_bump": "weapon_suppressor_01_nml.dds",
        "map_Ks": "~weapon_suppressor_01_spc-rgb~c8037795.dds",
    },
}
MATERIALS = set(MATERIAL_MAPS)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def extractor_identity() -> str:
    """Permit a locally rebuilt pinned source; never trust an arbitrary binary."""
    receipt = WORKSPACE / 'tooling-local/extractor-build.json'
    if not receipt.exists():
        return EXTRACTOR_SHA  # historical build identity, useful for fixtures
    if receipt.is_symlink():
        raise ValueError('Extractor receipt is redirected')
    data = json.loads(receipt.read_text())
    if (data.get('source_commit') != SOURCE_COMMIT or
            data.get('patch_sha256') != SOURCE_PATCH_SHA or
            data.get('source_diff_sha256') != SOURCE_PATCH_SHA or
            not re.fullmatch(r'[0-9a-f]{64}', data.get('binary_sha256', ''))):
        raise ValueError('Extractor build is not the pinned source repair')
    return data['binary_sha256']


def attachment_points(export: Path, fastfile: Path) -> dict:
    if not is_within(export, WORKSPACE / "converted") or export.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("External or oversized bone export")
    text = export.read_text()
    if "// Game Origin: IW4" not in text.splitlines() or f"// Zone Origin: {fastfile.stem}" not in text.splitlines():
        raise ValueError("Bone export origin differs")
    points = {}
    for index, name, key in ((1, "j_pistol_grip", "grip_obj"), (5, "tag_flash", "muzzle_obj"), (3, "tag_flash_silenced", "suppressed_muzzle_obj")):
        if not re.search(rf'^BONE {index} [0-9]+ "{name}"$', text, re.M):
            raise ValueError("M9 attachment bone identity differs")
        match = re.search(rf"^BONE {index}\nOFFSET ([^\n]+)$", text, re.M)
        if not match:
            raise ValueError("Missing M9 attachment transform")
        xyz = tuple(float(value) for value in match[1].split(", "))
        if len(xyz) != 3 or not all(math.isfinite(value) and abs(value) < 50 for value in xyz):
            raise ValueError("Invalid M9 attachment transform")
        # OAT converts CoD's Z-up basis to OBJ's Y-up basis.
        points[key] = [xyz[0], xyz[2], -xyz[1]]
    return {"bone_export_sha256": digest(export), **points}


def inspect_export(obj: Path, fastfile: Path) -> dict:
    if not is_within(obj, WORKSPACE / "converted") or obj.name != "weapon_beretta_lod0.obj":
        raise ValueError("Expected the task-local original weapon_beretta highest-LOD OBJ")
    if not is_within(fastfile, COPIES) or fastfile.name not in FASTFILES:
        raise ValueError("Expected one of the three task-local approved fastfile copies")
    expected_extractor = extractor_identity()
    if digest(EXTRACTOR) != expected_extractor:
        raise ValueError("Native extractor bytes differ from the recorded approved source repair")
    if obj.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Oversized model export")
    text = obj.read_text()
    if "# game origin: iw4" not in text.lower().splitlines() or f"# Zone Origin: {fastfile.stem}" not in text.splitlines():
        raise ValueError("OBJ game/zone origin does not match the copied IW4 fastfile")
    if "mtllib weapon_beretta.mtl" not in text.splitlines():
        raise ValueError("Expected the original M9 material-library reference")
    geometry = parse(text)
    if not set(geometry["groups"]).issubset(MATERIALS):
        raise ValueError("Unverified M9 material association")
    mtl = obj.with_name("weapon_beretta.mtl")
    if not is_within(mtl, obj.parent) or mtl.stat().st_size > 1024 * 1024:
        raise ValueError("External or oversized material metadata")
    materials, current = {}, None
    for line in mtl.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "newmtl" and len(fields) == 2 and fields[1] in MATERIALS:
            current = fields[1]
            if current in materials:
                raise ValueError("Duplicate material metadata")
            materials[current] = {}
        elif fields[0] in MAPS and len(fields) == 2 and current:
            # Only inspect the exact exporter-written names; never follow image
            # references or arbitrary material file paths.
            expected = MATERIAL_MAPS[current]
            if fields[1] != "../images/" + expected[fields[0]] or fields[0] in materials[current]:
                raise ValueError("M9 texture relationship differs from the prepared source textures")
            materials[current][fields[0]] = expected[fields[0]]
        else:
            raise ValueError("Unexpected exported material statement")
    if set(materials) != set(geometry["groups"]) or any(m != MATERIAL_MAPS[name] for name, m in materials.items()):
        raise ValueError("Incomplete M9 material/texture relationships")
    report = {
        "steam_app_id": 10180, "model_asset_name": "weapon_beretta", "lod": 0,
        "extractor_sha256": expected_extractor, "fastfile_name": fastfile.name,
        "extractor_source_commit": SOURCE_COMMIT, "extractor_source_patch_sha256": SOURCE_PATCH_SHA,
        "fastfile_sha256": digest(fastfile), "obj_sha256": digest(obj),
        "material_metadata_sha256": digest(mtl), "material_texture_names": materials,
        "obj_origin_checked": True, "material_relationships_checked": True,
        "runtime_verified": False,
    }
    bone_export = obj.with_suffix(".xmodel_export")
    if bone_export.exists():
        report["attachment_points"] = attachment_points(bone_export, fastfile)
    return report


def verify(obj: Path, proof: dict) -> dict:
    name = proof.get("fastfile_name")
    if name not in FASTFILES:
        raise ValueError("Copied source fastfile identity missing")
    actual = inspect_export(obj, COPIES / name)
    if proof != actual:
        raise ValueError("Export provenance differs from current source/export bytes")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--fastfile", choices=sorted(FASTFILES), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect_export(args.obj, COPIES / args.fastfile)
    output = args.output or args.obj.with_name("weapon_beretta-provenance.json")
    if not is_within(output, WORKSPACE / "converted"):
        raise ValueError("Provenance output must stay in this task's converted folder")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"provenance": str(output), "model_asset_name": report["model_asset_name"], "runtime_verified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
