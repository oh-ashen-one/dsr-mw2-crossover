"""CPU-only deformation of actual native DSR arm geometry by the reload study.

Reads private stock and staged files; never writes game/model/animation files.
This checks a skinning convention, not native rendering or player hand contact.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

from dsr_mw2.animation_pose import rotate
from tools.havok_offline_trial import main as skeleton_trial

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main(attachment_report="evidence/m9-attachment-review.json"):
    attachment_path = (ROOT/attachment_report).resolve()
    require(attachment_path.is_relative_to(ROOT), "Attachment report outside task")
    skeleton, output = skeleton_trial()
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER
    from soulstruct.utilities.maths import Matrix3
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX

    def affine(t, r, s):
        matrix = np.eye(4)
        for axis in range(3):
            v = tuple(float(s[axis]) if k == axis else 0.0 for k in range(3))
            matrix[:3, axis] = rotate(tuple(r), v)
        matrix[:3, 3] = tuple(t)[:3]
        return matrix

    def hierarchy(local, parents):
        done, visiting = {}, set()
        def resolve(i):
            if i in done: return done[i]
            require(i not in visiting and -1 <= parents[i] < len(local), "Invalid skeleton hierarchy")
            visiting.add(i)
            done[i] = resolve(parents[i]) @ local[i] if parents[i] >= 0 else local[i]
            visiting.remove(i)
            return done[i]
        return np.array([resolve(i) for i in range(len(local))])

    path = ROOT / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/AM_M_0000.partsbnd.dcx"
    data = path.read_bytes()
    source_sha = hashlib.sha256(data).hexdigest()
    require(source_sha == "f22b4dce9ca629801f765125bf8baf08e4259e46748ccd45e8de7e4b98d5feaf", "Native arm part changed")
    binder = Binder.from_bytes(data)
    raw = next(e for e in binder.entries if e.path.lower().endswith(".flver")).get_uncompressed_data()
    model = FLVER.from_bytes(raw)
    require(len(model.meshes) == 1 and len(model.bones) == 78, "Unexpected native arm structure")
    local = []
    for bone in model.bones:
        matrix = np.eye(4)
        matrix[:3, :3] = Matrix3.from_euler_angles_rad(bone.rotate, order="xzy").data @ np.diag(tuple(bone.scale))
        matrix[:3, 3] = tuple(bone.translate)
        local.append(matrix)
    flver_bind = hierarchy(local, [int(b.parent_bone_index) for b in model.bones])
    mesh = model.meshes[0]
    require(mesh.is_dynamic and len(mesh.vertex_arrays) == 1 and mesh.bone_indices is not None, "Unexpected skin layout")
    vertices = mesh.vertex_arrays[0].array
    positions = np.column_stack((vertices["position"].astype(float), np.ones(len(vertices))))
    weights = vertices["bone_weights"].astype(float)
    indices = vertices["bone_indices"].astype(int)
    require(np.isfinite(weights).all() and (weights >= 0).all(), "Invalid weights")
    require(np.max(np.abs(weights.sum(axis=1)-1)) < 1e-4, "Skin weights do not sum to one")
    require((indices >= 0).all() and (indices < len(mesh.bone_indices)).all(), "Invalid skin palette index")
    global_indices = mesh.bone_indices[indices].astype(int)
    used = sorted(set(int(b) for b in global_indices[weights > 0]))
    target = skeleton.skeleton.skeleton
    native_names = [b.name for b in target.bones]
    mapping = {b: native_names.index(model.bones[b].name) for b in used}
    native_parents = [int(p) for p in target.parentIndices]
    native_local = [affine(t.translation, t.rotation, t.scale) for t in target.referencePose]
    native_bind = hierarchy(native_local, native_parents)
    bind_error = max(float(np.max(np.abs(flver_bind[b]-native_bind[n]))) for b, n in mapping.items())
    # These are intentionally two distinct rest spaces. The native authoring
    # reference maps HKX FK by bone name, retaining each FLVER inverse bind.
    # Requiring HKX reference == FLVER bind was an incorrect earlier gate.
    # Validate inverse-bind identity in FLVER's own rest space instead; retain
    # and measure the legitimate HKX reference deformation without correction.
    inverse_bind = np.linalg.inv(flver_bind)

    def deform(pose):
        delta = np.repeat(np.eye(4)[None, :, :], len(model.bones), axis=0)
        for b, n in mapping.items(): delta[b] = pose[n] @ inverse_bind[b]
        transformed = np.einsum("vkij,vj->vki", delta[global_indices], positions)
        # Quantized native weights differ from one by about 1/32767. Match the
        # reference CPU skinning's explicit division by total weight; preserve
        # the file weights themselves and report their original quantization.
        out = np.einsum("vki,vk->vi", transformed, weights)[:, :3] / weights.sum(axis=1)[:, None]
        require(np.isfinite(out).all(), "Nonfinite native skinned geometry")
        return out

    flver_as_pose = np.repeat(np.eye(4)[None, :, :], len(native_names), axis=0)
    for b, n in mapping.items(): flver_as_pose[n] = flver_bind[b]
    flver_restored = deform(flver_as_pose)
    rest_error = float(np.max(np.linalg.norm(flver_restored-positions[:, :3], axis=1)))
    require(rest_error < 2e-5, "Actual arm mesh does not reconstruct in its own FLVER bind space")
    restored = deform(native_bind)
    reference_displacement = float(np.max(np.linalg.norm(restored-positions[:, :3], axis=1)))
    triangles = mesh.face_sets[0].triangulate(uses_0xffff_separators=True, include_degenerate_faces=False)
    require(len(triangles) > 0 and int(triangles.max()) < len(vertices), "Invalid native triangles")
    edges = np.unique(np.sort(np.concatenate([triangles[:, (0, 1)], triangles[:, (1, 2)], triangles[:, (2, 0)]]), axis=1), axis=0)
    lengths = np.linalg.norm(positions[edges[:, 0], :3]-positions[edges[:, 1], :3], axis=1)
    edges, lengths = edges[lengths > 1e-5], lengths[lengths > 1e-5]
    proof = json.loads((output / "m9-reload-study-report.json").read_text())
    animation_path = (ROOT / proof["output"]).resolve()
    require(animation_path.is_relative_to(output.resolve()), "Animation candidate escaped task output")
    raw_animation = animation_path.read_bytes()
    animation_sha = hashlib.sha256(raw_animation).hexdigest()
    require(animation_sha == proof["output_sha256"], "Reload candidate differs from checked report")
    container = AnimationHKX.from_bytes(raw_animation).animation_container
    bound = list(container.hkx_binding.transformTrackToBoneIndices)
    baseline_bytes = (output / "m9-native-anchor-pose.json").read_bytes()
    require(hashlib.sha256(baseline_bytes).hexdigest() == proof["native_baseline_pose_sha256"], "Native stance baseline changed")
    baseline = json.loads(baseline_bytes)["local"]
    require(len(baseline) == len(native_local), "Native baseline bone count changed")
    baseline_local = [affine(t["translation"],t["rotation"],t["scale"]) for t in baseline]
    baseline_vertices = deform(hierarchy(baseline_local, native_parents))
    baseline_edge_lengths = np.linalg.norm(baseline_vertices[edges[:, 0]]-baseline_vertices[edges[:, 1]], axis=1)
    baseline_ratios = baseline_edge_lengths/lengths
    attachment = json.loads(attachment_path.read_text())["variants"][0]
    gun_raw = (ROOT / attachment["output"]).read_bytes()
    require(hashlib.sha256(gun_raw).hexdigest() == attachment["candidate_sha256"], "Staged weapon candidate changed")
    gun_binder = Binder.from_bytes(gun_raw)
    gun_model = FLVER.from_bytes(next(e for e in gun_binder.entries if e.path.lower().endswith(".flver")).get_uncompressed_data())
    gun_positions, gun_triangles = [], []
    for gun_mesh in gun_model.meshes:
        require(len(gun_mesh.vertex_arrays) == 1, "Unexpected weapon vertex layout")
        offset = len(gun_positions)
        gun_positions.extend(gun_mesh.vertex_arrays[0].array["position"].tolist())
        faces = gun_mesh.face_sets[0].triangulate(uses_0xffff_separators=True, include_degenerate_faces=False)
        gun_triangles.extend((faces + offset).tolist())
    require(len(gun_positions) == 765 and len(gun_triangles) == 558, "Unexpected authentic M9 geometry")
    gun_positions = np.column_stack((np.array(gun_positions), np.ones(len(gun_positions))))
    # DSR's right-weapon attachment convention applies pi rotations about X
    # and Y before R_Weapon FK (row convention in reviewed reference source).
    # In column convention their product is diag(-1,-1,+1). Do not flip the
    # actual mesh to compensate for an omitted attachment rotation.
    weapon_flip = np.diag((-1.0,-1.0,1.0,1.0))
    weapon_index = native_names.index("R_Weapon")
    muzzle_local = np.array([*attachment["source_muzzle_in_mesh_space_m"],1.0])
    anchor_attachment = hierarchy(baseline_local,native_parents)[weapon_index] @ weapon_flip
    anchor_forward = anchor_attachment[:3,:3] @ np.array([-1.0,0,0])
    weapon_samples = []
    per_frame = []
    samples = []
    for frame, transforms in enumerate(container.interleaved_data):
        posed = list(baseline_local)
        for b, t in zip(bound, transforms, strict=True): posed[b] = affine(t.translation, t.rotation, t.scale)
        posed_world = hierarchy(posed, native_parents)
        deformed = deform(posed_world)
        weapon_transform = posed_world[weapon_index] @ weapon_flip
        gun_world = (weapon_transform @ gun_positions.T).T[:,:3]
        require(np.isfinite(gun_world).all(), "Nonfinite attached weapon geometry")
        muzzle_world = (weapon_transform @ muzzle_local)[:3]
        muzzle_forward = weapon_transform[:3,:3] @ np.array([-1.0,0,0])
        weapon_samples.append({"frame":frame,"muzzle":muzzle_world.tolist(),"forward":muzzle_forward.tolist()})
        ratios = np.linalg.norm(deformed[edges[:, 0]]-deformed[edges[:, 1]], axis=1)/lengths
        worst_index = int(ratios.argmax())
        worst_vertices = edges[worst_index]
        per_frame.append({"frame": frame, "maximum_edge_stretch": float(ratios.max()),
                          "edges_stretched_over_2x": int((ratios > 2).sum()),
                          "maximum_edge_length_increase_from_native_anchor_m": float(np.max(ratios*lengths-baseline_edge_lengths)),
                          "worst_edge_bind_length_m": float(lengths[worst_index]),
                          "worst_edge_animated_length_m": float(ratios[worst_index]*lengths[worst_index]),
                          "worst_edge_vertices": [int(v) for v in worst_vertices],
                          "worst_edge_weights": [{model.bones[int(b)].name: float(w) for b,w in zip(global_indices[v], weights[v]) if w > 0} for v in worst_vertices],
                          "maximum_vertex_motion_from_bind_m": float(np.max(np.linalg.norm(deformed-restored, axis=1)))})
        if frame in (0, 18, 64, 72, len(container.interleaved_data)-1):
            samples.append({"frame": frame, "vertices": deformed.tolist(), "bones": posed_world[:, :3, 3].tolist(),
                            "weapon_vertices":gun_world.tolist(), "muzzle":muzzle_world.tolist(), "muzzle_forward":muzzle_forward.tolist()})
    worst = max(per_frame, key=lambda x: x["maximum_edge_stretch"])
    unbound_used = [model.bones[b].name for b, n in mapping.items() if n not in bound]
    report = {"at": datetime.now(timezone.utc).isoformat(), "native_part": path.name,
              "native_part_sha256": source_sha, "native_flver_sha256": hashlib.sha256(raw).hexdigest(),
              "animation_sha256": animation_sha, "vertices": len(vertices), "triangles": len(triangles),
              "unique_edges": len(edges), "weighted_bones": len(used), "animation_frames_checked": len(per_frame),
              "native_hkx_flver_bind_matrix_error": bind_error, "rest_vertex_error_m": rest_error,
              "native_hkx_reference_mesh_displacement_m": reference_displacement,
              "reference_spaces_preserved_separately": True,
              "native_anchor_maximum_edge_stretch": float(baseline_ratios.max()),
              "native_anchor_edges_stretched_over_2x": int((baseline_ratios > 2).sum()),
              "skinning_contract": "Map HKX global pose by exact bone name, then multiply by inverse FLVER global bind; column-vector convention",
              "contract_source": "https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/NewAnimSkeleton.cs",
              "inverse_bind_source": "https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/NewAnimSkeleton_FLVER.cs",
              "reference_application_executed": False, "reference_alignment_resolved_offline": True,
              "weight_evaluation": "Weighted sum divided by original quantized weight sum, matching reference CPU SkinVector3; no file weight changes",
              "weight_evaluation_source": "https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/FlverSubmeshRenderer.cs",
              "weights_max_sum_error": float(np.max(np.abs(weights.sum(axis=1)-1))),
              "worst_frame": worst, "weighted_bones_missing_animation_tracks": unbound_used,
              "maximum_edge_length_increase_from_native_anchor_m": max(f["maximum_edge_length_increase_from_native_anchor_m"] for f in per_frame),
              "all_frames_finite": True, "runtime_verified": False, "installed": False, "renderer_used": False,
              "ready_for_installation": False,
              "attached_weapon_sha256": attachment["candidate_sha256"],
              "attached_weapon_vertices_per_frame":len(gun_positions),
              "weapon_attachment_reference":"https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/NewChrAsm.cs#L699",
              "native_anchor_weapon_forward":anchor_forward.tolist(),
              "weapon_limit":"Rigid weapon at parts bind, following actual player R_Weapon FK and reference right-hand flips; no slide/magazine or parts-animation playback",
              "limits": ["CPU inverse-bind linear skinning; native renderer/armor variants not tested",
                         "Edge ratios are distortion diagnostics, not a visual acceptance threshold",
                         "Native hand-to-gun contact and twist deformation still need authoring/review"]}
    (output / "m9-reload-geometry-report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output / (animation_path.stem + "-geometry-report.json")).write_text(json.dumps(report, indent=2)+"\n")
    (output / "m9-reload-geometry-samples.json").write_text(json.dumps({"samples": samples, "triangles": triangles.tolist(),
        "edges": edges.tolist(), "parents": native_parents, "bone_names": native_names,
        "weapon_triangles":gun_triangles}, separators=(",", ":"))+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachment-report",default="evidence/m9-attachment-review.json")
    if main(parser.parse_args().attachment_report) is False:
        raise SystemExit(2)
