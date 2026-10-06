"""Require the pinned, task-local Soulstruct adapter before any import side effects."""

from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
COMMIT = "12b69189a2ccebbc623a1b6565be89a18d6c9958"
ADAPTER = 'Path(os.environ["DSR_MW2_TOOL_DATA"]).resolve()'


def configure():
    record = json.loads((WORKSPACE / "tooling-local/soulstruct-install.json").read_text())
    if record.get("commit") != COMMIT or record.get("version") != "2.6.0":
        raise ValueError("Unexpected Soulstruct revision")
    distribution = importlib.metadata.distribution("soulstruct")
    config_path = Path(distribution.locate_file("soulstruct/config.py"))
    if distribution.version != "2.6.0" or not config_path.resolve().is_relative_to((WORKSPACE / ".venv").resolve()):
        raise ValueError("Use the approved Soulstruct install in this task's .venv")
    # Soulstruct creates its log/config directory during import. Check the adapter
    # on disk first so an accidental reinstall cannot write into the Mac home.
    if ADAPTER not in config_path.read_text():
        raise ValueError("Task-local AppData adapter missing; run tools/prepare_soulstruct.py")
    data = WORKSPACE / "tooling-local/soulstruct"
    os.environ["DSR_MW2_TOOL_DATA"] = str(data)
    from soulstruct.config import Config, _SOULSTRUCT_APPDATA
    if Path(_SOULSTRUCT_APPDATA).resolve() != data.resolve():
        raise ValueError("Soulstruct is using an unexpected AppData directory")
    Config.CONSOLE_LOG_LEVEL = "ERROR"
    Config.setup_log()
    return Config
