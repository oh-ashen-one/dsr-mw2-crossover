"""Stage and measure native M9 attachment candidates with CPU geometry only.

Uses the already approved base Soulstruct; no Havok, Blender, DSAnimStudio,
loader, game, audio playback or GPU execution. Diagnostic poses are explicit
test transforms, never presented as decoded native animations.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from dsr_mw2.animation_pose import Transform, compose, quaternion_from_columns, read_rig, rotate
from dsr_mw2.flver_bone_bounds import read_bounds
from dsr_mw2.skin_geometry import (
    IDENTITY, dummy_position, mesh_displacement, point, skin, undo, world_transforms,
)
from dsr_mw2.soulstruct_tools import configure

ROOT = Path(__file__).resolve().parents[1]
PART = Path('parts/WP_A_1401.partsbnd.dcx')
SOURCE_RIG_SHA = 'd4aac5a90a906d4ae298755797012b913c0a1a1345e9f327fd8b9e701eacb273'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def native_rig(model):
    from soulstruct.utilities.maths import Matrix3
    parents, local = [], []
    for bone in model.bones:
        require(all(abs(float(x) - 1) < 1e-7 for x in bone.scale), 'Scaled FLVER needs separate scale treatment')
        matrix = Matrix3.from_euler_angles_rad(bone.rotate, order='xzy').data
        local.append(Transform(quaternion_from_columns(tuple(tuple(c) for c in matrix.T)), tuple(float(x) for x in bone.translate)))
        parents.append(int(bone.parent_bone_index))
    binds = world_transforms(parents, local)
    # Compare the independent hierarchy composition with the approved library.
    native = model.get_bone_tree().get_bone_armature_space_transforms()
    for own, (t, r, _) in zip(binds, native, strict=True):
        require(math.dist(own.translation, tuple(t)) < 1e-7, 'Native bind translation mismatch')
        for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            expected = tuple((r.data @ axis) + t.data)
            require(math.dist(point(own, axis), expected) < 1e-7, 'Native bind rotation mismatch')
    return parents, local, binds


def read_model(data):
    from soulstruct.flver import FLVER
    from soulstruct.utilities.maths import AABB, Vector3
    model = FLVER.from_bytes(data)
    bounds = read_bounds(data)
    require(len(bounds) == len(model.bones), 'Native bone bounds count differs')
    for bone, (low, high) in zip(model.bones, bounds, strict=True):
        bone.bounding_box = AABB(Vector3(low), Vector3(high))
    return model


def geometry(model):
    positions, influences, triangles = [], [], []
    for mesh in model.meshes:
        require(mesh.is_dynamic and len(mesh.vertex_arrays) == 1, 'Expected skinned single-layout M9 mesh')
        array = mesh.vertex_arrays[0].array
        base = len(positions)
        positions.extend(tuple(float(x) for x in p) for p in array['position'])
        for indices, weights in zip(array['bone_indices'], array['bone_weights'], strict=True):
            active = []
            for index, weight in zip(indices, weights, strict=True):
                require(math.isfinite(float(weight)) and weight >= 0, 'Invalid FLVER skin weight')
                if weight == 0:
                    continue
                index = int(index)
                if mesh.bone_indices is not None:
                    require(0 <= index < len(mesh.bone_indices), 'Vertex palette index outside mesh')
                    index = int(mesh.bone_indices[index])
                active.append((index, float(weight)))
            influences.append(tuple(active))
        faces = mesh.face_sets[0]
        require(not faces.is_triangle_strip, 'Unexpected triangle strip')
        triangles.extend(tuple(int(i) + base for i in face) for face in faces.vertex_indices)
    return positions, influences, triangles


def measure(model, muzzle, driving_bone):
    parents, local, binds = native_rig(model)
    positions, influences, triangles = geometry(model)
    dummy = model.dummies[0]
    used = sorted({i for weights in influences for i, _ in weights})
    require(len(used) == 1, 'This diagnostic expects the current rigid M9')
    restored = skin(positions, influences, binds, binds)
    require(mesh_displacement(positions, restored) < 1e-6, 'Inverse bind distorts actual M9 vertices')
    posed_local = list(local)
    rotation = (0, 0, math.sin(math.radians(15) / 2), math.cos(math.radians(15) / 2))
    posed_local[driving_bone] = compose(Transform(rotation, (.02, .01, .03)), local[driving_bone])
    articulated = world_transforms(parents, posed_local)
    turn = Transform((0, math.sqrt(.5), 0, math.sqrt(.5)), (1.25, .75, -2.0))
    cases = [('bind', binds, IDENTITY), ('attachment_15deg_37mm', articulated, IDENTITY),
             ('same_pose_world_turn_90deg', articulated, turn)]
    results = []
    for name, pose, world in cases:
        deformed = skin(positions, influences, binds, pose)
        vertices_world = tuple(point(world, p) for p in deformed)
        # World-space skinning must agree with applying world after model-space skinning.
        direct_world = skin(positions, influences, binds, tuple(compose(world, p) for p in pose))
        world_error = mesh_displacement(vertices_world, direct_world)
        require(world_error < 1e-6, 'World transform convention differs from skinning')
        edge_error = max(abs(math.dist(positions[a], positions[b]) - math.dist(vertices_world[a], vertices_world[b]))
                         for triangle in triangles for a, b in zip(triangle, triangle[1:] + triangle[:1], strict=True))
        require(edge_error < 1e-6, 'Rigid M9 changed shape under the pose')
        mesh_muzzle = skin((muzzle,), (((used[0], 1.0),),), binds, pose)[0]
        attach = dummy_position(tuple(dummy.translate), int(dummy.parent_bone_index), int(dummy.attach_bone_index),
                                bool(dummy.follows_attach_bone), binds, pose)
        muzzle_direction = rotate(compose(pose[used[0]], undo(binds[used[0]])).rotation, (-1, 0, 0))
        reference_direction = rotate(binds[dummy.parent_bone_index].rotation, tuple(dummy.forward))
        dummy_direction = rotate(compose(pose[dummy.attach_bone_index], undo(binds[dummy.attach_bone_index])).rotation,
                                 reference_direction)
        length = math.sqrt(sum(v * v for v in dummy_direction))
        require(length > 1e-8, 'Zero native dummy direction')
        cosine = sum(a * b / length for a, b in zip(muzzle_direction, dummy_direction, strict=True))
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        results.append({'pose': name, 'actual_vertices_deformed': len(positions),
                        'maximum_model_vertex_displacement_m': mesh_displacement(positions, deformed),
                        'muzzle_to_dummy_distance_m': math.dist(point(world, mesh_muzzle), point(world, attach)),
                        'muzzle_to_dummy_forward_angle_degrees': angle,
                        'maximum_triangle_edge_length_error_m': edge_error,
                        'world_skinning_equivariance_error_m': world_error})
    return {'weighted_global_bones': used, 'vertices': len(positions), 'triangles': len(triangles),
            'bind_vertex_error_m': mesh_displacement(positions, restored), 'poses': results}


def stage(folder_name, variant, source_points):
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.utilities.maths import AABB, Vector3

    folder = ROOT / 'converted/dsr' / folder_name
    proof = json.loads((folder / 'model-report.json').read_text())
    original_data = (folder / PART).read_bytes()
    require(digest(original_data) == proof['output_sha256'], 'Prepared M9 binder changed')
    points = proof['source']['attachment_points']
    require(points['bone_export_sha256'] == SOURCE_RIG_SHA, 'Source grip/muzzle identity changed')
    for key, value in source_points.items():
        require(math.dist(points[key], value) < 1e-8, 'Stored grip/muzzle differs from original source rig')
    key = 'suppressed_muzzle_obj' if variant == 'suppressed' else 'muzzle_obj'
    muzzle = tuple((a - b) * scale for a, b, scale in zip(points[key], points['grip_obj'], (-.0254, .0254, .0254), strict=True))
    binder = Binder.from_bytes(original_data)
    entry = next(e for e in binder.entries if e.path.endswith('.flver'))
    original = read_model(entry.get_uncompressed_data())
    require([b.name for b in original.bones] == ['WP_A_1401', 'move_poit', 'move_poit01', 'move_poit04',
                                               'move_poit02', 'move_poit03', 'Model_Dmy'], 'Native skeleton changed')
    require(len(original.dummies) == 1, 'Unexpected native attachment count')
    dummy = original.dummies[0]
    require((dummy.reference_id, dummy.parent_bone_index, dummy.attach_bone_index, dummy.follows_attach_bone)
            == (2, 6, 1, True), 'Native dummy identity changed')
    before = measure(original, muzzle, driving_bone=1)
    require(before['weighted_global_bones'] == [0], 'Original M9 attachment changed')
    candidate = copy.deepcopy(original)
    _, _, binds = native_rig(candidate)
    for mesh in candidate.meshes:
        # Keep bind positions/grip fixed. Only the motion delta now comes from
        # the same measured native bone that the attachment follows.
        mesh.bone_indices = np.array([1], dtype=np.int32)
    candidate.dummies[0].translate = Vector3(point(undo(binds[6]), muzzle))
    # Compute bounds from explicit effective weights; retain other bone boxes.
    # read_model restores the raw bounds lost by the pinned FLVERBone reader.
    positions, influences, _ = geometry(candidate)
    require(all(weights == ((1, 1.0),) for weights in influences), 'Candidate is not rigidly bound to bone 1')
    local_positions = [point(undo(binds[1]), p) for p in positions]
    candidate.bones[1].bounding_box = AABB(
        Vector3(tuple(min(p[axis] for p in local_positions) for axis in range(3))),
        Vector3(tuple(max(p[axis] for p in local_positions) for axis in range(3))))
    entry.set_uncompressed_data(bytes(candidate))
    encoded = bytes(binder)
    reloaded = Binder.from_bytes(encoded)
    checked = read_model(next(e for e in reloaded.entries if e.path.endswith('.flver')).get_uncompressed_data())
    for old, new in zip(Binder.from_bytes(original_data).entries, reloaded.entries, strict=True):
        require((old.entry_id, old.path, old.flags) == (new.entry_id, new.path, new.flags), 'Binder routing changed')
        if not old.path.endswith('.flver'):
            require(old.data == new.data, 'Native animation/texture member changed')
    for old, new in zip(original.bones, checked.bones, strict=True):
        for field in ('name', 'translate', 'rotate', 'scale', 'parent_bone_index', 'child_bone_index',
                      'next_sibling_bone_index', 'previous_sibling_bone_index', 'usage_flags'):
            require(getattr(old, field) == getattr(new, field), 'Native bind skeleton changed')
    for index, (old, new) in enumerate(zip(original.bones, checked.bones, strict=True)):
        if index != 1:
            require(tuple(old.bounding_box.min) == tuple(new.bounding_box.min)
                    and tuple(old.bounding_box.max) == tuple(new.bounding_box.max), 'Unrelated bone bounds changed')
    for old, new in zip(original.meshes, checked.meshes, strict=True):
        require(old.material == new.material and old.default_bone_index == new.default_bone_index and old.is_dynamic == new.is_dynamic,
                'Material/mesh mode changed')
        require(np.array_equal(new.bone_indices, [1]), 'Candidate mesh attachment did not persist')
        for name in old.vertex_arrays[0].array.dtype.names:
            require(np.array_equal(old.vertex_arrays[0].array[name], new.vertex_arrays[0].array[name]), 'Vertex data changed: ' + name)
        for a, b in zip(old.face_sets, new.face_sets, strict=True):
            require(np.array_equal(a.vertex_indices, b.vertex_indices), 'Triangles changed')
    for field in ('reference_id', 'parent_bone_index', 'attach_bone_index', 'follows_attach_bone', 'use_upward_vector',
                  'forward', 'upward', 'unk_x30', 'unk_x34'):
        require(getattr(dummy, field) == getattr(checked.dummies[0], field), 'Native dummy semantics changed')
    after = measure(checked, muzzle, driving_bone=1)
    require(max(p['muzzle_to_dummy_distance_m'] for p in after['poses']) < 1e-6, 'Staged dummy does not follow muzzle')
    require(max(p['muzzle_to_dummy_forward_angle_degrees'] for p in after['poses']) < .001, 'Muzzle and dummy directions differ')
    require(after['poses'][1]['maximum_model_vertex_displacement_m'] > .02, 'Actual geometry did not follow attachment pose')
    # Check actual deformed geometry's culling bounds in the weighted bone's
    # local bind space, rather than accepting refreshed bounds on faith.
    positions, _, _ = geometry(checked)
    bounds = checked.bones[1].bounding_box
    for position in positions:
        local_point = point(undo(binds[1]), position)
        require(all(float(low) - 1e-6 <= value <= float(high) + 1e-6
                    for value, low, high in zip(local_point, bounds.min, bounds.max, strict=True)),
                'Native weighted-bone culling bounds exclude a vertex')
    output = ROOT / 'converted/dsr/m9-attachment-review' / variant / PART
    require(output.resolve().is_relative_to(ROOT / 'converted') and not output.is_symlink(), 'Output escaped task assets')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    require((folder / PART).read_bytes() == original_data, 'Existing M9 candidate changed')
    return {'variant': variant, 'input_sha256': digest(original_data), 'candidate_sha256': digest(encoded),
            'output': str(output.relative_to(ROOT)), 'source_muzzle_in_mesh_space_m': muzzle,
            'before': before, 'candidate': after, 'native_animation_and_texture_bytes_preserved': True,
            'bind_geometry_and_grip_preserved': True, 'weighted_bone_culling_bounds_checked': True,
            'installed': False, 'runtime_verified': False}


def main():
    configure()
    source_path = ROOT / 'converted/mw2-2009/unlinked/m9-native64/model_export/weapon_beretta_lod0.xmodel_export'
    source = source_path.read_bytes()
    require(digest(source) == SOURCE_RIG_SHA, 'Authentic source rig revision differs')
    bones = {bone.name: bone for bone in read_rig(source.decode('ascii'))}
    points = {}
    for name, key in (('j_pistol_grip', 'grip_obj'), ('tag_flash', 'muzzle_obj'), ('tag_flash_silenced', 'suppressed_muzzle_obj')):
        x, y, z = bones[name].global_bind.translation
        points[key] = (x, z, -y)  # OAT's inspected source -> OBJ basis.
    results = [stage('m9-model-candidate', 'base', points), stage('m9-suppressed-model-candidate', 'suppressed', points)]
    report = {'at': datetime.now(timezone.utc).isoformat(), 'variants': results,
              'source_rig_sha256': SOURCE_RIG_SHA, 'pose_source': 'explicit synthetic attachment/world transforms',
              'candidate_changes': ['mesh bone palette 0 -> native attachment bone 1',
                                    'dummy 2 position aligned to authentic muzzle in parent-bone bind space',
                                    'bone 1 culling bounds computed from explicit weighted vertices; other boxes preserved'],
              'bounds_reader_finding': 'Pinned Soulstruct FLVERBone reader loses bounding_box_min/max when building the object. Original fixed-record reader restores them; changed bone bounds verified from serialized bytes',
              'limits': ['No native HKX animation was decoded or played; diagnostic poses are not native firing/reload poses',
                         'Dummy parent-reference/attach-delta convention needs native playback confirmation',
                         'Dummy 2 use as actual projectile origin is not established by this geometry check',
                         'No player hand pose/contact, stance, slide/magazine articulation, reload, recoil or timing verified',
                         'M9 still uses the rigid MW2 world model and preserved native crossbow animations'],
              'installed': False, 'game_launched': False, 'renderer_used': False, 'runtime_verified': False,
              'references_read_only': [
                  'https://github.com/Grimrukh/soulstruct-blender/blob/548afaae652ece0a6eac30b125b5e60cbd7bee00/io_soulstruct/soulstruct/blender/flver/models/types/bl_flver_dummy.py',
                  'https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/NewDummyPolyInfo.cs']}
    (ROOT / 'evidence/m9-attachment-review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
