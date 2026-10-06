"""Compile/test original controller; no game, Wine, loader or live-memory writer."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tooling-local/native-handling"


def run(args):
    result = subprocess.run([str(x) for x in args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-I", ROOT / "native/include"]
    sources = [ROOT / "native/src/dsr_snapshot.cpp", ROOT / "native/src/m9_handling.cpp", ROOT / "native/src/iw4_view_kick.cpp",
               ROOT / "native/src/m9_input.cpp"]
    test = OUT / "handling-test"
    run(["/usr/bin/clang++", *flags, "-g", "-fsanitize=address,undefined", *sources,
         ROOT / "native/tests/handling_test.cpp", "-o", test])
    result = run([test])
    input_test = OUT / "input-test"
    run(["/usr/bin/clang++", *flags, "-g", "-fsanitize=address,undefined", ROOT / "native/src/m9_input.cpp",
         ROOT / "native/tests/input_test.cpp", "-o", input_test])
    input_result = run([input_test])
    objects = []
    for source in sources:
        obj = OUT / (source.stem + ".o")
        run(["/opt/homebrew/bin/x86_64-w64-mingw32-g++", *flags, "-O2", "-fno-exceptions", "-fno-rtti", "-c", source, "-o", obj])
        objects.append({"file": obj.name, "sha256": hashlib.sha256(obj.read_bytes()).hexdigest()})
    report = {"at": datetime.now(timezone.utc).isoformat(), "macos_fixture_result": result.strip(),
              "sanitizers": ["address", "undefined"], "windows_objects": objects,
              "input_fixture_result": input_result.strip(), "input_mapping_implemented": True,
              "physical_controller_tested": False,
              "native_writer_implemented": False, "camera_adapter_implemented": False,
              "native_reload_action_callback_implemented": False,
              "reload_requires_native_action_receipt": True,
              "semantic_transfer_and_rollback_implemented": True,
              "game_launched": False, "installed": False, "runtime_verified": False,
              "scope": "Controller uses real native inventory observer; writes modeled only by synthetic memory fixture",
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT / "native").rglob("*")) if p.suffix in {".cpp", ".hpp"}}}
    (ROOT / "evidence/m9-handling-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
