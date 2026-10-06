"""Short owner-facing entry point; detailed launch output stays task-local."""
from __future__ import annotations

import json
import subprocess
import sys

from .choose_loadout import label
from .install_private import WORKSPACE, inspect_install
from .launch import preflight
from .save_inspect import inspect_private


def equipment_message(snapshot: dict) -> str:
    characters = snapshot.get('characters', [])
    if len(characters) != 1:
        return 'New characters start with the M9. Existing characters keep their saved equipment.'
    character = characters[0]
    if character['selected_right_item'] == 1250000:
        return 'Your saved character has the M9 selected in the right hand.'
    if character['m9_equipped_slots'] == ['right_2'] and character['selected_right_slot'] == 1:
        return 'Your saved character has the M9 in the second right-hand slot. Switch weapon once (D-pad Right) outside menus.'
    if character['m9_and_bolts_in_inventory'] and any(
            item['item_id'] == 1250000 for item in character['m9_and_bolts_in_inventory']):
        return 'Your saved character owns the M9. Equip MW2 M9 in the right hand using the Equipment menu.'
    return 'The inspected character has no M9. Existing characters do not receive new starting equipment.'


def progress_message(line: str) -> str | None:
    """Display only known factual events; a process is not proof of gameplay."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict) or not isinstance(event.get("status"), str):
        return None
    return {
        "native_game_process_started": "DSR has started its process. Its window and gameplay are not yet verified.",
        "steam_did_not_start_native_game": "Steam did not start DSR. Closing this private Steam session; the setup is preserved.",
        "waiting_for_private_shutdown": "The private session is still closing. The launcher is keeping its resource lock until it exits.",
        "read_only_diagnostics_started": "Local equipment diagnostics have been requested. You control all play.",
        "read_only_diagnostics_unavailable": "Optional diagnostics are unavailable. Your game session is unaffected.",
    }.get(event.get("status"))


def run_with_progress(log) -> int:
    # Keep the diagnostic stream, but surface the important startup/failure
    # events promptly instead of making the owner wait blindly for Steam exit.
    with subprocess.Popen([sys.executable, "-B", "-m", "dsr_mw2.launch"], cwd=WORKSPACE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                          encoding="utf-8", errors="replace") as child:
        for line in child.stdout:
            log.write(line)
            log.flush()
            message = progress_message(line)
            if message:
                print(message, flush=True)
        return child.wait()


def main() -> int:
    check = preflight("m9")
    print("Dark Souls Remastered × Modern Warfare 2 — unfinished prototype\n", flush=True)
    if check["blockers"]:
        print("Startup stopped:")
        for reason in check["blockers"]:
            print("  " + reason)
        return 75
    state = inspect_install()
    print("Selected: " + label(state["preset"]), flush=True)
    try:
        print(equipment_message(inspect_private()), flush=True)
    except (OSError, ValueError):
        print('Saved equipment could not be inspected. New characters start with the M9; existing equipment is preserved.', flush=True)
    print("The MW2 M9 currently uses the DSR crossbow equipment icon.", flush=True)
    print("Opening the private offline copy. Steam may take a moment to initialize.", flush=True)
    print("This build still uses DSR crossbow firing. MW2 magazines, reloads, aiming and custom loadouts are not installed.", flush=True)
    log = WORKSPACE / "tooling-local/launch/owner-launch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        result = run_with_progress(stream)
    if result:
        print("The private launcher exited with status " + str(result) + ".")
        print("If the game closed unexpectedly, the diagnostic log is preserved.")
        print("Diagnostic log: " + str(log))
    else:
        print("The private session has closed.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
