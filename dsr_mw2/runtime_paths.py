"""Resolve only this task's explicitly recorded private runtime location."""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
LOCAL_BOTTLE = WORKSPACE / "profiles/dsr-mw2"


def bottle_path(workspace: Path = WORKSPACE) -> Path:
    receipt = workspace / "profiles/runtime-location.json"
    if workspace.resolve() == WORKSPACE and receipt.is_file():
        if receipt.is_symlink():
            raise ValueError("Runtime location receipt may not be a symlink")
        recorded = Path(json.loads(receipt.read_text())["bottle"])
        if recorded != LOCAL_BOTTLE or recorded.is_symlink() or recorded.resolve() != LOCAL_BOTTLE:
            raise ValueError("Runtime location is not this task's fixed private profile")
        return recorded
    return workspace / "profiles/dsr-mw2"
