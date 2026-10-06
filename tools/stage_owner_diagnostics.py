"""Stage only our original read-only probe. Never run Windows or launch a game."""
import json
from pathlib import Path
from dsr_mw2.owner_diagnostics import stage
from dsr_mw2.runtime_paths import bottle_path

if __name__ == '__main__':
    print(json.dumps(stage(Path(__file__).resolve().parents[1], bottle_path()), indent=2))
