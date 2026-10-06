"""Prepare explicit prototype equipment text in both native DSR English FMG sets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .audit import is_within
from .soulstruct_tools import WORKSPACE, configure
from .model_candidate import read as read_model
from .weapon_progression import FAMILIES

RELATIVE = Path("msg/ENGLISH/item.msgbnd.dcx")


def build(output: Path, model: Path | None = None) -> dict:
    if not is_within(output, WORKSPACE / "converted"):
        raise ValueError("Output must stay in this task's converted directory")
    model_report = read_model(model)[0] if model else None
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.text.fmg import FMG
    source = WORKSPACE / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered" / RELATIVE
    original = source.read_bytes()
    binder = Binder.from_bytes(original)
    originals = [(e.entry_id, e.path, e.flags, e.data) for e in binder.entries]
    edits = {
        11: "M9 setup (crossbow prototype)", 115: "M9 setup (crossbow prototype)",
        21: "Native DSR projectile test setup.", 114: "Native DSR projectile test setup.",
        25: "Native crossbow mechanics candidate.\nGun model is not included in this package.\nUses standard bolts and single-shot loading.",
        106: "Native crossbow mechanics candidate.\nGun model is not included in this package.\nUses standard bolts and single-shot loading.",
    }
    if model_report:
        suppressed = model_report["attachment"] == "original suppressor"
        for key in (11, 115):
            edits[key] = "MW2 M9 suppressed (prototype)" if suppressed else "MW2 M9 (crossbow prototype)"
        for key in (21, 114):
            edits[key] = "MW2 M9 model, native DSR crossbow action."
        for key in (25, 106):
            edits[key] = "Original MW2 M9 model in a DSR crossbow prototype.\nUses standard bolts and single-shot loading.\nMW2 magazine reload and ADS are not implemented."
            if suppressed:
                edits[key] += "\nOriginal suppressor model; no sound/damage suppression effect."
    for entry in binder.entries:
        if entry.entry_id not in edits:
            continue
        table = FMG.from_bytes(entry.get_uncompressed_data())
        before = dict(table.entries)
        if not set(FAMILIES).issubset(table.entries):
            raise ValueError("Expected native Light Crossbow family text row missing")
        for row_id, prefix in FAMILIES.items():
            text = edits[entry.entry_id]
            if prefix and entry.entry_id in (11, 115):
                text = prefix + " " + text
            table.entries[row_id] = text
        encoded = bytes(table)
        check = FMG.from_bytes(encoded)
        if set(check.entries) != set(before) or any(check.entries[k] != table.entries[k] for k in FAMILIES):
            raise ValueError("Equipment text round trip differs")
        if any(check.entries[k] != v for k, v in before.items() if k not in FAMILIES):
            raise ValueError("Untouched equipment text changed")
        entry.set_uncompressed_data(encoded)
    candidate = bytes(binder)
    check = Binder.from_bytes(candidate)
    unchanged = []
    for old, new in zip(originals, check.entries, strict=True):
        if old[:3] != (new.entry_id, new.path, new.flags):
            raise ValueError("Message binder metadata changed")
        if new.entry_id not in edits:
            if new.data != old[3]:
                raise ValueError("Untouched message binder member changed")
            unchanged.append(new.entry_id)
    target = output / RELATIVE
    if any(not is_within(p, output) for p in (target, output / "text-report.json")):
        raise ValueError("Equipment text output contains an external symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate)
    report = {
        "source_sha256": hashlib.sha256(original).hexdigest(), "output_sha256": hashlib.sha256(candidate).hexdigest(),
        "edited_binder_entry_ids": list(edits), "edited_text_id": 1250000, "edited_text_ids": list(FAMILIES),
        "unchanged_binder_entry_ids": unchanged, "label": edits[11],
        "authentic_gun_mesh_present": model_report is not None,
        "model_candidate_sha256": model_report["output_sha256"] if model_report else None,
        "runtime_verified": False, "activated": False,
    }
    (output / "text-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Checked authentic M9 candidate; never a placeholder")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (args.model / "equipment-text" if args.model else WORKSPACE / "converted/dsr/prototype-text")
    print(json.dumps(build(output, args.model), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
