"""Stage hash-pinned runtime files as data, with no execution or account copying."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile

from .audit import is_within, read_manifest

WORKSPACE = Path(__file__).resolve().parents[1]
BOTTLE = WORKSPACE / "profiles/dsr-mw2"
from .local_config import path as configured_path
SOURCE_STEAM = configured_path("source_steam", WORKSPACE / "retail/Steam")
ARCHIVE = Path("/tmp/dsr-shader-overhaul-0.2.1.zip")
ARCHIVE_HASH = "cba7ce62a2062f55a31a1b0d1c02b4e47848fc32df3df5b860257ccb0b17e701"
FILES = {
    "modengine2_launcher.exe": "da6ab6a56a799245547e2d18f3f9cd6e5f07700535a83525f887fc93b7113e68",
    "modengine2/bin/modengine2.dll": "09f9c8ca1a3fd93399c277ec78173e1af28be98fedc94cead04cb1346e4b2976",
    "modengine2/bin/lua.dll": "49583880e35dd0adb1b6e1c0318f7031f1931412becbc55837f20b928cf91c0e",
    "modengine2/crashpad/crashpad_handler.exe": "f13b6130c2211eeb1bf5b5652f9fffac8f85d1c1740872f2d5d97529c4f5d97f",
    "modengine2/crashpad/zlib1.dll": "7522a213bb6b9112aac8f7392ce050bfdb11fe5d78a021f3f85ebca2397b5cea",
}


def write_local(path: Path, data: bytes):
    if not is_within(path, BOTTLE):
        raise ValueError("Runtime staging path escapes this task bottle")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() != data:
        raise ValueError(f"Existing task runtime differs; preserving it: {path.name}")
    path.write_bytes(data)


def main() -> int:
    raise RuntimeError("Historical loader-staging research is disabled; follow docs/SETUP.md for the native file route")
    if not BOTTLE.is_dir() or not is_within(BOTTLE, WORKSPACE):
        raise ValueError("Expected the existing task-owned bottle")
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARCHIVE_HASH:
        raise ValueError("Loader archive differs from the inspected release")
    root = BOTTLE / "drive_c/Tools/DSR-MW2"
    staged = []
    with ZipFile(ARCHIVE) as archive:
        for relative, expected in FILES.items():
            data = archive.read("ModEngine2/" + relative)
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise ValueError(f"Pinned loader member differs: {relative}")
            write_local(root / relative, data)
            staged.append({"path": relative, "sha256": actual, "bytes": len(data)})
    config = (WORKSPACE / "config_dsr_offline.toml").read_text().replace(
        '{ enabled = true, name = "dsr-mw2", path = "mod" }',
        '{ enabled = false, name = "dsr-mw2", path = "mod" }',
    )
    write_local(root / "config_dsr_stock.toml", config.encode())
    (root / "mod").mkdir(exist_ok=True)

    # Copy only installed Steam program bytes. Never copy config/loginusers,
    # userdata, cookies, ssfn, cloud settings or any account-bearing directory.
    client = SOURCE_STEAM / "Steam.exe"
    client_data = client.read_bytes()
    task_steam = BOTTLE / "drive_c/Program Files (x86)/Steam"
    write_local(task_steam / "Steam.exe", client_data)
    game = BOTTLE / "drive_c/Games/Dark Souls Remastered"
    alias = task_steam / "steamapps/common/DARK SOULS REMASTERED"
    if not game.is_dir() or not is_within(game, BOTTLE):
        raise ValueError("Task-owned DSR copy missing")
    alias.parent.mkdir(parents=True, exist_ok=True)
    if alias.is_symlink():
        if alias.resolve() != game.resolve():
            raise ValueError("Existing Steam game link points elsewhere")
    elif alias.exists():
        raise ValueError("Existing Steam game directory found; preserving it")
    else:
        alias.symlink_to(os.path.relpath(game, alias.parent), target_is_directory=True)
    from .steam_manifest import installed_dsr_manifest
    manifest = installed_dsr_manifest((SOURCE_STEAM / "steamapps/appmanifest_570940.acf").read_text())
    write_local(task_steam / "steamapps/appmanifest_570940.acf", manifest.encode())
    report = {
        "files": staged, "archive_sha256": ARCHIVE_HASH,
        "steam_program_sha256": hashlib.sha256(client_data).hexdigest(),
        "steam_program_bytes": len(client_data), "account_state_copied": False,
        "steam_client_started": False, "steam_login_verified": False,
        "task_game_link_resolves_local": is_within(alias, BOTTLE),
        "loader_execution_approved": False, "executed": False, "activated": False,
        "excluded": ["shader overhaul", "ScyllaHide", "debug-menu assets", "updaters", "account data", "retail saves"],
    }
    write_local(root / "STAGED-NOT-EXECUTED.json", (json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
