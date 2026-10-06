"""Sample approved local M9 exports with original CPU-only math; no Havok import."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from dsr_mw2.animation_pose import compose, read_rig, sample_components
from dsr_mw2.animation_events import classify_events, note_maps, weapon_fields
from dsr_mw2.xanim import read

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "converted/mw2-2009/m9/pose-samples"
    if not out.resolve().is_relative_to(ROOT / "converted"):
        raise ValueError("Output escaped task assets")
    out.mkdir(parents=True, exist_ok=True)
    base = ROOT / "converted/mw2-2009/unlinked"
    weapon = (base / "m9-reference-weapon/weapons/beretta_mp").read_bytes()
    if hashlib.sha256(weapon).hexdigest() != "4dbd3ef6addaae2d20608d96a252dcfde4958a24937953bb5c3694e6a377f3a3":
        raise ValueError("Source weapon note mapping changed")
    fields = weapon_fields(weapon)
    maps = note_maps(fields)
    rig_records = []
    for name, expected in (
        ("viewmodel_beretta_lod0", "d7b64f119ea39e34d740dc34d48477fc9bb06d2e57b2e7671d0038d20177e96c"),
        ("viewmodel_base_viewhands_lod0", "e0cdf472f625d3c62525a8f5f43fbe14ebe6b6870441e9f6dd0500dd68f6cc5d"),
    ):
        data = (base / "m9-handling-models/model_export" / (name + ".xmodel_export")).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Model rig source hash differs")
        bones = read_rig(data.decode("ascii"))
        for bone in bones:
            restored = compose(bones[bone.parent].global_bind, bone.local_bind) if bone.parent >= 0 else bone.local_bind
            if (max(abs(a-b) for a,b in zip(restored.translation, bone.global_bind.translation, strict=True)) > 1e-5 or
                    abs(sum(a*b for a,b in zip(restored.rotation, bone.global_bind.rotation, strict=True))) < 0.999999):
                raise ValueError("Rig bind-pose reconstruction failed")
        rig_records.append({"asset": name, "sha256": expected, "bones": len(bones), "bind_pose_recomposition_passed": True})
    clips = []
    proofs = json.loads((ROOT / "evidence/m9-animation-export-check.json").read_text())["clips"]
    for proof in proofs:
        name = proof["name"]
        if Path(name).name != name:
            raise ValueError("Invalid source clip name")
        data = (base / "m9-handling-animation/xanim" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != proof["sha256"]:
            raise ValueError("Source clip hash differs")
        animation = read(data)
        cues = classify_events(animation, maps)
        times = [min(i/60, animation.seconds) for i in range(math.ceil(animation.seconds*60)+1)]
        sampled = [sample_components(animation, min(t*animation.fps, float(animation.frames))) for t in times]
        missing = sum(component is None for frame in sampled for bone in frame.values() for component in bone.values())
        output = {"asset": name, "source_sha256": proof["sha256"], "source_asset_type": animation.asset_type,
                  "target_game_format": False, "note": "Source components only. Absolute/additive interpretation and DSR rig mapping remain required.",
                  "seconds": times, "sampled_source_components": sampled,
                  "source_events": [{"name": n, "seconds": frame/animation.fps} for n, frame in animation.events],
                  "typed_source_cues": cues,
                  "timing_contract": "Source frames/phase only; follow the eventual native animation clock, not wall-clock timers or ammo-transfer time"}
        target = out / (name + ".json")
        if target.is_symlink():
            raise ValueError("Pose sample destination cannot be a symlink")
        encoded = json.dumps(output, separators=(",", ":"), allow_nan=False).encode()
        target.write_bytes(encoded)
        clips.append({"asset": name, "samples": len(times), "source_bones": len(animation.bones),
                      "missing_components_preserved": missing, "sampled_sha256": hashlib.sha256(encoded).hexdigest(),
                      "bytes": len(encoded), "source_asset_type": animation.asset_type,
                      "typed_source_cues": cues})
    report = {"at": datetime.now(timezone.utc).isoformat(), "rigs": rig_records, "clips": clips,
              "output_sample_rate": 60, "retargeted_to_dsr": False, "havok_executed": False,
              "game_launched": False, "renderer_used": False, "installed": False,
              "limits": ["No DSR basis/bone correspondence guessed", "Missing tracks remain null",
                         "Raw animation asset_type is preserved, not assumed to mean DSR local-space motion"]}
    report["cue_contract"] = {
        "sound_and_rumble_distinguished": True,
        "sound_alias_to_wav_verified": False,
        "native_animation_clock_bound": False,
        "weapon_reload_add_seconds": float(fields["reloadAddTime"]),
        "weapon_tactical_reload_seconds": float(fields["reloadTime"]),
        "weapon_empty_reload_seconds": float(fields["reloadEmptyTime"]),
        "note": "Authored clip-in and chamber notes do not equal the 1.2-second ammo transfer; do not synthesize cues from inventory changes",
    }
    (ROOT / "evidence/m9-pose-sampling.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"rigs": len(rig_records), "clips": len(clips), "samples": sum(x["samples"] for x in clips),
                      "retargeted_to_dsr": False, "havok_executed": False}))


if __name__ == "__main__":
    main()
