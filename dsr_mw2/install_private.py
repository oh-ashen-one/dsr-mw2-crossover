"""Install native data into a second task-owned DSR copy; never run the game."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .audit import is_within
from .runtime_paths import bottle_path, LOCAL_BOTTLE
from .loadouts import load as load_loadout
from .process_ownership import bottle_processes

WORKSPACE = Path(__file__).resolve().parents[1]
STOCK_HASHES = {
    "param/GameParam/GameParam.parambnd.dcx": "cc4a81cc87f028534d965c908a8aa7dba2f9e235ac30f5e72ddf6bb45dc7b5ab",
    "msg/ENGLISH/item.msgbnd.dcx": "20193b611fdf087da4d7d098f9ff754b0bb59f636519c483ba7960f77cfbf691",
    "parts/WP_A_1401.partsbnd.dcx": "e851d82ad7828ba0a3cec47885157d9964aaf3163635f370f148f35d57d6e833",
}
PRESETS = ("m9-sidearm", "m9-low-damage", "m9-sidearm-suppressed", "m9-low-damage-suppressed")
REVISIONS = ("legacy", "upright-v1", "winding-v2")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    # Replacing a directory entry also avoids modifying a possible hard link.
    fd, name = tempfile.mkstemp(prefix=".dsr-mw2-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def layout(workspace: Path) -> tuple[Path, Path, Path]:
    bottle = bottle_path(workspace)
    stock = bottle / "drive_c/Games/Dark Souls Remastered"
    candidate = bottle / "drive_c/Games/DSR-MW2"
    boundary = LOCAL_BOTTLE.parent if bottle == LOCAL_BOTTLE else workspace
    for p in (bottle, stock, candidate):
        if p.is_symlink() or not is_within(p, boundary):
            raise ValueError("Private install path escapes the task workspace")
    return bottle, stock, candidate


def checked_package(workspace: Path, preset: str, revision: str = "legacy") -> dict[str, bytes]:
    if preset not in PRESETS:
        raise ValueError("Unknown prepared loadout")
    if revision not in REVISIONS:
        raise ValueError("Unknown prepared package revision")
    folder = workspace / "converted/packages"
    if revision != "legacy":
        folder = folder / revision
    folder = folder / preset
    if not is_within(folder, workspace):
        raise ValueError("Package escapes the workspace")
    manifest_path = folder / "manifest.json"
    if not is_within(manifest_path, folder):
        raise ValueError("Package manifest escapes its folder")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError("Package manifest must be an object")
    if manifest.get("authentic_mw2_model_present") is not True:
        raise ValueError("Authentic model proof is missing")
    base = preset.removesuffix("-suppressed")
    definition = workspace / "loadouts" / (base + ".json")
    model_folder = "m9-suppressed-model-candidate" if preset.endswith("-suppressed") else "m9-model-candidate"
    model_path = workspace / "converted/dsr" / model_folder / "model-report.json"
    if revision in {"upright-v1", "winding-v2"}:
        variant = "suppressed" if preset.endswith("-suppressed") else "base"
        model_path = workspace / "converted/dsr" / ("m9-" + revision) / variant / "model-report.json"
    parameter_report = workspace / "converted/dsr" / base / "build-report.json"
    text_report = model_path.parent / "equipment-text/text-report.json"
    if any(not is_within(p, workspace) for p in (definition, model_path, parameter_report, text_report)):
        raise ValueError("Package identity records escape the workspace")
    model = json.loads(model_path.read_text())
    if not isinstance(model, dict):
        raise ValueError("Model identity record must be an object")
    if (manifest.get("loadout") != load_loadout(definition)
            or manifest.get("model_attachment") != model.get("attachment")
            or manifest.get("model_provenance") != model.get("source")
            or model.get("authentic_asset_provenance_verified") is not True):
        raise ValueError("Package identity does not match the selected loadout and model")
    parameters = json.loads(parameter_report.read_text())
    texts = json.loads(text_report.read_text())
    if (not isinstance(parameters, dict) or parameters.get("loadout") != manifest["loadout"]
            or parameters.get("source_sha256") != STOCK_HASHES["param/GameParam/GameParam.parambnd.dcx"]
            or not isinstance(texts, dict) or texts.get("model_candidate_sha256") != model.get("output_sha256")
            or texts.get("source_sha256") != STOCK_HASHES["msg/ENGLISH/item.msgbnd.dcx"]):
        raise ValueError("Package native-data provenance does not match the selected setup")
    expected_hashes = {
        "mod/param/GameParam/GameParam.parambnd.dcx": parameters.get("output_sha256"),
        "mod/msg/ENGLISH/item.msgbnd.dcx": texts.get("output_sha256"),
        "mod/parts/WP_A_1401.partsbnd.dcx": model.get("output_sha256"),
    }
    records = manifest.get("files")
    if (not isinstance(records, list) or any(not isinstance(r, dict) or
            not isinstance(r.get("path"), str) or type(r.get("bytes")) is not int
            or not isinstance(r.get("sha256"), str) for r in records)):
        raise ValueError("Package file records are incomplete")
    if len(records) != len(STOCK_HASHES) or {r["path"] for r in records} != {"mod/" + p for p in STOCK_HASHES}:
        raise ValueError("Package must contain exactly the three expected native data files")
    contents = {}
    for record in records:
        source = folder / record["path"]
        if not is_within(source, folder):
            raise ValueError("Package file escapes its folder")
        data = source.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Package hash or size changed")
        if record["sha256"] != expected_hashes[record["path"]]:
            raise ValueError("Package native data does not match the selected setup: " + record["path"])
        contents[record["path"].removeprefix("mod/")] = data
    return contents


def install(workspace: Path, preset: str, *, clone=True, revision: str | None = None) -> dict:
    workspace = workspace.resolve()
    bottle, stock, candidate = layout(workspace)
    state_path = bottle / ".dsr-mw2-native-install.json"
    for p in (state_path, bottle / ".dsr-mw2-session.lock"):
        if p.is_symlink() or not is_within(p, bottle):
            raise ValueError("Private install metadata must remain in the bottle")
    for relative, expected in STOCK_HASHES.items():
        original = stock / relative
        if not is_within(original, stock) or sha(original) != expected:
            raise ValueError(f"Private stock baseline changed: {relative}")
    # The lock is shared with the launcher. No file switching while it owns it.
    with (bottle / ".dsr-mw2-session.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError("A process owns this private bottle; close its session before changing files")
        previous = json.loads(state_path.read_text()) if state_path.exists() else None
        selected_revision = revision or (previous.get("revision", "legacy") if previous else "legacy")
        data = checked_package(workspace, preset, selected_revision)
        if not candidate.exists():
            if not clone:
                raise ValueError("Candidate copy is missing")
            subprocess.run(["/bin/cp", "-cR", str(stock), str(candidate)], check=True)
        expected = previous["installed_hashes"] if previous else STOCK_HASHES
        before = {}
        for relative in STOCK_HASHES:
            target = candidate / relative
            if not is_within(target, candidate) or sha(target) != expected[relative]:
                raise ValueError(f"Unmanaged candidate change; preserving it: {relative}")
            before[relative] = target.read_bytes()
        changed = []
        try:
            for relative, payload in data.items():
                atomic_write(candidate / relative, payload)
                changed.append(relative)
            hashes = {p: sha(candidate / p) for p in data}
            if hashes != {p: hashlib.sha256(v).hexdigest() for p, v in data.items()}:
                raise ValueError("Installed file verification failed")
            report = {
                "preset": preset, "revision": selected_revision, "route": "private-native-files",
                "game_relative": "drive_c/Games/DSR-MW2",
                "installed_hashes": hashes, "stock_hashes": dict(STOCK_HASHES),
                "stock_baseline_preserved": True, "loader_required": False,
                "runtime_verified": False,
            }
            atomic_write(state_path, (json.dumps(report, indent=2) + "\n").encode())
        except Exception:
            for relative in reversed(changed):
                atomic_write(candidate / relative, before[relative])
            raise
    return report


def inspect_install(workspace: Path = WORKSPACE, *, action_trial: bool = False) -> dict:
    # A missing/corrupt receipt is a failed check, never a successful empty hash
    # comparison or an uncaught traceback from the owner's launcher.
    result = {"installed": False, "stock_baseline_preserved": False,
              "package_matches_install": False, "runtime_verified": False}
    try:
        bottle, stock, candidate = layout(workspace)
        state = bottle / ".dsr-mw2-native-install.json"
        result["stock_baseline_preserved"] = all(
            is_within(stock / p, stock) and sha(stock / p) == digest for p, digest in STOCK_HASHES.items())
        if not state.exists():
            return result
        if state.is_symlink() or not is_within(state, bottle):
            raise ValueError("Private install receipt escapes its bottle")
        report = json.loads(state.read_text())
        revision = report.get("revision", "legacy")
        data = checked_package(workspace, report["preset"], revision)
        expected = {p: hashlib.sha256(payload).hexdigest() for p, payload in data.items()}
        if report.get("installed_hashes") != expected:
            raise ValueError("Installed receipt differs from the selected package")
        if action_trial:
            from .action_trial import expected_override
            expected.update(expected_override(candidate))
        result["preset"] = report["preset"]
        result["revision"] = revision
        result["package_matches_install"] = all(
            is_within(candidate / p, candidate) and sha(candidate / p) == digest for p, digest in expected.items())
        result["installed"] = result["package_matches_install"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="m9-sidearm")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--revision", choices=REVISIONS, help="Explicit version switch; otherwise preserve the current version")
    args = parser.parse_args()
    report = inspect_install() if args.check else install(WORKSPACE, args.preset, revision=args.revision)
    print(json.dumps(report, indent=2))
    return 0 if not args.check or (report.get("installed") and report.get("stock_baseline_preserved")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
