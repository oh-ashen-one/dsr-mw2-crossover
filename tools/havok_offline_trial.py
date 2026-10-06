"""Prepared offline trial; execute only after the exact Havok/SciPy approval.

No game, Wine, helper executable, network, install or runtime mutation. The
input is the existing task-local skeleton copy; output is a separate HKX copy.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tooling-local/sources/soulstruct-havok-review"
COMMIT = "bf2d41fc83de4a43bd3ed3df8605741f143cad2c"


def main():
    from dsr_mw2.local_config import require_permission
    require_permission('allow_offline_conversion')
    head = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != COMMIT or dirty:
        raise ValueError("Havok source must match the reviewed unmodified commit")
    os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
    sys.dont_write_bytecode = True
    from dsr_mw2.soulstruct_tools import configure
    configure()
    dependencies = ROOT / "tooling-local/havok-python-deps"
    if not (dependencies / "scipy-1.18.0.dist-info").is_dir():
        raise ValueError("Pinned SciPy wheel has not been installed to the approved task-only target")
    sys.path.insert(0, str(dependencies))
    # soulstruct is a PEP 420 namespace. Register the source root rather than
    # appending to its transient __path__, which imports may recalculate.
    sys.path.insert(0, str(SOURCE / "src"))
    # The pinned source imports an undeclared terminal-color dependency. This
    # original, process-local adapter supplies only the observed printing API;
    # it performs no terminal setup and cannot affect Havok data or math.
    # Do not install/execute an additional downloaded package for color output.
    color = types.ModuleType("colorama")
    color.just_fix_windows_console = lambda: None
    color.Fore = types.SimpleNamespace(**{name: "" for name in (
        "RED", "GREEN", "YELLOW", "BLUE", "CYAN", "MAGENTA", "LIGHTMAGENTA_EX", "RESET")})
    if "colorama" in sys.modules:
        raise ValueError("Unexpected preloaded terminal-color dependency")
    sys.modules["colorama"] = color

    output = ROOT / "converted/mw2-2009/m9/havok"
    output.mkdir(parents=True, exist_ok=True)
    if not output.resolve().is_relative_to(ROOT / "converted"):
        raise ValueError("Havok output escaped this task")
    log_root = ROOT / "tooling-local/soulstruct"

    def audit(event, args):
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "socket.connect", "socket.bind"}:
            raise RuntimeError("Havok trial prohibits subprocess/network execution: " + event)
        path = None
        if event == "open":
            name, mode, flags = args
            if isinstance(name, (str, bytes, os.PathLike)) and ((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
                path = Path(os.fsdecode(name)).resolve()
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod"}:
            path = Path(os.fsdecode(args[0])).resolve()
        elif event in {"os.rename", "os.link", "os.symlink"}:
            raise RuntimeError("Havok trial prohibits link/rename operations")
        if path is not None and not any(path.is_relative_to(p) for p in (output, log_root)):
            raise RuntimeError("Havok trial write outside private outputs: " + str(path))

    sys.addaudithook(audit)
    from soulstruct.havok.fromsoft.darksouls1r import SkeletonHKX
    import scipy
    if scipy.__version__ != "1.18.0":
        raise ValueError("Unexpected SciPy version")
    original = (ROOT / "tooling-local/handling-review/dsr-player-skeleton.hkx").read_bytes()
    if hashlib.sha256(original).hexdigest() != "6439d12659afa550ef2c296116d457dcabf0f5bf9760cbdf099d4a6db38a8917":
        raise ValueError("Copied native skeleton revision changed")
    before = SkeletonHKX.from_bytes(original)
    encoded = bytes(before)
    after = SkeletonHKX.from_bytes(encoded)
    a, b = before.skeleton.skeleton, after.skeleton.skeleton
    if [x.name for x in a.bones] != [x.name for x in b.bones] or a.parentIndices != b.parentIndices:
        raise ValueError("Native skeleton names or hierarchy changed on round trip")
    # Compare all native bind-pose components, not just bone count.
    import numpy as np
    for left, right in zip(a.referencePose, b.referencePose, strict=True):
        for field in ("translation", "rotation", "scale"):
            if not np.allclose(tuple(getattr(left, field)), tuple(getattr(right, field)), atol=1e-6, rtol=0):
                raise ValueError("Native bind-pose component changed: " + field)
    if encoded[4:8] != b"TAG0" or b"20150100" not in encoded[:32]:
        raise ValueError("Round trip lost native DSR Havok version")
    destination = output / "dsr-player-skeleton-roundtrip.hkx"
    if destination.is_symlink():
        raise ValueError("Output cannot be a symlink")
    destination.write_bytes(encoded)
    report = {"at": datetime.now(timezone.utc).isoformat(), "havok_commit": COMMIT,
              "scipy_version": scipy.__version__, "bone_count": len(a.bones),
              "source_sha256": hashlib.sha256(original).hexdigest(),
              "roundtrip_sha256": hashlib.sha256(encoded).hexdigest(), "skeleton_roundtrip_passed": True,
              "game_launched": False, "helper_executable_run": False, "retargeted": False}
    (output / "roundtrip-report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
    return before, output


if __name__ == "__main__":
    main()
