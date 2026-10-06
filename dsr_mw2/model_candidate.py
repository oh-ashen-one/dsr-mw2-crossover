"""Verify an inactive converted M9 binder and its still-local export provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .audit import is_within
from .asset_provenance import verify

WORKSPACE = Path(__file__).resolve().parents[1]
PARTS = Path("parts/WP_A_1401.partsbnd.dcx")


def read(folder: Path) -> tuple[dict, bytes]:
    if not is_within(folder, WORKSPACE / "converted"):
        raise ValueError("Model candidate must stay inside this task's converted folder")
    report_path, candidate = folder / "model-report.json", folder / PARTS
    if not is_within(report_path, folder) or not is_within(candidate, folder):
        raise ValueError("Model candidate contains an external symlink")
    report = json.loads(report_path.read_text())
    if report.get("authentic_asset_provenance_verified") is not True or report.get("activated") is not False or report.get("runtime_verified") is not False:
        raise ValueError("Expected an inactive model with checked export provenance")
    relative = report.get("export_obj_relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Task-local source OBJ identity missing")
    obj = WORKSPACE / "converted" / relative
    if not is_within(obj, WORKSPACE / "converted"):
        raise ValueError("Model source escapes task converted folder")
    verify(obj, report["source"])
    data = candidate.read_bytes()
    if hashlib.sha256(data).hexdigest() != report["output_sha256"]:
        raise ValueError("Converted model binder differs from its checked report")
    return report, data
