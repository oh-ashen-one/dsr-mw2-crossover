"""Launch only the isolated native DSR copy under the Studio's shared GPU lock."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

from .install_private import WORKSPACE, PRESETS, inspect_install, install
from .profile import guard, command, environment
from .runtime_paths import bottle_path
from .steam_mode import configure as configure_steam_mode
from .process_ownership import processes, bottle_processes as owned_processes
from .native_runtime import check as check_native_runtime
from .install_audio import check as check_audio
from .save_banks import inspect as inspect_save_banks, select_locked as select_save_bank
from .owner_diagnostics import start as start_read_only_diagnostics
from .window_controls import start as start_window_controls

BOTTLE = bottle_path()
from .local_config import path as configured_path
GPU = configured_path("gpu_dir", WORKSPACE / "tooling-local/gpu")
# Windows infrastructure that is never a competing renderer.
QUIET_WINDOWS = re.compile(r"(?i)steamwebhelper|steamservice|steam\.exe|wineserver|winedevice|services\.exe|"
                           r"explorer\.exe|plugplay|rpcss|svchost|winemenubuilder|conhost|start\.exe|DarkSoulsRemastered")


def busy_windows_programs() -> list[str]:
    """Other CrossOver programs using CPU, e.g. a game or Unreal editor (shared-slot rule)."""
    busy = []
    for line in subprocess.check_output(["ps", "-axo", "%cpu=,command="], text=True).splitlines():
        match = re.match(r"\s*([\d.]+)\s+(.*)$", line)
        if match and re.search(r"(?i)[A-Z]:\\.*\.exe", match.group(2)) and not QUIET_WINDOWS.search(match.group(2)) \
                and float(match.group(1)) >= 5.0:
            busy.append(match.group(2)[:80])
    return busy
STEAM = BOTTLE / "drive_c/Program Files (x86)/Steam"
SANDBOX = WORKSPACE / "tools/dsr-offline.sb"
ENGINES = {"gta5.exe", "gta5_enhanced.exe", "eldenring.exe", "darksoulsremastered.exe",
           "unrealeditor", "unrealgame", "unity", "godot", "blender"}
OWNER_RESERVATION = "OWNER RESERVATION: DSR-MW2 startup and owner play; background renders remain paused.\n"
M9_MODES = {'m9', 'm9-test'}


def is_engine(name: str) -> bool:
    path = name.replace("\\", "/")
    # ~/.unity/bin/unity is the Unity command-line/MCP bridge, not an editor or renderer.
    if path.lower().endswith("/.unity/bin/unity"):
        return False
    return path.split("/")[-1].lower() in ENGINES


def native_input_trial(mode: str) -> bool:
    return mode == 'm9-test' and os.environ.get('DSR_MW2_NATIVE_INPUT_TRIAL') == 'validation-v1'


def owner_reserved() -> bool:
    pause = GPU / "PAUSED"
    return pause.is_file() and pause.read_text() == OWNER_RESERVATION


def gpu_percent() -> int | None:
    output = subprocess.check_output(["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"], text=True)
    values = [int(x) for x in re.findall(r'"Device Utilization %"\s*=\s*(\d+)', output)]
    return max(values) if values else None


def network_wrapper(mode: str) -> list[str]:
    # A first-run entitlement check may need connected Steam. This exception
    # only runs the hash-checked unmodified baseline; the M9 is always offline.
    return [] if mode in {"steam-login", "stock-online"} else ["/usr/bin/sandbox-exec", "-f", str(SANDBOX)]


def bottle_processes() -> list[int]:
    return owned_processes(BOTTLE)


def game_processes() -> list[int]:
    owned = set(bottle_processes())
    return [pid for pid, _, name in processes() if pid in owned and
            name.replace("\\", "/").split("/")[-1].lower() == "darksoulsremastered.exe"]


def steam_processes() -> list[int]:
    owned = set(bottle_processes())
    return [pid for pid, _, name in processes() if pid in owned and
            name.replace('\\', '/').split('/')[-1].lower() == 'steam.exe']


def preflight(mode: str) -> dict:
    blockers = guard(BOTTLE)
    try:
        inspect_save_banks(BOTTLE)
    except (OSError, ValueError) as exc:
        blockers.append('Private save separation failed: '+str(exc))
    if mode == 'm9-test':
        from .validation_session import verify
        try:
            verify(BOTTLE)
        except (OSError, ValueError, RuntimeError) as exc:
            blockers.append('Disposable validation save check failed: ' + str(exc))
    if mode != "steam-login" and (GPU / "PAUSED").exists() and not owner_reserved():
        blockers.append("The Studio coordinator has paused game launches: " + (GPU / "PAUSED").read_text().strip())
    if mode != "steam-login":
        for program in busy_windows_programs():
            blockers.append("Another game or renderer is active (CrossOver): " + program)
    if mode != "steam-login" and (not (GPU / "bin/gpu_slot.py").is_file() or not (GPU / "locks/perf.lock").is_file()):
        blockers.append("The active shared renderer protocol is unavailable")
    if Path("/dev/console").owner() != Path.home().owner():
        blockers.append("The owner desktop is not logged in")
    chip = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    if chip != "Apple M3 Ultra":
        blockers.append("This launcher is configured for the M3 Ultra Studio")
    for pid, state, name in processes():
        if mode != "steam-login" and is_engine(name):
            blockers.append(f"Another game or renderer is active (PID {pid}); it will not be interrupted")
    if bottle_processes():
        blockers.append("A process already owns this private bottle; preserve it before a fresh offline launch")
    from .action_trial import check as check_action_trial, permitted as permitted_action_trial
    blockers.extend(check_action_trial(mode))
    if os.environ.get('DSR_MW2_VIEWMODEL_TRIAL'):
        try:
            from .owner_test import viewmodel_check
            if not native_input_trial(mode) or os.environ.get('DSR_MW2_VIEWMODEL_TRIAL')!='source-vm-v1':
                raise ValueError('Viewmodel requires the private offline gun-test gate')
            viewmodel_check()
        except (OSError,ValueError,KeyError) as exc:
            blockers.append('Viewmodel preparation failed: '+str(exc))
    state = inspect_install(action_trial=permitted_action_trial(mode))
    if mode != "steam-login":
        blockers.extend(check_native_runtime(BOTTLE / "drive_c/Games/Dark Souls Remastered"))
        if mode in M9_MODES:
            blockers.extend(check_native_runtime(BOTTLE / "drive_c/Games/DSR-MW2", input_trial=native_input_trial(mode)))
    if mode != "steam-login" and not state.get("stock_baseline_preserved"):
        blockers.append("The private stock baseline has changed")
    if mode in M9_MODES and (not state.get("installed") or not state.get("stock_baseline_preserved")):
        blockers.append("The private native candidate or its stock baseline has changed" +
                        (": " + state["error"] if state.get("error") else ""))
    if mode in M9_MODES:
        from .mpeg_audio_trial import check as check_mpeg_trial
        mpeg_trial = check_mpeg_trial(mode)
        audio = mpeg_trial if mpeg_trial is not None else check_audio()
        if not audio.get("valid"):
            blockers.append("Private audio verification failed: " + audio.get("error", "unknown error"))
        elif audio.get('runtime_rejected'):
            blockers.append('The installed audio bank is the observed FMOD-crashing candidate; restore stock audio')
    # Only presence is inspected. Never print/parse cached account identifiers or tokens.
    if mode != "steam-login" and not (STEAM / "config/loginusers.vdf").is_file():
        blockers.append("The private Steam client has not completed its first sign-in")
    return {"mode": mode, "blockers": blockers, "game_launched": False, "runtime_verified": False}


def watch_game(process: subprocess.Popen, timeout: float = 300, on_started=None) -> bool:
    """Follow Steam's asynchronous startup, then wait for the native game to exit."""
    started = time.monotonic()
    seen_game = False
    while True:
        games = game_processes()
        if games:
            if not seen_game:
                print(json.dumps({"status": "native_game_process_started", "pids": games,
                                  "visual_readiness_verified": False}), flush=True)
                if on_started is not None:
                    print(json.dumps(on_started(games)), flush=True)
            seen_game = True
        elif (seen_game or time.monotonic() - started >= timeout or
              (time.monotonic() - started >= 15 and process.poll() is not None and not bottle_processes())):
            return seen_game
        time.sleep(3)


def run_inside(mode: str) -> int:
    check = preflight(mode)
    print(json.dumps(check, indent=2), flush=True)
    if check["blockers"]:
        return 75
    if mode != "steam-login" and (os.environ.get("GPU_SLOT_HELD") != "perf" or os.environ.get("GPU_SLOT_DIR") != str(GPU)):
        raise ValueError("Exclusive shared GPU slot is missing")
    out = WORKSPACE / "tooling-local/launch"
    out.mkdir(exist_ok=True)
    env = environment()
    # Every M9 process is born under the IP restriction. The unmodified online
    # baseline is a separate diagnostic. A pre-existing server is refused above.
    if mode == "steam-login":
        cmd = command(r"C:\Program Files (x86)\Steam\Steam.exe")
        cwd = STEAM
    else:
        folder = "DSR-MW2" if mode in M9_MODES else "Dark Souls Remastered"
        # Steam queues the app launch until its client is ready and sets up the
        # native license/IPC context. Direct EXE startup raced authentication.
        # A task-local diagnostic switch changes only Steam UI rendering. It
        # does not disable CEF sandboxing or change game/global GPU settings.
        ui_args = ["-cef-disable-gpu"] if os.environ.get("DSR_MW2_STEAM_SOFTWARE_UI", "1") == "1" else []
        cmd = [*network_wrapper(mode), *command(
            r"C:\Program Files (x86)\Steam\Steam.exe", *ui_args, "-silent", "-applaunch", "570940",
            dll_overrides='xinput1_3=n,b' if native_input_trial(mode) else None,
            graphics_backend='d3dmetal' if mode in M9_MODES else None,
            seh_trace=native_input_trial(mode) and os.environ.get('DSR_MW2_SEH_TRACE')=='validation-v1')]
        cwd = BOTTLE / "drive_c/Games" / folder
    with (BOTTLE / ".dsr-mw2-session.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Recheck after locking: a chooser may have changed the install, or a
        # separately opened private process may have appeared since preflight.
        check = preflight(mode)
        if check["blockers"]:
            print(json.dumps(check, indent=2), flush=True)
            return 75
        # A connected sign-in-only session must never expose the M9 bank
        # to Steam Cloud either. This runs before any Steam process starts.
        # Even a connected sign-in-only session gets the unmodified library
        # target, so its Play button cannot launch M9 with the stock save bank.
        alias = STEAM / "steamapps/common/DARK SOULS REMASTERED"
        allowed = {BOTTLE / "drive_c/Games" / name for name in ("DSR-MW2", "Dark Souls Remastered")}
        if not alias.is_symlink() or alias.resolve() not in allowed:
            raise ValueError("Private Steam library alias changed; preserving it")
        replacement = alias.with_name(".dsr-mw2-library-link")
        if replacement.exists() or replacement.is_symlink():
            raise ValueError("Another library switch is pending")
        select_save_bank(BOTTLE, 'validation' if mode == 'm9-test' else ('m9' if mode == 'm9' else 'stock'))
        if mode == 'm9-test':
            from .validation_session import verify
            verify(BOTTLE, active=True)
        if mode != "steam-login":
            configure_steam_mode(STEAM / "config/loginusers.vdf", offline=mode != "stock-online")
        library_target = BOTTLE / "drive_c/Games" / ('DSR-MW2' if mode in M9_MODES else 'Dark Souls Remastered')
        replacement.symlink_to(os.path.relpath(library_target, alias.parent), target_is_directory=True)
        os.replace(replacement, alias)
        with (out / f"{mode}.log").open("a") as log:
            log.write(f"\nSession {mode} at {time.time()}\n")
            log.flush()
            process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            (out / "process.json").write_text(json.dumps({"pid": process.pid, "mode": mode, "bottle": str(BOTTLE)}, indent=2))
            started_game = mode == "steam-login"
            shutdown = None
            diagnostic_children = []
            if mode != "steam-login":
                def started(pids):
                    diagnostic = start_read_only_diagnostics(
                        mode, pids, WORKSPACE, BOTTLE, network_wrapper(mode), diagnostic_children)
                    window = start_window_controls(
                        mode, pids, WORKSPACE, BOTTLE, network_wrapper(mode), diagnostic_children)
                    return {**diagnostic, 'window_controls': window}
                diagnostics = started if mode in M9_MODES else None
                started_game = watch_game(process, on_started=diagnostics)
                if not started_game:
                    print(json.dumps({"status": "steam_did_not_start_native_game", "runtime_verified": False}), flush=True)
                # On a failed dispatch, shut down our Steam too. Otherwise a
                # successful Steam exit can mask failure and its UI holds the
                # renderer indefinitely. No other bottle is addressed.
                if steam_processes():
                    shutdown = subprocess.Popen([*network_wrapper(mode),
                        *command(r"C:\Program Files (x86)\Steam\Steam.exe", "-shutdown")],
                        cwd=STEAM, env=env, stdout=log, stderr=subprocess.STDOUT)
            # Steam/Wine may fork away from the command. Retain the renderer lock
            # while any process still owns this bottle. Tell the owner if normal
            # shutdown stalls, including when the original Steam process lives.
            waiting_since = time.monotonic()
            explained_wait = False
            while (process.poll() is None or (shutdown is not None and shutdown.poll() is None) or
                   any(child.poll() is None for child in diagnostic_children) or bottle_processes()):
                if mode != "steam-login" and not explained_wait and time.monotonic() - waiting_since >= 30:
                    print(json.dumps({"status": "waiting_for_private_shutdown", "runtime_verified": False}), flush=True)
                    explained_wait = True
                time.sleep(3)
            rc = process.wait()
        if mode == 'm9-test':
            from .validation_session import verify
            verify(BOTTLE, active=True)
            select_save_bank(BOTTLE, 'm9')
            print(json.dumps({'status': 'owner_save_restored', **verify(BOTTLE)}), flush=True)
    return rc if started_game else 70


def run_reserved(mode: str) -> int:
    """Use the actual exclusive lock while the owner's background pause stays intact."""
    with (GPU / "locks/perf.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another session holds the shared renderer lock", flush=True)
            return 75
        holder = GPU / "holders" / f"perf-{os.getpid()}.json"
        record = {"pid": os.getpid(), "start": subprocess.check_output(
            ["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True).strip(),
            "class": "perf", "slot": "perf", "label": "dsr-mw2-owner-exclusive",
            "state": "settling", "since_epoch": time.time(), "cmd": "DSR owner startup; no automatic playthrough"}
        holder.write_text(json.dumps(record))
        try:
            deadline, calm_since = time.monotonic() + 60, None
            while True:
                check = preflight(mode)
                if not owner_reserved() or check["blockers"]:
                    print(json.dumps(check), flush=True)
                    return 75
                percent = gpu_percent()
                if percent is None or not 0 <= percent < 30:
                    calm_since = None
                elif calm_since is None:
                    calm_since = time.monotonic()
                elif time.monotonic() - calm_since >= 12:
                    break
                if time.monotonic() >= deadline:
                    print(json.dumps({"status": "no_stable_gpu_headroom", "gpu_percent": percent}), flush=True)
                    return 75
                time.sleep(2)
            record["state"] = "running"
            holder.write_text(json.dumps(record))
            env = environment()
            env.update(GPU_SLOT_HELD="perf", GPU_SLOT_DIR=str(GPU))
            return subprocess.run([sys.executable, "-B", "-m", "dsr_mw2.launch",
                                   "--mode", mode, "--inside-slot"], env=env, cwd=WORKSPACE).returncode
        finally:
            holder.unlink(missing_ok=True)
            fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("m9", "m9-test", "stock", "stock-online", "steam-login"), default="m9")
    parser.add_argument("--preset", choices=PRESETS)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--inside-slot", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check:
        report = preflight(args.mode)
        print(json.dumps(report, indent=2))
        return 75 if report["blockers"] else 0
    if args.inside_slot:
        return run_inside(args.mode)
    report = preflight(args.mode)
    print(json.dumps(report, indent=2), flush=True)
    if report["blockers"]:
        return 75  # No queued launch, retry, or pause bypass.
    if args.mode == "steam-login":
        # Account UI alone is not a game/engine launch and claims no renderer slot.
        # It never starts DSR. Gameplay retains its pause and exclusive-slot gates.
        return run_inside(args.mode)
    if args.preset:
        install(WORKSPACE, args.preset)
    if owner_reserved():
        return run_reserved(args.mode)
    env = environment()
    env.update(GPU_SLOT_DIR=str(GPU), GPU_SLOT_PERF_MAX_HOLD="0", GPU_SLOT_SAMPLE_INTERVAL="15")
    cmd = [sys.executable, str(GPU / "bin/gpu_slot.py"), "perf", "--label", "dsr-mw2-private",
           "--timeout", "60", "--", sys.executable, "-B", "-m", "dsr_mw2.launch",
           "--mode", args.mode, "--inside-slot"]
    return subprocess.run(cmd, env=env, cwd=WORKSPACE).returncode


if __name__ == "__main__":
    raise SystemExit(main())
