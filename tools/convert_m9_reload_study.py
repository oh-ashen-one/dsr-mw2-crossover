"""Approved, single-thread offline M9 reload -> native DSR HKX study.

Not an installable action: no TAE, ESD, inventory, camera or runtime writes.
The actual source/target bind poses drive an explicit rotational retarget.
No first-person gun subtree is treated as an absolute player-bone track.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path

from dsr_mw2.animation_events import classify_events, note_maps, weapon_fields
from dsr_mw2.animation_pose import Transform, quaternion_from_columns, read_rig, rotate, sample_components
from dsr_mw2.animation_retarget import OrthogonalBasis, iw4_viewhand_pose, retarget_global_rotations, retarget_local_rotation, forearm_twist_rotation
from dsr_mw2.skin_geometry import world_transforms
from dsr_mw2.xanim import read
from tools.havok_offline_trial import main as skeleton_trial

ROOT = Path(__file__).resolve().parents[1]
CLIPS = ("reload", "reload_empty2", "fire", "lastfire", "fire_ads", "pullout", "putaway")


def require(value, message):
    if not value:
        raise ValueError(message)


def pinned(path, sha):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, "Input hash mismatch: " + path.name)
    return data


def main(clip="reload", finger_mode="anatomical"):
    require(clip in CLIPS and finger_mode in ("anatomical", "native-grip"), "Unsupported conversion study")
    clip_name = "viewmodel_beretta_" + clip
    skeleton, output = skeleton_trial()  # pins + private write/network/helper audit
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.havok.types.hk2015 import hkaAnnotationTrackAnnotation
    from soulstruct.havok.utilities.maths import Quaternion, TRSTransform, Vector3
    from soulstruct.dcx import DCXType
    from soulstruct.containers import Binder
    import numpy as np

    base = ROOT / "converted/mw2-2009/unlinked"
    proof = next(p for p in json.loads((ROOT / "evidence/m9-animation-export-check.json").read_text())["clips"]
                 if p["name"] == clip_name)
    animation = read(pinned(base / "m9-handling-animation/xanim" / clip_name, proof["sha256"]))
    require(animation.frames == proof["frames"] and 1 <= animation.frames <= 127
            and (animation.fps, animation.asset_type, animation.looped) == (30, 1, False),
            "Unexpected source clip semantics")
    rig_sha = "e0cdf472f625d3c62525a8f5f43fbe14ebe6b6870441e9f6dd0500dd68f6cc5d"
    rig = read_rig(pinned(base / "m9-handling-models/model_export/viewmodel_base_viewhands_lod0.xmodel_export", rig_sha).decode())
    weapon_sha = "4dbd3ef6addaae2d20608d96a252dcfde4958a24937953bb5c3694e6a377f3a3"
    fields = weapon_fields(pinned(base / "m9-reference-weapon/weapons/beretta_mp", weapon_sha))
    cues = classify_events(animation, note_maps(fields))
    target = skeleton.skeleton.skeleton
    target_names = [b.name for b in target.bones]
    require(len(target_names) == 61 and target.name == "Master", "Unexpected native player skeleton")
    parents = [int(p) for p in target.parentIndices]
    # Use a real native firing pose as the target anchor, not the reference
    # T-pose. Its first frame coincides with the native shot cue at t=0.
    binder_data = pinned(ROOT / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx",
                         "e510a964d2792dd10307243e9abbe1fa2f63e25487bbb2d4d1c9f2870f662ff7")
    binder = Binder.from_bytes(binder_data)
    anchor_data = next(e for e in binder.entries if e.entry_id == 464000).get_uncompressed_data()
    anchor_sha = "3ddb7906a607a61918943961cb5d1af691461962f95de064a1723034f04eb907"
    require(hashlib.sha256(anchor_data).hexdigest() == anchor_sha, "Native stance revision changed")
    anchor = AnimationHKX.from_bytes(anchor_data).animation_container
    anchor.load_spline_data()  # Pure Python; does not run CompressAnim.
    reference = [t.to_trs_transform() for t in target.referencePose]
    for index, track in zip(anchor.hkx_binding.transformTrackToBoneIndices, anchor.spline_data.blocks[0], strict=True):
        reference[index] = track.get_trs_transform_at_frame(0)
    native_bind = tuple(Transform(tuple(float(x) for x in t.rotation), tuple(float(x) for x in t.translation))
                        for t in reference)
    scales = [tuple(float(v) for v in t.scale) for t in reference]
    scale_deviation = max(abs(v-1) for scale in scales for v in scale)
    require(scale_deviation < 2e-6,
            "Scaled native skeleton requires separate treatment")
    source_names = [b.name for b in rig]
    by_name = {}
    for side, suffix in (("L", "le"), ("R", "ri")):
        for dst, src in (("UpperArm", "shoulder"), ("Forearm", "elbow"), ("Hand", "wrist")):
            by_name[f"{side}_{dst}"] = f"j_{src}_{suffix}"
        # Native foretwist is a sibling of the forearm, while the source twist
        # is its descendant. Global-delta retargeting preserves that difference.
        by_name[f"{side}_ForeTwist"] = f"j_wristtwist_{suffix}"
        # DSR has three finger chains. No invented fourth/fifth native fingers.
        for number, source in ((0, "thumb"), (1, "index"), (2, "mid")):
            for joint in range(3):
                by_name[f"{side}_Finger{number}" + (str(joint) if joint else "")] = f"j_{source}_{suffix}_{joint}"
    mapping = {target_names.index(t): source_names.index(s) for t, s in by_name.items()}
    tracks = sorted(mapping)
    require(len(tracks) == 26, "Unexpected upper-body mask")
    # DSR's left side is +X and native toes point toward -Z. This conversion
    # changes handedness; treating it as a quaternion would mirror forward.
    basis = OrthogonalBasis(((0, 0, -1), (1, 0, 0), (0, 1, 0)))
    idle_proof = next(p for p in json.loads((ROOT / "evidence/m9-animation-export-check.json").read_text())["clips"]
                      if p["name"] == "viewmodel_beretta_idle")
    idle = read(pinned(base / "m9-handling-animation/xanim/viewmodel_beretta_idle", idle_proof["sha256"]))
    source_bind = iw4_viewhand_pose(rig, sample_components(idle, 0))
    idle_components = sample_components(idle, 0)
    native_reference_world = world_transforms(parents, [Transform(tuple(t.rotation),tuple(t.translation)[:3]) for t in target.referencePose])
    bind_result = retarget_global_rotations(source_bind, source_bind, native_bind, parents, mapping, basis)
    require(all(abs(sum(x*y for x, y in zip(a.rotation, b.rotation))) > .999999
                and a.translation == b.translation for a, b in zip(bind_result, native_bind)), "Bind invariant failed")

    rate = 60
    frame_count = animation.frames * 2 + 1
    poses, frames = [], []
    for i in range(frame_count):
        sample = sample_components(animation, i / 2)
        source_pose = iw4_viewhand_pose(rig, sample)
        retarget = list(retarget_global_rotations(source_bind, source_pose, native_bind, parents, mapping, basis))
        for b,s in mapping.items():
            if "Finger" not in target_names[b]: continue
            if finger_mode == "native-grip":
                # Explicit conservative study: retain DSR's authored grip.
                # Do not present this as converted MW2 finger articulation.
                retarget[b] = native_bind[b]
                continue
            source_name = rig[s].name
            require(idle_components[source_name]["rotation"] is not None and sample[source_name]["rotation"] is not None,
                    "Finger rotation component absent")
            q = retarget_local_rotation(idle_components[source_name]["rotation"], sample[source_name]["rotation"],
                native_bind[b].rotation, rig[s].global_bind.rotation, native_reference_world[b].rotation, basis)
            retarget[b] = Transform(q, native_bind[b].translation)
        for side in ("L", "R"):
            fore, hand, twist = (target_names.index(side + "_" + part) for part in ("Forearm", "Hand", "ForeTwist"))
            require(parents[fore] == parents[twist] and parents[hand] == fore
                    and native_bind[fore].translation == native_bind[twist].translation,
                    "Native foretwist no longer shares the elbow origin")
            q = forearm_twist_rotation(retarget[fore].rotation, retarget[hand].rotation,
                                      native_bind[fore].rotation, native_bind[hand].rotation, native_bind[twist].rotation)
            retarget[twist] = Transform(q, native_bind[twist].translation)
        require(all(p.translation == bind.translation for p, bind in zip(retarget, native_bind)), "Native bone length changed")
        require(all(retarget[b] == native_bind[b] for b in range(61) if b not in mapping), "Unmapped local bone changed")
        poses.append(retarget)
        frames.append([TRSTransform(translation=Vector3(retarget[b].translation),
                                    rotation=Quaternion(retarget[b].rotation), scale=Vector3(scales[b])) for b in tracks])

    hkx = AnimationHKX.from_minimal_data_interleaved(
        frames, tracks, original_skeleton_name=target.name, frame_rate=rate,
        track_names=[target_names[b] for b in tracks])
    # Native animation members are bare tagfiles inside a compressed ANIBND;
    # a newly constructed GameFile otherwise inherits its default DCX wrapper.
    hkx.dcx_type = DCXType.Null
    native = hkx.animation_container.hkx_animation
    # Carry authored timing in native annotation records as metadata. These are
    # NOT sound playback IDs, TAE events, ammo transfer, or a rumble adapter.
    annotations = [hkaAnnotationTrackAnnotation(time=cue["source_seconds"],
                    text="mw2_source:" + cue["kind"] + ":" + cue["alias"]) for cue in cues]
    native.annotationTracks[0].annotations = annotations
    encoded = bytes(hkx)
    require(encoded[4:8] == b"TAG0" and b"20150100" in encoded[:32], "Wrong target Havok format")
    decoded = AnimationHKX.from_bytes(encoded)
    container = decoded.animation_container
    require(container.is_interleaved and container.frame_count == frame_count, "Animation frame/codec mismatch")
    require(list(container.hkx_binding.transformTrackToBoneIndices) == tracks, "Native binding changed")
    require(container.hkx_binding.originalSkeletonName == "Master", "Native skeleton name changed")
    require(abs(container.hkx_animation.duration - animation.seconds) < 1e-6, "Source duration changed")
    require(container.hkx_animation.extractedMotion is None, "Unexpected player root motion")
    require(container.hkx_animation.numberOfFloatTracks == 0, "Unexpected float tracks")
    max_error = 0.0
    for original_frame, restored in zip(frames, container.interleaved_data, strict=True):
        for old, new in zip(original_frame, restored, strict=True):
            for field in ("translation", "rotation", "scale"):
                error = max(abs(float(a)-float(b)) for a, b in zip(getattr(old, field), getattr(new, field), strict=True))
                max_error = max(max_error, error)
                require(error < 1e-6, "Serialized pose component changed")
    restored_cues = container.hkx_animation.annotationTracks[0].annotations
    require(len(restored_cues) == len(annotations), "Source cue count changed")
    require(all(a.text == b.text and abs(a.time-b.time) < 1e-6 for a, b in zip(annotations, restored_cues)),
            "Source cue changed on round trip")
    # Preserve tiny native scale drift, including in these position metrics.
    # Full affine composition avoids silently unitizing the actual skeleton.
    worlds = []
    for pose in poses:
        matrices = []
        for b, t in enumerate(pose):
            require(parents[b] < b, "Expected topological native skeleton")
            matrix = np.eye(4)
            for axis in range(3):
                vector = tuple(scales[b][axis] if k == axis else 0 for k in range(3))
                matrix[:3, axis] = rotate(t.rotation, vector)
            matrix[:3, 3] = t.translation
            matrices.append(matrices[parents[b]] @ matrix if parents[b] >= 0 else matrix)
        worlds.append(matrices)
    hands = {}
    for name in ("L_Hand", "R_Hand"):
        bone = target_names.index(name)
        path = [tuple(world[bone][:3, 3]) for world in worlds]
        hands[name] = {"path_length_m": sum(math.dist(a, b) for a, b in zip(path, path[1:])),
                       "maximum_distance_from_first_m": max(math.dist(path[0], p) for p in path)}
    active = sum(any(abs(sum(a*b for a, b in zip(poses[0][bone].rotation, p[bone].rotation))) < .99999
                     for p in poses[1:]) for bone in tracks)
    require(active >= 2, "Candidate lost its motion")
    stem = "m9-" + clip + "-" + finger_mode + "-axial-study"
    destination = output / (stem + ".hkx")
    require(not destination.is_symlink(), "Candidate destination cannot be a symlink")
    destination.write_bytes(encoded)
    report = {
        "at": datetime.now(timezone.utc).isoformat(), "source_clip": clip_name, "source_sha256": proof["sha256"],
        "source_hand_rig_sha256": rig_sha, "source_weapon_sha256": weapon_sha,
        "target_skeleton_sha256": "6439d12659afa550ef2c296116d457dcabf0f5bf9760cbdf099d4a6db38a8917",
        "output": str(destination.relative_to(ROOT)), "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded), "havok_version": "20150100", "codec": "interleaved uncompressed",
        "target_skeleton": "Master", "target_bones": 61, "bound_tracks": len(tracks), "moving_tracks": active,
        "frame_count": frame_count, "frame_rate": rate, "duration_seconds": animation.seconds,
        "retarget_method": "Global source-idle-relative rotational delta applied to the real native a46_4000 first-frame pose; native local translations retained; no IK/contact solver",
        "finger_mode": finger_mode,
        "foretwist_method": "Native sibling elbow origin and native anchor twist retained; forearm swing plus half wrist axial roll; explicit target-rig authoring rule",
        "finger_retarget_method": ("Joint-local source-idle deltas transferred through each source/target reference bone's anatomical frame onto native grip"
                                   if finger_mode == "anatomical" else "Native DSR anchor finger rotations retained; MW2 finger articulation intentionally excluded"),
        "review_basis": "MW2 forward/left/up -> DSR -Z/+X/+Y, determinant -1; conjugation explicitly preserves handedness",
        "source_idle_sha256": idle_proof["sha256"], "native_anchor_sha256": anchor_sha, "native_anchor_entry": 464000,
        "bone_correspondence": by_name, "binding_indices": tracks,
        "source_pose_interpretation": "Viewhand parent-local absolute tracks; named NO_QUAT=identity, NO_TRANS=bind translation; absent bones=bind; relative j_gun subtree excluded",
        "interpretation_references": [
            "https://github.com/Scobalula/Greyhound/blob/master/src/WraithXCOD/WraithXCOD/CoDXAnimTranslator.cpp",
            "https://github.com/Scobalula/Greyhound/blob/master/src/WraithXCOD/WraithXCOD/GameModernWarfare2.cpp"],
        "references_read_only": True, "source_asset_type": 1, "asset_type_not_used_as_generic_semantics": True,
        "source_cues": cues, "source_cues_preserved_as_native_annotations": True,
        "maximum_serialization_component_error": max_error, "target_local_bone_lengths_preserved": True,
        "native_scales_preserved": True, "maximum_native_scale_deviation_from_one": scale_deviation,
        "source_bind_maps_to_target_bind": True, "unmapped_bones_in_binding": False,
        "hand_motion": hands, "roundtrip_passed": True,
        "installed": False, "game_launched": False, "renderer_used": False, "helper_executable_run": False,
        "runtime_verified": False, "ready_for_installation": False,
        "remaining": ["Review/correct first-person to full-body stance and hand contact on native skinned geometry",
                      "Weapon slide/magazine rig and attachment coupling; twist-bone correction",
                      "Native action/TAE/locomotion blend and cancellation integration",
                      "Native sound IDs and event binding; annotations are metadata only",
                      "Verify native acceptance of this partial interleaved animation before packaging"],
    }
    baseline = {"native_anchor_sha256": anchor_sha, "local": [{"translation": t.translation,
        "rotation": t.rotation, "scale": scales[i]} for i,t in enumerate(native_bind)]}
    baseline_bytes = json.dumps(baseline, separators=(",", ":"), allow_nan=False).encode()
    (output / "m9-native-anchor-pose.json").write_bytes(baseline_bytes)
    report["native_baseline_pose_sha256"] = hashlib.sha256(baseline_bytes).hexdigest()
    (output / (stem + "-report.json")).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    (output / "m9-reload-study-report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: report[k] for k in ("output", "output_sha256", "bytes", "bound_tracks", "moving_tracks",
                     "frame_count", "duration_seconds", "maximum_serialization_component_error", "roundtrip_passed",
                     "installed", "runtime_verified")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", choices=CLIPS, default="reload")
    parser.add_argument("--finger-mode", choices=("anatomical", "native-grip"), default="anatomical")
    options = parser.parse_args()
    main(options.clip, options.finger_mode)
