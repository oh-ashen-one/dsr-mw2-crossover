"""Validate offline loadout candidates. They are not runtime-verified MW2 weapons."""

from __future__ import annotations

import json
import math
from pathlib import Path


ALLOWED_KEYS = {
    "name", "description", "physical_damage", "weight", "required_strength",
    "required_dexterity", "projectile_speed", "gravity", "ammo_count", "starter_classes",
}


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != ALLOWED_KEYS:
        raise ValueError("Loadout must have exactly the documented fields")
    if not isinstance(data["name"], str) or not data["name"].isascii() or not data["name"]:
        raise ValueError("Loadout name must be nonempty ASCII")
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in data["name"]):
        raise ValueError("Loadout name must be a simple lowercase filename")
    if not isinstance(data["description"], str):
        raise ValueError("Description must be a string")
    for name, lower, upper in (
        ("physical_damage", 1, 300), ("required_strength", 1, 30),
        ("required_dexterity", 1, 30), ("ammo_count", 1, 999),
    ):
        value = data[name]
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    for name, lower, upper in (("weight", .1, 10), ("projectile_speed", 20, 60), ("gravity", 0, 5)):
        value = data[name]
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{name} must be finite and in [{lower}, {upper}]")
    classes = data["starter_classes"]
    if not isinstance(classes, list) or not classes or any(type(c) is not int or c not in range(2000, 2010) for c in classes):
        raise ValueError("starter_classes must contain new-character class IDs 2000–2009")
    if len(set(classes)) != len(classes):
        raise ValueError("Duplicate starter class")
    return data
