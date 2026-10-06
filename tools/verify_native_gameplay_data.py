"""Lightweight, read-only native-data and negative checks. Never launch a game."""
from datetime import datetime, timezone
import json

from dsr_mw2.soulstruct_tools import WORKSPACE, configure
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.install_private import PRESETS, STOCK_HASHES, checked_package, inspect_install, sha
from dsr_mw2.native_audit import verify_parameters, verify_equipment_text
from dsr_mw2.loadouts import load


def main():
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    from dsr_mw2.param_patch import patch_row

    relative = "param/GameParam/GameParam.parambnd.dcx"
    stock_path = bottle_path() / "drive_c/Games/Dark Souls Remastered" / relative
    if sha(stock_path) != STOCK_HASHES[relative]:
        raise ValueError("Unknown native DSR baseline")
    stock = stock_path.read_bytes()
    text_relative = "msg/ENGLISH/item.msgbnd.dcx"
    text_path = bottle_path() / "drive_c/Games/Dark Souls Remastered" / text_relative
    if sha(text_path) != STOCK_HASHES[text_relative]:
        raise ValueError("Unknown native DSR English text baseline")
    stock_text = text_path.read_bytes()
    results = []
    for name in PRESETS:
        package = checked_package(WORKSPACE, name)
        definition = load(WORKSPACE / "loadouts" / (name.removesuffix("-suppressed") + ".json"))
        results.append({"preset": name, **verify_parameters(stock, package[relative], definition),
                        "equipment_text": verify_equipment_text(stock_text, package[text_relative], name.endswith("-suppressed"))})

    # These deliberately wrong binders exist in memory only. Check that the
    # independent audit rejects changes hidden inside otherwise valid containers.
    source = checked_package(WORKSPACE, "m9-sidearm")[relative]
    preset = load(WORKSPACE / "loadouts/m9-sidearm.json")
    negatives = []
    for table, row_id, field, value in (
        ("Bullet", 600, "IsMapPiercing", 1),
        ("AtkParam_Pc", 2050, "IgnoreInvincibilityFrames", 1),
        ("CharaInitParam", 2000, "RightHandWeapon1", -1),
        ("CharaInitParam", 2000, "RightHandWeapon1", 212000),
        ("EquipParamWeapon", 2100000, "BasePhysicalDamage", 999),
        ("EquipParamWeapon", 1250100, "RequiredStrength", 10),
    ):
        binder = Binder.from_bytes(source)
        parsed = GameParamBND.from_bytes(source)
        rows = {k.rsplit("\\", 1)[-1]: v for k, v in parsed.params.items()}
        row = rows[table][row_id]
        before = bytes(row)
        setattr(row, field, value)
        entry = next(e for e in binder.entries if e.path.rsplit("\\", 1)[-1] == table + ".param")
        raw, _ = patch_row(entry.get_uncompressed_data(), row_id, before, bytes(row))
        entry.set_uncompressed_data(raw)
        try:
            verify_parameters(stock, bytes(binder), preset)
        except ValueError as exc:
            negatives.append({"table": table, "row": row_id, "field": field, "rejected": True, "reason": str(exc)})
        else:
            raise ValueError(f"Audit accepted invalid native data: {table}/{field}")
    installed = inspect_install()
    if not installed["installed"] or not installed["stock_baseline_preserved"]:
        raise ValueError("Installed private candidate no longer matches a checked package")
    report = {"at": datetime.now(timezone.utc).isoformat(), "packages": results,
              "invalid_native_mutations_rejected": negatives, "installation": installed,
              "source_sha256": STOCK_HASHES[relative], "game_launched": False,
              "runtime_verified": False,
              "scope": "Actual native parameter bytes; no rendering, input, collision or gameplay was exercised",
              "limitations": ["Native crossbow actions and bolt VFX remain", "Standard Bolt tuning is shared with other users of Bullet 600",
                              "Native ascension/reinforcement routes are preserved, not new MW2 attachment mechanics",
                              "MW2 magazine/reload/ADS/animation/audio remain unimplemented"]}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
