"""Inspect installed game state and CrossOver save-path isolation without launching games."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from .runtime_paths import bottle_path


APPS = {
    "dsr": ("570940", "DARK SOULS REMASTERED", "DarkSoulsRemastered.exe"),
    "mw2_2009": ("10180", "Call of Duty Modern Warfare 2", "iw4sp.exe"),
}


def read_manifest(path: Path) -> dict[str, str]:
    """Read only the top-level scalar ACF fields needed for a conservative gate."""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {}
    return dict(re.findall(r'^\s*"([^"\n]+)"\s+"([^"\n]*)"\s*$', data, re.MULTILINE))


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def inspect(steamapps: Path, bottle: Path, workspace: Path) -> dict:
    games = {}
    for key, (appid, fallback_dir, exe) in APPS.items():
        manifest = read_manifest(steamapps / f"appmanifest_{appid}.acf")
        install_dir = manifest.get("installdir", fallback_dir)
        game_root = steamapps / "common" / install_dir
        exe_path = game_root / exe
        games[key] = {
            "appid": appid,
            "name": manifest.get("name"),
            "state_flags": manifest.get("StateFlags"),
            "bytes_downloaded": manifest.get("BytesDownloaded"),
            "exe_exists": exe_path.is_file(),
            "installed": manifest.get("appid") == appid
            and manifest.get("StateFlags") == "4"
            and exe_path.is_file(),
        }

    documents = bottle / "drive_c" / "users" / "crossover" / "Documents"
    actual_documents = documents.resolve(strict=False)
    devices = bottle / "dosdevices"
    mappings = {
        path.name: str(path.resolve(strict=False))
        for path in devices.iterdir() if path.is_symlink()
    } if devices.is_dir() else {}
    external_mappings = {
        name: target for name, target in mappings.items()
        if not is_within(Path(target), bottle)
    }
    state_path = bottle / ".dsr-mw2-isolation.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    profile = {
        "bottle_is_task_owned": is_within(bottle, workspace) or bottle == bottle_path(workspace),
        "windows_documents": str(documents),
        "resolved_documents": str(actual_documents),
        "resolves_in_workspace": is_within(documents, workspace),
        "resolves_in_private_profile": is_within(documents, bottle),
        "directory_exists": actual_documents.is_dir(),
        "game_save_write_verified": False,
        "drive_mappings": mappings,
        "external_drive_mappings": external_mappings,
        "drive_mappings_checked": devices.is_dir(),
        "os_sandbox_verified": False,
        "external_mapping_recreated": bool(state.get("external_mapping_recreated", False)),
        "drive_mapping_persistence_verified": bool(state.get("drive_mapping_persistence_verified", False)),
        "windows_documents_probe_verified": bool(state.get("windows_documents_probe_verified", False)),
        "startup_console_verified": bool(state.get("startup_console_verified", False)),
        "device_reservations": state.get("device_reservations", 0),
    }
    profile["filesystem_isolated"] = (
        profile["bottle_is_task_owned"]
        and profile["resolves_in_private_profile"]
        and profile["directory_exists"]
        and profile["drive_mappings_checked"]
        and not external_mappings
    )

    return {
        "games": games,
        "profile": profile,
        "safe_for_runtime_investigation": all(g["installed"] for g in games.values())
        and profile["filesystem_isolated"]
        and (not profile["external_mapping_recreated"] or profile["drive_mapping_persistence_verified"]),
        "playable_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steamapps", type=Path, required=True)
    parser.add_argument("--bottle", type=Path, required=True, help="Task-owned CrossOver bottle; never the shared Steam bottle")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = inspect(args.steamapps, args.bottle, args.workspace)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["safe_for_runtime_investigation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
