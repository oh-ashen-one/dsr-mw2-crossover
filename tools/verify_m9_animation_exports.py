"""Verify local M9 animation exports; emit only metadata, not motion data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dsr_mw2.xanim import read

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("idle", "fire", "fire_ads", "lastfire", "reload", "reload_empty2", "ads_up", "ads_down", "pullout", "putaway")


def main():
    base = ROOT / "converted/mw2-2009/unlinked/m9-handling-animation/xanim"
    source = ROOT / "profiles/dsr-mw2/drive_c/Assets/mw2-2009/zone/english/common_mp.ff"
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_sha != "e0ef62d050d43b84df99b460106631351f9932b744e77ac3ab5f30db00f0f26f":
        raise ValueError("M9 animation source fastfile revision changed")
    clips = []
    rigs = []
    for suffix in NAMES:
        name = "viewmodel_beretta_" + suffix
        p = base / name
        data = p.read_bytes()
        a = read(data)
        if suffix not in {"ads_up", "ads_down"}:
            names = {b.name for b in a.bones}
            if not {"j_gun", "tag_clip", "j_bolt", "j_wrist_le", "j_wrist_ri"} <= names:
                raise ValueError("Expected M9 gun/hand animation bones are missing")
            rigs.append(names)
        clips.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                      "frames": a.frames, "fps": a.fps, "seconds": a.seconds, "bone_count": len(a.bones),
                      "notes": [{"name": n, "frame": f, "seconds": f/a.fps} for n, f in a.events]})
    if any(rig != rigs[0] for rig in rigs):
        raise ValueError("M9 animation clips disagree on bone names")
    report = {"at": datetime.now(timezone.utc).isoformat(), "source_fastfile_sha256": source_sha,
              "extractor_sha256": "f7ee888b026a4f7d47a7e74b83c3e08022d61e0a2776efaa51c168741c78a94a",
              "source_names_preserved": True, "complete_files_parsed": True, "clips": clips,
              "rig_consistent": True, "dsr_havok_target": "Havok 2015.01 tagfile, observed in native c0000 Skeleton.hkx",
              "retargeted_to_dsr": False, "installed": False, "game_launched": False,
              "limits": ["MW2 source clip duration differs from weapon timing; do not equate note tracks with ammo commit time",
                         "Player skeleton, gun slide and magazine need native retargeting; world mesh currently rigid",
                         "No native Havok animation writer is installed in the approved Soulstruct environment"]}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
