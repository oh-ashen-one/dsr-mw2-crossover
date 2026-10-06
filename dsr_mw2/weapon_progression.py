"""Keep the M9's setup consistent across native Light Crossbow ascensions.

DSR stores reinforcement levels in ReinforceParamWeapon; these six weapon rows
are the base and ascension families. Preserve native costs, materials, origins,
level multipliers, movesets and elemental proportions. This creates no new route.
"""
FAMILIES = {
    1250000: "", 1250100: "Crystal", 1250200: "Lightning",
    1250400: "Magic", 1250600: "Divine", 1250800: "Fire",
}
DAMAGE_FIELDS = ("BasePhysicalDamage", "BaseMagicDamage", "BaseFireDamage", "BaseLightningDamage")


def edits(rows: dict, preset: dict) -> list[tuple[int, dict]]:
    actual = {key for key, row in rows.items() if row.WeaponModel == 1401}
    if actual != set(FAMILIES) or rows[1250000].BasePhysicalDamage != 50:
        raise ValueError("Unexpected native Light Crossbow family; refusing partial progression patch")
    changes = []
    for row_id in FAMILIES:
        row = rows[row_id]
        if row.WeaponCategory != 11 or row.UsesEquippedBolts != 1:
            raise ValueError("Ascension row is no longer a native bolt crossbow")
        # Integer half-up rounding preserves zero-valued elements and avoids
        # floating rounding ambiguity for the 70-damage preset's 1.4x scaling.
        fields = {field: (getattr(row, field) * preset["physical_damage"] + 25) // 50
                  for field in DAMAGE_FIELDS}
        fields.update(Weight=preset["weight"], RequiredStrength=preset["required_strength"],
                      RequiredDexterity=preset["required_dexterity"])
        changes.append((row_id, fields))
    return changes
