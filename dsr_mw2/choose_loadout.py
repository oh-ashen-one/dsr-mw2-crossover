"""Choose one prepared native M9 setup without starting Steam or the game."""
from __future__ import annotations

from .install_private import WORKSPACE, install, inspect_install
from .launch import BOTTLE, bottle_processes
from .profile import guard

CHOICES = (
    ("m9-sidearm", "M9 — standard", "100 base damage"),
    ("m9-low-damage", "M9 — lower damage", "70 base damage"),
    ("m9-sidearm-suppressed", "M9 with suppressor", "100 base damage; visual attachment"),
    ("m9-low-damage-suppressed", "M9 with suppressor — lower damage", "70 base damage; visual attachment"),
)


def label(preset: str) -> str:
    return next((name for key, name, _ in CHOICES if key == preset), preset)


def select(preset: str) -> dict:
    if preset not in {key for key, _, _ in CHOICES}:
        raise ValueError("Choose one of the four prepared M9 setups")
    reasons = guard(BOTTLE)
    if reasons:
        raise ValueError("Private profile check failed: " + "; ".join(reasons))
    if bottle_processes():
        raise ValueError("The private DSR session is still open. Finish that session before changing its loadout.")
    return install(WORKSPACE, preset, clone=False)


def main() -> int:
    state = inspect_install()
    if not state.get("installed") or not state.get("stock_baseline_preserved"):
        print("The installed files need repair before a loadout can be changed.")
        return 1
    print("Dark Souls Remastered × Modern Warfare 2\n")
    print("Current setup: " + label(state["preset"]))
    print("All four choices use the authentic MW2 M9 with DSR single-shot crossbow actions.")
    print("Suppressors currently change appearance only. Gameplay is unverified.\n")
    for number, (_, name, detail) in enumerate(CHOICES, 1):
        print(f"  {number}. {name} ({detail})")
    print("  0. Keep the current setup\n")
    while True:
        try:
            answer = input("Choose 1–4, or press Return to keep the current setup: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCurrent setup kept.")
            return 0
        if answer in {"", "0"}:
            print("Current setup kept.")
            return 0
        if answer in {"1", "2", "3", "4"}:
            break
        print("Enter 1, 2, 3, 4 or 0.")
    try:
        result = select(CHOICES[int(answer) - 1][0])
    except (OSError, ValueError) as exc:
        print(f"Loadout not changed: {exc}")
        return 1
    print("\nSelected: " + label(result["preset"]))
    print("Open Play DSR + MW2.command when you want to start.")
    print("New characters are configured for the M9 in right-hand slot 1 and 99 bolts. Existing equipment is preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
