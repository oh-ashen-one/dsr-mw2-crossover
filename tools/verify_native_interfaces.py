"""Read only the private stock executable; write a report to stdout."""
from datetime import datetime, timezone
import json
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.native_interfaces import inspect


def main():
    exe = bottle_path() / "drive_c/Games/Dark Souls Remastered/DarkSoulsRemastered.exe"
    if exe.is_symlink():
        raise ValueError("Private stock executable cannot be a symlink")
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **inspect(exe.read_bytes()),
                      "game_launched": False, "runtime_binary_installed": False}, indent=2))


if __name__ == "__main__":
    main()
