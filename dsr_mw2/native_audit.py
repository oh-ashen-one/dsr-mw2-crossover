"""Independently check the native weapon/ammo/impact chain in a prepared PARAM binder.

This does not call the builder or trust its change report. It compares actual
native rows, table bytes and routing against the pinned unmodified DSR input.
It proves data consistency only; collision and animations still need gameplay.
"""
from __future__ import annotations

import copy
import hashlib
import struct


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def tables(parsed) -> dict:
    return {name.rsplit("\\", 1)[-1]: table for name, table in parsed.params.items()}


def verify_parameters(stock: bytes, candidate: bytes, preset: dict) -> dict:
    # The caller must configure the approved task-local Soulstruct before import.
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND

    old_binder, new_binder = Binder.from_bytes(stock), Binder.from_bytes(candidate)
    old = tables(GameParamBND.from_bytes(stock))
    new = tables(GameParamBND.from_bytes(candidate))
    require(len(old_binder.entries) == len(new_binder.entries), "Native binder entry count changed")
    require(set(old) == set(new), "Native parameter tables changed")

    weapon = new["EquipParamWeapon"][1250000]
    for name, expected in {"WeaponModel": 1401, "WeaponModelCategory": 7, "WeaponCategory": 11,
                           "AttackAnimationCategory": 46, "UsesEquippedBolts": 1,
                           "UsesEquippedArrows": 0, "BehaviorVariationID": 4600}.items():
        require(getattr(weapon, name) == expected, f"M9 lost native crossbow routing: {name}")
    ammo = new["EquipParamWeapon"][2100000]
    require(ammo.BehaviorVariationID == 1100, "Standard Bolt behavior variation changed")
    require(bytes(ammo) == bytes(old["EquipParamWeapon"][2100000]), "Standard Bolt weapon row changed")
    behavior_ids = (101100300, 101100400)
    for row_id in behavior_ids:
        behavior = new["BehaviorParam_PC"][row_id]
        require(behavior.VariationID == ammo.BehaviorVariationID
                and behavior.ReferenceType == 1 and behavior.ReferenceID == 600,
                f"Equipped ammo no longer routes through native Bullet 600: {row_id}")
    bullet = new["Bullet"][600]
    require(bullet.BulletAttack == 2050 and bullet.BulletCount == 1,
            "Standard Bolt native impact routing changed")
    require(bullet.IsMapPiercing == 0 and bullet.PiercesTargets == 0
            and bullet.IsEndlessHit == 0 and bullet.HitsBothTeams == 0,
            "Projectile collision or target filtering changed")
    require(abs(bullet.InitialHitRadius - .02) < 1e-6, "Native projectile hit radius changed")
    attack = new["AtkParam_Pc"][bullet.BulletAttack]
    require(attack.IsPhysicalProjectile == 1 and attack.IgnoreInvincibilityFrames == 0
            and attack.IgnoreGuard == 0 and attack.MapHitType == 1,
            "Impact attack no longer retains native collision/defense behavior")

    # Exact allowed field changes, specified here independently of build_params.
    families = (1250000, 1250100, 1250200, 1250400, 1250600, 1250800)
    require({key for key, row in old["EquipParamWeapon"].rows.items() if row.WeaponModel == 1401} == set(families),
            "Unknown native crossbow ascension family")
    family_edits = {}
    for row_id in families:
        stock_row = old["EquipParamWeapon"][row_id]
        family_edits[row_id] = {field: int(getattr(stock_row, field) * preset["physical_damage"] / 50 + .5)
                               for field in ("BasePhysicalDamage", "BaseMagicDamage", "BaseFireDamage", "BaseLightningDamage")}
        family_edits[row_id].update(Weight=preset["weight"], RequiredStrength=preset["required_strength"],
                                   RequiredDexterity=preset["required_dexterity"])
    edits = {
        "EquipParamWeapon": family_edits,
        "Bullet": {600: {
            "InitialSpeed": preset["projectile_speed"], "MinSpeed": preset["projectile_speed"],
            "MaxSpeed": preset["projectile_speed"], "GravityBeforeAttenuation": preset["gravity"],
            "GravityAfterAttenuation": preset["gravity"], "AccelerationBeforeAttenuation": 0.0,
            "AccelerationAfterAttenuation": 0.0,
        }},
        "CharaInitParam": {row_id: {"RightHandWeapon1": 1250000,
                                     "RightHandWeapon2": old["CharaInitParam"][row_id].RightHandWeapon1,
                                     "BoltSlot1": 2100000,
                                     "BoltSlot1Count": preset["ammo_count"]}
                           for row_id in preset["starter_classes"]},
    }
    unchanged = []
    for before, after in zip(old_binder.entries, new_binder.entries, strict=True):
        require((before.entry_id, before.path, before.flags) == (after.entry_id, after.path, after.flags),
                "Native binder metadata/order changed")
        table_name = before.path.rsplit("\\", 1)[-1].removesuffix(".param")
        original, actual = before.get_uncompressed_data(), after.get_uncompressed_data()
        if table_name not in edits:
            require(before.data == after.data, f"Unrelated native table changed: {table_name}")
            unchanged.append(table_name)
            continue
        # Retain every raw header, duplicate ID, name and unselected row. Only
        # exact typed replacement bytes at unique original offsets are allowed.
        expected_bytes = bytearray(original)
        count = struct.unpack_from("<H", original, 10)[0]
        for row_id, changes in edits[table_name].items():
            offsets = [struct.unpack_from("<iII", original, 48 + i * 12) for i in range(count)]
            matches = [offset for row, offset, _ in offsets if row == row_id]
            require(len(matches) == 1, f"Ambiguous native row: {table_name}/{row_id}")
            row = copy.deepcopy(old[table_name][row_id])
            offset = matches[0]
            require(original[offset:offset + len(bytes(row))] == bytes(row), "Native row does not round-trip")
            for field, value in changes.items():
                setattr(row, field, value)
            require(bytes(new[table_name][row_id]) == bytes(row),
                    f"Unexpected native row fields: {table_name}/{row_id}")
            expected_bytes[offset:offset + len(bytes(row))] = bytes(row)
        require(actual == expected_bytes, f"Unselected row/header bytes changed: {table_name}")

    starts = []
    for row_id in preset["starter_classes"]:
        row = new["CharaInitParam"][row_id]
        require(row.Strength >= weapon.RequiredStrength and row.Dexterity >= weapon.RequiredDexterity,
                f"Starting class cannot wield the prepared sidearm: {row_id}")
        starts.append({"class_id": row_id, "right_hand_slot_1": row.RightHandWeapon1,
                       "right_hand_slot_2": row.RightHandWeapon2,
                       "bolt_slot_1": row.BoltSlot1, "bolt_count": row.BoltSlot1Count,
                       "meets_weapon_requirements": True})
    return {
        "sha256": hashlib.sha256(candidate).hexdigest(),
        "weapon_row": 1250000, "model_id": weapon.WeaponModel, "ammo_row": 2100000,
        "ammo_behavior_rows": list(behavior_ids), "projectile_row": 600, "impact_attack_row": 2050,
        "base_weapon_damage": weapon.BasePhysicalDamage, "base_ammo_damage": ammo.BasePhysicalDamage,
        "initial_speed": bullet.InitialSpeed, "native_hit_radius": bullet.InitialHitRadius,
        "native_collision_flags_preserved": True, "unchanged_tables": unchanged,
        "only_intended_fields_changed": True, "new_character_starts": starts,
        "weapon_family_rows": list(families), "native_reinforcement_table_and_origins_preserved": True,
        "runtime_verified": False,
    }


def verify_equipment_text(stock: bytes, candidate: bytes, suppressed: bool) -> dict:
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.text.fmg import FMG

    original, changed = Binder.from_bytes(stock), Binder.from_bytes(candidate)
    families = {1250000: "", 1250100: "Crystal ", 1250200: "Lightning ",
                1250400: "Magic ", 1250600: "Divine ", 1250800: "Fire "}
    text_ids = {11, 115, 21, 114, 25, 106}
    require(len(original.entries) == len(changed.entries), "Equipment message binder count changed")
    visited = set()
    label = "MW2 M9 suppressed (prototype)" if suppressed else "MW2 M9 (crossbow prototype)"
    for before, after in zip(original.entries, changed.entries, strict=True):
        require((before.entry_id, before.path, before.flags) == (after.entry_id, after.path, after.flags),
                "Equipment message binder metadata changed")
        if before.entry_id not in text_ids:
            require(before.data == after.data, "Unrelated equipment message table changed")
            continue
        visited.add(before.entry_id)
        a, b = FMG.from_bytes(before.get_uncompressed_data()), FMG.from_bytes(after.get_uncompressed_data())
        require(set(a.entries) == set(b.entries), "Equipment text inventory changed")
        for key, text in a.entries.items():
            if key not in families:
                require(b.entries[key] == text, "Unrelated equipment text changed")
            elif before.entry_id in {11, 115}:
                require(b.entries[key] == families[key] + label, "M9 ascension/attachment name is wrong")
            elif before.entry_id in {21, 114}:
                require(b.entries[key] == "MW2 M9 model, native DSR crossbow action.", "M9 summary is wrong")
            else:
                require("Uses standard bolts and single-shot loading." in b.entries[key]
                        and "MW2 magazine reload and ADS are not implemented." in b.entries[key],
                        "M9 description omits its actual action limitations")
                require(("no sound/damage suppression effect" in b.entries[key]) == suppressed,
                        "M9 attachment description is wrong")
    require(visited == text_ids, "Expected native equipment text table is missing")
    return {"family_rows": list(families), "fmg_tables": sorted(visited), "attachment_names_match": True,
            "other_equipment_text_preserved": True}
