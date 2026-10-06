"""Read process paths to identify this task's bottle, without account inspection."""
from pathlib import Path
import subprocess


def processes() -> list[tuple[int, str, str]]:
    lines = subprocess.check_output(["ps", "-axo", "pid=,stat=,comm="], text=True).splitlines()
    return [(int(pid), state, name) for pid, state, name in
            (line.strip().split(None, 2) for line in lines if line.strip())]


def bottle_processes(bottle: Path) -> list[int]:
    wine = [(pid, name) for pid, _, name in processes()
            if name.lower().endswith(".exe") or Path(name).name in {"wineserver", "wineloader"}]
    found = []
    for pid, name in wine:
        output = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                                capture_output=True, text=True).stdout
        # wineserver can have /tmp as its cwd; registry handles identify it.
        if Path(name).name == "wineserver":
            output += subprocess.run(["lsof", "-p", str(pid), "-Fn"],
                                     capture_output=True, text=True).stdout
        if any(line.startswith("n" + str(bottle) + "/") or line == "n" + str(bottle)
               for line in output.splitlines()):
            found.append(pid)
    return found
