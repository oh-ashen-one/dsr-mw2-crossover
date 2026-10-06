"""Build a local DSR crossbow mechanics candidate using the approved Soulstruct source.

The authentic M9 model/animations are not supplied by this parameter build. Nothing
is activated or launched; files are staged in converted/dsr for later owner testing.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from . import loadouts
from .audit import is_within
from .param_patch import patch_row
from .soulstruct_tools import configure
from .weapon_progression import edits as weapon_edits
from .install_private import STOCK_HASHES

WORKSPACE = Path(__file__).resolve().parents[1]
SOULSTRUCT_COMMIT = "12b69189a2ccebbc623a1b6565be89a18d6c9958"
PARAM_RELATIVE = Path("param/GameParam/GameParam.parambnd.dcx")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(source: Path, preset_path: Path, output: Path) -> dict:
    if not source.is_file():
        raise ValueError(f"Source file missing: {source}")
    if not is_within(output, WORKSPACE / "converted") or is_within(source, output):
        raise ValueError("Output must be under this workspace's converted directory and separate from the source")
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND

    preset = loadouts.load(preset_path)
    source_bytes = source.read_bytes()
    if digest(source_bytes) != STOCK_HASHES[str(PARAM_RELATIVE)]:
        raise ValueError("Unexpected DSR source revision; preserve it and review compatibility first")
    binder = Binder.from_bytes(source_bytes)
    parsed = GameParamBND.from_bytes(source_bytes)
    tables = {k.rsplit("\\", 1)[-1]: v for k, v in parsed.params.items()}
    original_entries = [(e.entry_id, e.path, e.flags, e.data) for e in binder.entries]
    changes = []
    patches: dict[str, list[tuple[int, dict]]] = {
        "EquipParamWeapon": weapon_edits(tables["EquipParamWeapon"].rows, preset),
        "Bullet": [(600, {
            "InitialSpeed": preset["projectile_speed"], "MaxSpeed": preset["projectile_speed"],
            "MinSpeed": preset["projectile_speed"], "AccelerationBeforeAttenuation": 0.0,
            "AccelerationAfterAttenuation": 0.0, "GravityBeforeAttenuation": preset["gravity"],
            "GravityAfterAttenuation": preset["gravity"],
        })],
        "CharaInitParam": [(c, {
            "RightHandWeapon1": 1250000,
            "RightHandWeapon2": tables["CharaInitParam"][c].RightHandWeapon1,
            "BoltSlot1": 2100000, "BoltSlot1Count": preset["ammo_count"],
        }) for c in preset["starter_classes"]],
    }
    # Ammo behavior, impact attack, collision radius, map piercing, boss/NPC data,
    # base stats and other equipment stay stock. Keep the original starting sword
    # in slot 2, so future characters begin with the crossover weapon selected.
    for table_name, edits in patches.items():
        entry = next(e for e in binder.entries if e.path.rsplit("\\", 1)[-1] == table_name + ".param")
        raw = entry.get_uncompressed_data()
        for row_id, fields in edits:
            row = tables[table_name][row_id]
            original = bytes(row)
            replacement = copy.deepcopy(row)
            values = {}
            for field, value in fields.items():
                previous = getattr(replacement, field)
                setattr(replacement, field, value)
                values[field] = {"before": previous, "after": value}
            raw, offset = patch_row(raw, row_id, original, bytes(replacement))
            changes.append({"table": table_name, "row_id": row_id, "offset": offset, "fields": values})
        entry.set_uncompressed_data(raw)
    candidate = bytes(binder)
    check = Binder.from_bytes(candidate)
    if len(check.entries) != len(original_entries):
        raise ValueError("Binder entry count changed")
    checked_tables = {k.rsplit("\\", 1)[-1]: v for k, v in GameParamBND.from_bytes(candidate).params.items()}
    expected_changed = {n + ".param" for n in patches}
    untouched = []
    for old, new in zip(original_entries, check.entries, strict=True):
        entry_id, path, flags, data = old
        if (entry_id, path, flags) != (new.entry_id, new.path, new.flags):
            raise ValueError("Binder metadata/order changed")
        if path.rsplit("\\", 1)[-1] not in expected_changed:
            if data != new.data:
                raise ValueError(f"Untouched binder entry changed: {path}")
            untouched.append({"entry_id": entry_id, "name": path.rsplit("\\", 1)[-1], "sha256": digest(data)})
    for change in changes:
        row = checked_tables[change["table"]][change["row_id"]]
        for field, values in change["fields"].items():
            actual = getattr(row, field)
            expected = values["after"]
            if abs(actual - expected) > 1e-5:
                raise ValueError(f"Reloaded field differs: {field}")
    # Verify exactly the selected byte spans changed in each modified PARAM.
    for table_name in patches:
        old_data = next(o[3] for o in original_entries if o[1].rsplit("\\", 1)[-1] == table_name + ".param")
        new_data = next(e.data for e in check.entries if e.path.rsplit("\\", 1)[-1] == table_name + ".param")
        if len(old_data) != len(new_data):
            raise ValueError("PARAM size changed")
        spans = [(c["offset"], c["offset"] + len(bytes(tables[table_name][c["row_id"]]))) for c in changes if c["table"] == table_name]
        if any(a != b and not any(start <= i < end for start, end in spans) for i, (a, b) in enumerate(zip(old_data, new_data))):
            raise ValueError("Bytes outside selected rows changed")
    target = output / "mod" / PARAM_RELATIVE
    if any(not is_within(p, output) for p in (target, output / "build-report.json")):
        raise ValueError("Candidate output contains an external symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate)
    report = {
        "loadout": preset, "source_sha256": digest(source_bytes), "output_sha256": digest(candidate),
        "soulstruct_commit": SOULSTRUCT_COMMIT, "binder_entries": len(check.entries),
        "untouched_entries_verified": untouched, "changes": changes,
        "native_weapon_row": 1250000, "native_ammo_row": 2100000, "native_projectile_row": 600,
        "native_weapon_family_rows": [row_id for row_id, _ in patches["EquipParamWeapon"]],
        "progression": "Native upgrade paths/costs/multipliers preserved; all Light Crossbow families retain proportional M9 damage, weight and requirements",
        "native_impact_attack_row": 2050, "source_file_unchanged": source.read_bytes() == source_bytes,
        "authentic_mw2_model_present": False, "activated": False, "runtime_verified": False,
        "handling": "Stock DSR crossbow action, single-shot load, standard bolts; no MW2 magazine, ADS or reload animation",
        "affects": "Light Crossbow, Standard Bolt projectile and selected NEW character starts; existing saves receive no items",
    }
    (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=WORKSPACE / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered" / PARAM_RELATIVE)
    parser.add_argument("--loadout", type=Path, default=WORKSPACE / "loadouts/m9-sidearm.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    name = loadouts.load(args.loadout)["name"]
    output = args.output or WORKSPACE / "converted/dsr" / name
    result = build(args.source, args.loadout, output)
    print(json.dumps({"output": str(output), "sha256": result["output_sha256"], "unchanged_entries": len(result["untouched_entries_verified"]), "runtime_verified": False, "authentic_mw2_model_present": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
