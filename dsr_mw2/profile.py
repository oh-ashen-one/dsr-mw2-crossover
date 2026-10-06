"""Read-only checks and the verified direct CrossOver entry point."""

from __future__ import annotations

import os
import json
from pathlib import Path
import stat
import string

from .audit import is_within
from .runtime_paths import bottle_path

WORKSPACE = Path(__file__).resolve().parents[1]
from .local_config import path as configured_path
CX = configured_path("crossover_app", "/Applications/CrossOver.app") / "Contents/SharedSupport/CrossOver"
RESERVATION = b"DSR-MW2: reserved; no host device\n"


def save_path_guard(bottle: Path) -> list[str]:
    """Check Windows' actual Documents selectors as well as the POSIX folder.

    Read only Personal values from the private registry. Never print or copy
    account registry values. No disposable/game save is written by this check.
    """
    try:
        expected = {
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders": r"C:\users\crossover\Documents",
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders": r"%USERPROFILE%\Documents",
        }
        registry = bottle / "user.reg"
        if registry.is_symlink() or not is_within(registry, bottle):
            return ["Private Documents registry is outside this bottle"]
        personal = {}
        section = ""
        for line in registry.read_text().splitlines():
            if line.startswith("["):
                section = line[1:].split("]", 1)[0].replace("\\\\", "\\")
            elif section in expected and line.startswith('"Personal"='):
                if section in personal:
                    return ["Private Documents registry selectors are ambiguous"]
                personal[section] = json.loads(line.split("=", 1)[1].removeprefix("str(2):"))
        if personal != expected:
            return ["Windows Documents no longer selects the verified private folder"]
        documents = bottle / "drive_c/users/crossover/Documents"
        nbgi = documents / "NBGI"
        if nbgi.is_symlink() or not is_within(nbgi, documents):
            return ["Native DSR save parent points outside private Documents"]
        # Also reject a link beneath the save parent (including per-account
        # directories or an individual SL2). Never enumerate an external target.
        if nbgi.exists() and any(p.is_symlink() for p in nbgi.rglob("*")):
            return ["A native DSR save path contains an unverified redirect"]
    except (OSError, ValueError) as exc:
        return ["Private save-path check failed: " + str(exc)]
    return []


def guard(bottle: Path) -> list[str]:
    reasons = []
    devices = bottle / "dosdevices"
    user = bottle / "drive_c/users/crossover"
    if bottle.is_symlink() or bottle != bottle_path() or bottle.resolve() != bottle:
        return ["Profile is outside this task"]
    try:
        expected = {"c:"} | {letter + "::" for letter in string.ascii_lowercase if letter != "c"}
        if {p.name for p in devices.iterdir()} != expected:
            reasons.append("Drive reservations changed")
        if not (devices / "c:").is_symlink() or (devices / "c:").resolve() != bottle / "drive_c":
            reasons.append("C: does not resolve to the private game profile")
        for name in expected - {"c:"}:
            p = devices / name
            if p.is_symlink() or not p.is_file() or p.read_bytes() != RESERVATION:
                reasons.append("A reserved device slot changed")
                break
        for folder in (devices, user):
            if not folder.stat().st_flags & stat.UF_IMMUTABLE:
                reasons.append("Private path protection is no longer enabled")
        for name in ("Documents", "Desktop", "Downloads", "Pictures", "Music", "Videos", "AppData"):
            p = user / name
            if p.is_symlink() or not p.is_dir() or not is_within(p, bottle):
                reasons.append("A Windows user folder points outside the private profile")
    except OSError as exc:
        reasons.append(f"Private profile check failed: {exc}")
    reasons.extend(save_path_guard(bottle))
    return reasons


def command(executable: str, *args: str, dll_overrides: str | None = None, seh_trace: bool = False,
            graphics_backend: str | None = None) -> list[str]:
    # --cx-app / --wl-app enter winewrapper.exe, which crashed in this profile.
    # This installed, trusted Unix Wine entry point passed two fresh console boots.
    overrides = []
    if dll_overrides is not None:
        if dll_overrides != 'xinput1_3=n,b':
            raise ValueError('Only the scoped original XInput trial override is supported')
        # CrossOver bin/wine deletes inherited WINEDLLOVERRIDES at line716.
        # Its supported --dll option sets the child value after that cleanup.
        overrides = ['--dll', dll_overrides]
    debug = ['--debugmsg','-all,+seh'] if seh_trace else []
    graphics = []
    if graphics_backend is not None:
        if graphics_backend != 'd3dmetal':
            raise ValueError('Unsupported private graphics backend')
        # CrossOver's installed wine wrapper applies --env after bottle settings.
        # This affects only this launch and its children, never global settings.
        graphics = ['--env', 'CX_GRAPHICS_BACKEND=d3dmetal']
    return [str(CX / "bin/wine"), "--bottle", "dsr-mw2", "--no-gui", "--no-update", *overrides, *debug, *graphics,
            "--ux-app", str(CX / "lib/wine/x86_64-unix/wine"), executable, *args]


def environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("WINE", "CX_", "GPU_SLOT_")):
            env.pop(key)
    env.update(CX_BOTTLE_PATH=str(bottle_path().parent), CX_BOTTLE="dsr-mw2", WINEDEBUG="-all")
    return env
