"""Read this task's prepared artifacts and blockers; never launch a process."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib

from .audit import inspect, is_within
from .loadouts import load
from .stage_runtime import FILES
from .model_candidate import read as read_model
from .asset_provenance import EXTRACTOR, EXTRACTOR_SHA, digest
from .install_private import inspect_install, checked_package
from .runtime_paths import bottle_path
from .launch import preflight as launch_preflight
from .install_audio import check as audio_status

WORKSPACE = Path(__file__).resolve().parents[1]
from .local_config import path as configured_path
STEAMAPPS = configured_path("source_steam", WORKSPACE / "retail/Steam") / "steamapps"


def package_status(folder: Path, revision: str = 'legacy') -> dict:
    """Check actual package bytes and its disabled config, without trusting labels."""
    result = {"folder": str(folder), "files_hash_verified": False, "config_disabled": False}
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
        files = manifest["files"]
        if not files or not (manifest["mechanics_only"] or manifest.get("authentic_mw2_model_present") is True):
            raise ValueError("Expected an inactive mechanics or checked model package")
        result["authentic_model_candidate_included"] = manifest.get("authentic_mw2_model_present") is True
        result["files_hash_verified"] = all(
            is_within(folder / item["path"], folder)
            and hashlib.sha256((folder / item["path"]).read_bytes()).hexdigest() == item["sha256"]
            for item in files
        )
        if result["authentic_model_candidate_included"]:
            root = folder.parents[2] if revision == 'legacy' else folder.parents[3]
            checked_package(root, folder.name, revision)
        config = tomllib.loads((folder / "config_dsr_candidate.toml").read_text())
        mods = config["extension"]["mod_loader"]["mods"]
        result["config_disabled"] = bool(mods) and all(m["enabled"] is False for m in mods)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["error"] = str(exc)
        result["files_hash_verified"] = False
    return result


def runtime_staging() -> dict:
    root = WORKSPACE / "profiles/dsr-mw2/drive_c/Tools/DSR-MW2"
    result = {"folder": str(root), "pinned_files_hash_verified": False, "stock_config_disabled": False}
    try:
        result["pinned_files_hash_verified"] = all(
            is_within(root / relative, root)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
            for relative, expected in FILES.items()
        )
        config = tomllib.loads((root / "config_dsr_stock.toml").read_text())
        mods = config["extension"]["mod_loader"]["mods"]
        result["stock_config_disabled"] = bool(mods) and all(m["enabled"] is False for m in mods)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["error"] = str(exc)
    return result


def model_status(folder: Path) -> dict:
    result = {"folder": str(folder), "source_and_binder_verified": False, "runtime_verified": False}
    try:
        report, _ = read_model(folder)
        result.update(source_and_binder_verified=True, meshes=report["meshes"], vertices=report["vertices"], attachment=report["attachment"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["error"] = str(exc)
    return result


def status() -> dict:
    preflight = inspect(STEAMAPPS, bottle_path(), WORKSPACE)
    installation = inspect_install()
    revision = installation.get('revision', 'legacy')
    package_root = WORKSPACE / 'converted/packages'
    if revision != 'legacy':
        package_root = package_root / revision
    builds = []
    for preset in sorted((WORKSPACE / "loadouts").glob("*.json")):
        try:
            metadata = load(preset)
        except (OSError, ValueError) as exc:
            builds.append({"preset": str(preset), "error": str(exc)})
            continue
        folder = WORKSPACE / "converted/dsr" / metadata["name"]
        report_path = folder / "build-report.json"
        candidate = folder / "mod/param/GameParam/GameParam.parambnd.dcx"
        verified = False
        try:
            report = json.loads(report_path.read_text())
            verified = is_within(candidate, WORKSPACE) and hashlib.sha256(candidate.read_bytes()).hexdigest() == report["output_sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        builds.append({
            "name": metadata["name"], "parameter_file_hash_verified": verified,
            "candidate_folder": str(folder), "runtime_verified": False,
            "package": package_status(package_root / metadata["name"], revision),
        })
    head = WORKSPACE / ".git/HEAD"
    branch = head.read_text().strip().removeprefix("ref: refs/heads/") if head.is_file() else "unknown"
    approved = False
    extractor_verified = False
    try:
        receipt = json.loads((WORKSPACE / "tooling-local/native-extraction-approval.json").read_text())
        approved = receipt.get("native_execution_approved") is True
        extractor_verified = digest(EXTRACTOR) == EXTRACTOR_SHA
    except (OSError, ValueError):
        pass
    models = [model_status(WORKSPACE / "converted/dsr" / name) for name in ("m9-model-candidate", "m9-suppressed-model-candidate")]
    if revision in {'upright-v1', 'winding-v2'}:
        models = [model_status(WORKSPACE / 'converted/dsr' / ('m9-' + revision) / name) for name in ('base', 'suppressed')]
    suppressed = [package_status(package_root / (build["name"] + "-suppressed"), revision) for build in builds if "name" in build]
    blockers = list(launch_preflight("m9")["blockers"])
    checkpoint = WORKSPACE / 'evidence/integration-progress-2026-10-04.json'
    if checkpoint.is_file():
        try:
            pending = json.loads(checkpoint.read_text()).get('pending_owner_decision')
            if isinstance(pending, str) and pending:
                blockers.append(pending)
        except (OSError, ValueError, AttributeError):
            pass
    profile = preflight["profile"]
    if not profile["startup_console_verified"]:
        blockers.append("Private Wine console startup is unverified")
    if not profile["drive_mapping_persistence_verified"]:
        blockers.append("Private drive-map persistence is unverified")
    if not (bottle_path() / "drive_c/Program Files (x86)/Steam/config/loginusers.vdf").is_file():
        blockers.append("Private Steam first sign-in is pending; no account state has been copied")
    startup = {}
    try:
        startup = json.loads((WORKSPACE/'evidence/startup-approved-2026-10-04.json').read_text())
        for path_key, hash_key in [('stock_title_capture','stock_title_sha256'),
                                   ('fresh_m9_main_menu_capture','fresh_m9_main_menu_sha256')]:
            path = WORKSPACE/startup[path_key]
            if not is_within(path, WORKSPACE) or digest(path) != startup[hash_key]:
                raise ValueError('Startup capture changed')
        game = bottle_path()/'drive_c/Games/DSR-MW2'
        from .install_private import STOCK_HASHES
        if startup['installed_file_hashes'] != {p:digest(game/p) for p in STOCK_HASHES}:
            raise ValueError('Installed preset differs from captured startup')
    except (OSError, ValueError, TypeError, KeyError):
        startup = {}
    if not (startup.get('stock_title_verified') and startup.get('fresh_m9_startup_verified')):
        blockers.append('Captured stock/fresh-M9 startup evidence is absent or does not match this preset')
    blockers.append("Owner rejected handgun visuals, crossbow behavior and PS5 response; these are failed acceptance gates")
    blockers.append("MW2 magazines, reloads, ADS, recoil, gun sound and in-game loadouts are not integrated")
    blockers.append("Corrected visuals, in-game controller response, native hits/misses, death/defeat/reset and performance remain unverified")
    return {
        "goal": "Native DSR gameplay with authentic MW2 (2009) guns and custom loadouts",
        "workspace": str(WORKSPACE), "branch": branch, "preflight": preflight,
        "loadouts": builds, "prepared_textures": (WORKSPACE / "converted/mw2-2009/m9/dds/manifest.json").is_file(),
        "stock_flver_roundtrip": (WORKSPACE / "evidence/flver-roundtrip.json").is_file(),
        "native_extractor_compiled": (WORKSPACE / "tooling-local/OpenAssetTools-v0.33.0-macos/Unlinker").is_file(),
        "native_extractor_execution_approved": approved, "native64_extractor_hash_verified": extractor_verified,
        "loader_execution_approved": False,
        "loader_required": False, "native_installation": installation,
        "native_audio": audio_status(),
        "startup_evidence": startup,
        "runtime_staging": runtime_staging(),
        "authentic_gun_mesh_extracted": any(model["source_and_binder_verified"] for model in models),
        "model_candidates": models, "suppressed_packages": suppressed, "mw2_animation_retargeted": False,
        "activated": installation.get("installed", False), "ready_to_play_crossover": False,
        "blockers": blockers,
    }


def describe(report: dict) -> str:
    lines = [
        "DSR × MW2: unfinished crossbow prototype; owner acceptance failed",
        f"Own branch: {report['branch']}",
        "Installed: " + ", ".join(f"{name} {'yes' if game['installed'] else 'missing'}" for name, game in report["preflight"]["games"].items()),
        "",
        "Prepared loadouts (authentic M9 candidate, native crossbow action):",
    ]
    for build in report["loadouts"]:
        if "error" in build:
            lines.append(f"  Invalid preset {build['preset']}: {build['error']}")
            continue
        package = build["package"]
        checked = build["parameter_file_hash_verified"] and package["files_hash_verified"] and package["config_disabled"]
        lines.append(f"  {build['name']}: {'files checked' if checked else 'incomplete or changed; inspect JSON report'}")
    staged = report["runtime_staging"]
    for package in report["suppressed_packages"]:
        checked = package["files_hash_verified"] and package["config_disabled"]
        lines.append(f"  {Path(package['folder']).name}: {'files checked' if checked else 'incomplete or changed'}")
    lines.extend([
        "",
        "Native install: " + ("hashes verified; private stock baseline preserved" if report['native_installation'].get('installed') else "missing or changed"),
        "Selected loadout: " + report['native_installation'].get('preset', 'none'),
        "Model revision: " + report['native_installation'].get('revision', 'legacy'),
        "M9 shot audio: " + ('installed; playback unverified' if report.get('native_audio', {}).get('enabled') else 'stock'),
        "Experimental loader: not needed by the native file route; remains unused.",
        ("Stock title and fresh offline M9 menu verified; private save creation verified. Combat remains untested."
         if report.get('startup_evidence', {}).get('fresh_m9_startup_verified')
         else "Native startup evidence does not match this preset; gameplay remains unverified."),
        "",
        "Remaining blockers:",
        *[f"  - {item}" for item in report["blockers"]],
        "",
        "Launcher: Play DSR + MW2.command",
        "Loadout selector: Choose M9 Loadout.command",
        "Start guide: START HERE.md",
        "Detailed read-only report: python3 -B -m dsr_mw2.status --json",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    args = parser.parse_args()
    report = status()
    print(json.dumps(report, indent=2) if args.json else describe(report))
    return 2  # A prepared mechanics candidate is not a playable crossover.


if __name__ == "__main__":
    raise SystemExit(main())
