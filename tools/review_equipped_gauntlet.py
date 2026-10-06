"""Read-only CPU comparison of the actual disposable character's gauntlet."""
import hashlib
import json
from pathlib import Path
from dsr_mw2.animation_pose import rotate
from tools.havok_offline_trial import main as approved_havok

ROOT = Path(__file__).resolve().parents[1]


def main():
    proof = json.loads((ROOT / 'evidence/native-validation-armor.json').read_text())['gauntlet_part']
    skeleton, output = approved_havok()
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER
    from soulstruct.utilities.maths import Matrix3
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from dsr_mw2.runtime_paths import bottle_path
    raw = (bottle_path() / 'drive_c/Games/Dark Souls Remastered/parts' / proof['part']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == proof['part_sha256']
    model = FLVER.from_bytes(next(e for e in Binder.from_bytes(raw).entries if e.path.lower().endswith('.flver')).get_uncompressed_data())
    sk = skeleton.skeleton.skeleton
    names = [b.name for b in sk.bones]

    def hierarchy(local, parents):
        done = {}
        def get(i):
            if i not in done:
                done[i] = get(parents[i]) @ local[i] if parents[i] >= 0 else local[i]
            return done[i]
        return np.array([get(i) for i in range(len(local))])

    bind_local = []
    for bone in model.bones:
        m = np.eye(4)
        m[:3, :3] = Matrix3.from_euler_angles_rad(bone.rotate, order='xzy').data @ np.diag(tuple(bone.scale))
        m[:3, 3] = tuple(bone.translate)
        bind_local.append(m)
    bind = hierarchy(bind_local, [int(b.parent_bone_index) for b in model.bones])
    inverse_bind = np.linalg.inv(bind)
    poses = {}
    clips = {}
    anchor_path = output / 'm9-native-anchor-pose.json'
    anchor_bytes = anchor_path.read_bytes()
    anchor = json.loads(anchor_bytes)['local']
    local = []
    for t in anchor:
        m = np.eye(4)
        for axis in range(3):
            m[:3, axis] = rotate(tuple(t['rotation']), tuple(float(t['scale'][k]) if k == axis else 0. for k in range(3)))
        m[:3, 3] = t['translation'][:3]
        local.append(m)
    poses['native_anchor'] = hierarchy(local, [int(p) for p in sk.parentIndices])
    clips['native_anchor'] = {'path': str(anchor_path.relative_to(ROOT)), 'sha256': hashlib.sha256(anchor_bytes).hexdigest()}
    for variant in ('player-raised-v7', 'player-contact-v8', 'player-landmark-v9'):
        report = json.loads((output / variant / 'report.json').read_text())
        record = next(c for c in report['clips'] if c['source_clip'] == 'm9_ready_hold')
        data = (ROOT / record['spline']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == record['spline_sha256']
        c = AnimationHKX.from_bytes(data).animation_container
        c.load_spline_data()
        assert c.hkx_binding.transformTrackToBoneIndices == list(range(61))
        local = []
        for track in c.spline_data.blocks[0]:
            t = track.get_trs_transform_at_frame(0)
            m = np.eye(4)
            for axis in range(3):
                m[:3, axis] = rotate(tuple(t.rotation), tuple(float(t.scale[k]) if k == axis else 0. for k in range(3)))
            m[:3, 3] = tuple(t.translation)
            local.append(m)
        poses[variant] = hierarchy(local, [int(p) for p in sk.parentIndices])
        clips[variant] = {'path': record['spline'], 'sha256': record['spline_sha256']}
    results = []
    for index, mesh in enumerate(model.meshes):
        assert mesh.is_dynamic and len(mesh.vertex_arrays) == 1
        v = mesh.vertex_arrays[0].array
        p = np.column_stack((v['position'].astype(float), np.ones(len(v))))
        weights = v['bone_weights'].astype(float)
        palette = mesh.bone_indices[v['bone_indices'].astype(int)].astype(int)
        assert np.all(weights >= 0) and np.all(weights.sum(axis=1) > .99)
        used = sorted(set(int(i) for i in palette[weights > 0]))
        mapping = {i: names.index(model.bones[i].name) for i in used}
        triangles = mesh.face_sets[0].triangulate(uses_0xffff_separators=True, include_degenerate_faces=False)
        edges = np.unique(np.sort(np.concatenate([triangles[:, (0,1)], triangles[:, (1,2)], triangles[:, (2,0)]]), axis=1), axis=0)
        lengths = np.linalg.norm(p[edges[:,0],:3] - p[edges[:,1],:3], axis=1)
        edges, lengths = edges[lengths > 1e-5], lengths[lengths > 1e-5]
        variants = {}
        for variant, pose in poses.items():
            delta = np.repeat(np.eye(4)[None,:,:], len(model.bones), axis=0)
            for i, n in mapping.items(): delta[i] = pose[n] @ inverse_bind[i]
            xyz = np.einsum('vki,vk->vi', np.einsum('vkij,vj->vki', delta[palette], p), weights)[:,:3] / weights.sum(axis=1)[:,None]
            ratios = np.linalg.norm(xyz[edges[:,0]] - xyz[edges[:,1]], axis=1) / lengths
            variants[variant] = {'max_edge_stretch': float(ratios.max()), 'p99_edge_stretch': float(np.quantile(ratios,.99)),
                                 'edges_above_2x': int(sum(ratios>2)), 'bounds_min': xyz.min(axis=0).tolist(), 'bounds_max': xyz.max(axis=0).tolist()}
        results.append({'mesh': index, 'vertices': len(v), 'edges': len(edges), 'variants': variants})
    result = {'actual_gauntlet': proof, 'clips': clips, 'meshes': results,
              'scope': 'CPU skinning of actual equipped native gauntlet at held frame0; not actual native blended skeleton or a rendering acceptance'}
    destination = output / 'actual-gauntlet-study.json'
    destination.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
