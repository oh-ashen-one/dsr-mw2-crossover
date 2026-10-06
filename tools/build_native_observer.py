"""Build original source and execute only its macOS synthetic-memory tests.

Never loads the Windows DLL, starts Wine, attaches to a process or installs it.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tooling-local/native-observer"


def run(arguments):
    return subprocess.run([str(x) for x in arguments], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / "native/src/dsr_snapshot.cpp"
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-I", ROOT / "native/include"]
    fixture = OUT / "snapshot-test"
    run(["/usr/bin/clang++", *flags, "-g", "-fsanitize=address,undefined", source,
         ROOT / "native/tests/snapshot_test.cpp", "-o", fixture])
    result = run([fixture])
    dll = OUT / "dsr_mw2_observer.dll"
    run(["/opt/homebrew/bin/x86_64-w64-mingw32-g++", *flags, "-O2", "-shared", "-static", "-fno-exceptions", "-fno-rtti",
         "-Wl,--no-insert-timestamp", source, ROOT / "native/src/read_only_module.cpp", "-lbcrypt", "-o", dll])
    imports = run(["/opt/homebrew/bin/x86_64-w64-mingw32-objdump", "-p", dll])
    (OUT / "pe-inspection.txt").write_text(imports)
    forbidden = ["WriteProcessMemory", "CreateRemoteThread", "OpenProcess", "CreateProcessW", "ShellExecuteW", "libwinpthread-1.dll"]
    if any(name in imports for name in forbidden):
        raise ValueError("Read-only observer contains a prohibited mutation/launch import")
    for name in ("ReadProcessMemory", "DsrMw2ReadSnapshot", "DsrMw2SnapshotSize"):
        if name not in imports:
            raise ValueError("Expected read-only observer interface is missing: " + name)
    probe = OUT / "dsr_readonly_probe_v3.exe"
    run(["/opt/homebrew/bin/x86_64-w64-mingw32-g++", *flags, "-O2", "-static", "-fno-exceptions", "-fno-rtti",
         "-Wl,--no-insert-timestamp", source, ROOT / "native/src/read_only_probe.cpp", "-lbcrypt", "-o", probe])
    probe_imports = run(["/opt/homebrew/bin/x86_64-w64-mingw32-objdump", "-p", probe])
    (OUT / "probe-pe-inspection.txt").write_text(probe_imports)
    for name in ("WriteProcessMemory", "CreateRemoteThread", "VirtualAllocEx", "VirtualProtectEx",
                 "CreateProcess", "ShellExecute", "SendInput", "keybd_event", "mouse_event", "libwinpthread-1.dll"):
        if name in probe_imports:
            raise ValueError("External observer has a prohibited write/input/launch import: " + name)
    for name in ("OpenProcess", "ReadProcessMemory", "QueryFullProcessImageNameW", "WaitForSingleObject"):
        if name not in probe_imports:
            raise ValueError("External observer read-only interface missing: " + name)
    report = {"at": datetime.now(timezone.utc).isoformat(), "macos_fixture_result": result.strip(),
              "sanitizers": ["address", "undefined"], "windows_dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
              "windows_dll_bytes": dll.stat().st_size, "windows_dll_built": True,
              "windows_dll_executed": False, "game_attached": False, "game_launched": False,
              "external_probe": {"file": probe.name, "schema": 3,
                  "sha256": hashlib.sha256(probe.read_bytes()).hexdigest(), "bytes": probe.stat().st_size,
                  "executed": False, "source": "native/src/read_only_probe.cpp",
                  "capture_seconds": 120, "max_wait_for_character_seconds": 300,
                  "process_access": ["PROCESS_VM_READ", "PROCESS_QUERY_INFORMATION", "SYNCHRONIZE"]},
              "toolchain_note": "MinGW CRT imports VirtualProtect for its own PE relocations; adapter source never calls it or changes protection",
              "installed": False, "runtime_verified": False,
              "scope": "Original read-only native inventory/input adapter; no reload writer or loader",
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "native").rglob("*")) if p.suffix in {".cpp", ".hpp"}}}
    (ROOT / "evidence/owner-probe-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
