"""Package inactive native DSR mechanics candidates; never copy into a live mod root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib

from .audit import is_within
from .loadouts import load
from .model_candidate import read as read_model, PARTS

WORKSPACE = Path(__file__).resolve().parents[1]
PARAM = Path("param/GameParam/GameParam.parambnd.dcx")
TEXT = Path("msg/ENGLISH/item.msgbnd.dcx")


def verified(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Candidate hash differs: {path.name}")
    return data


def package(preset: Path, output: Path | None = None, model: Path | None = None) -> dict:
    loadout = load(preset)
    output = output or WORKSPACE / "converted/packages" / loadout["name"]
    if not is_within(output, WORKSPACE / "converted/packages"):
        raise ValueError("Packages must stay inside this task's converted/packages folder")
    source = WORKSPACE / "converted/dsr" / loadout["name"]
    params = json.loads((source / "build-report.json").read_text())
    if params["loadout"] != loadout or params["activated"] or params["runtime_verified"]:
        raise ValueError("Expected the matching inactive mechanics candidate")
    model_report, model_bytes = read_model(model) if model else (None, None)
    text_source = model / "equipment-text" if model else WORKSPACE / "converted/dsr/prototype-text"
    texts = json.loads((text_source / "text-report.json").read_text())
    if model_report and (texts.get("authentic_gun_mesh_present") is not True or texts.get("model_candidate_sha256") != model_report["output_sha256"]):
        raise ValueError("Equipment text does not match this authentic model candidate")
    if not model_report and texts.get("authentic_gun_mesh_present"):
        raise ValueError("Gun-model text cannot accompany a mechanics-only package")
    contents = {
        PARAM: verified(source / "mod" / PARAM, params["output_sha256"]),
        TEXT: verified(text_source / TEXT, texts["output_sha256"]),
    }
    if model_report:
        contents[PARTS] = model_bytes
    # An inactive mod list allows inspection/selection without silently activating
    # a half-finished crossover or replacing the owner's stock baseline.
    config = (WORKSPACE / "config_dsr_offline.toml").read_text().replace(
        '{ enabled = true, name = "dsr-mw2", path = "mod" }',
        '{ enabled = false, name = "dsr-mw2", path = "mod" }',
    )
    parsed = tomllib.loads(config)
    if any(m["enabled"] for m in parsed["extension"]["mod_loader"]["mods"]):
        raise ValueError("Packaged candidate must remain disabled")
    destinations = [Path("mod") / p for p in contents]
    destinations += [Path(p) for p in ("config_dsr_candidate.toml", "READ-ME-FIRST.txt", "manifest.json")]
    if any(not is_within(output / relative, output) for relative in destinations):
        raise ValueError("Package contains an external symlink")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for relative, data in contents.items():
        target = output / "mod" / relative
        if not is_within(target, output):
            raise ValueError("Package contains an external symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({"path": str(Path("mod") / relative), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    (output / "config_dsr_candidate.toml").write_text(config)
    visual = (
        "An authentic M9 model candidate is included with checked export provenance.\n"
        "Hand placement, materials and firing are NOT runtime verified.\n"
        if model_report else
        "This mechanics-only package excludes the gun model and retains the stock\n"
        "DSR crossbow model.\n"
    )
    readme = (
        f"{loadout['name']} — inactive DSR crossbow action candidate\n\n"
        + visual +
        "Uses stock DSR crossbow actions, native projectiles and a configurable\n"
        "starting sidearm/bolt setup for NEW characters. No save is edited.\n\n"
        "Use only the task-owned native installer and private profile.\n"
        "The direct native-file route needs no experimental loader.\n"
        "The agent owns remaining setup; gameplay remains unverified.\n\n"
        "The mod list is intentionally disabled. No executable is included here.\n"
        "See docs/MORNING-TEST.md for the integration checkpoint.\n"
    )
    (output / "READ-ME-FIRST.txt").write_text(readme)
    report = {
        "loadout": loadout, "files": records, "label": texts["label"],
        "mechanics_only": model_report is None, "authentic_mw2_model_present": model_report is not None,
        "model_provenance": model_report["source"] if model_report else None,
        "model_attachment": model_report.get("attachment") if model_report else None,
        "handling": "Stock DSR crossbow action; no MW2 magazine reload, ADS or player animation retargeting",
        "config_mod_enabled": False, "activated": False, "runtime_verified": False,
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loadout", type=Path, default=WORKSPACE / "loadouts/m9-sidearm.json")
    parser.add_argument("--model", type=Path, help="Include only a checked authentic M9 model candidate")
    parser.add_argument("--output", type=Path, help="Alternative inactive package folder inside converted/packages")
    args = parser.parse_args()
    report = package(args.loadout, output=args.output, model=args.model)
    print(json.dumps({"package": str(args.output or WORKSPACE / "converted/packages" / report["loadout"]["name"]), "files": report["files"], "activated": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
