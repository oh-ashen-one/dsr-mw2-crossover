"""Apply the task-local AppData adapter to the already installed, approved source.

This script does not download/install packages or launch a Windows tool.
Run with the dedicated .venv Python and the pinned source checkout path.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess

WORKSPACE = Path(__file__).resolve().parents[1]
COMMIT = "12b69189a2ccebbc623a1b6565be89a18d6c9958"
OLD = '_SOULSTRUCT_APPDATA = Path("~/AppData/Roaming/soulstruct").expanduser()'
NEW = 'import os\n_SOULSTRUCT_APPDATA = Path(os.environ["DSR_MW2_TOOL_DATA"]).resolve()'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    head = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    if head != COMMIT:
        raise SystemExit("Soulstruct source revision differs from the approved commit")
    distribution = importlib.metadata.distribution("soulstruct")
    if distribution.version != "2.6.0":
        raise SystemExit("Unexpected Soulstruct distribution version")
    config = Path(distribution.locate_file("soulstruct/config.py"))
    if not config.resolve().is_relative_to((WORKSPACE / ".venv").resolve()):
        raise SystemExit("Use this task's .venv Python; refusing to edit a shared package")
    installed = config.read_text()
    if OLD in installed:
        if installed.count(OLD) != 1:
            raise SystemExit("Unexpected configuration layout")
        config.write_text(installed.replace(OLD, NEW))
    elif NEW not in installed:
        raise SystemExit("Unknown Soulstruct config; refusing to patch")
    data = WORKSPACE / "tooling-local/soulstruct"
    data.mkdir(parents=True, exist_ok=True)
    report = {
        "commit": COMMIT, "version": distribution.version, "source": str(args.source.resolve()),
        "adapter": "Require DSR_MW2_TOOL_DATA and place logs/config under this task", "config": str(config),
    }
    (WORKSPACE / "tooling-local/soulstruct-install.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Task-local Soulstruct adapter prepared")


if __name__ == "__main__":
    main()
