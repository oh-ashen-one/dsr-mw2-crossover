"""Correct measured reverse-facing triangles, preserving the prior package.

No game launch. This repairs a geometry error, not MW2 handling or visual quality
acceptance. Uses only the previously approved pinned Soulstruct installation.
"""
import hashlib
import json
from pathlib import Path

from dsr_mw2.install_private import WORKSPACE, PRESETS, STOCK_HASHES, checked_package
from dsr_mw2.model_candidate import read as read_candidate, PARTS
from dsr_mw2.package_loadout import package
from dsr_mw2.soulstruct_tools import configure
from dsr_mw2.runtime_paths import bottle_path
from tools.review_m9_attachment import read_model


def facing(mesh):
    import numpy as np
    a = mesh.vertex_arrays[0].array
    fs = mesh.face_sets[0]
    faces = fs.triangulate(uses_0xffff_separators=True) if fs.is_triangle_strip else fs.vertex_indices
    p = a['position'][faces]
    n = a['normal'][faces].mean(axis=1)
    dot = np.einsum('ij,ij->i', np.cross(p[:,1]-p[:,0], p[:,2]-p[:,0]), n)
    return {'triangles': len(faces), 'positive': int(sum(dot > 1e-10)),
            'negative': int(sum(dot < -1e-10)), 'ambiguous': int(sum(abs(dot) <= 1e-10))}


def main():
    configure()
    import numpy as np
    from soulstruct.containers import Binder
    original = bottle_path() / 'drive_c/Games/Dark Souls Remastered' / PARTS
    assert hashlib.sha256(original.read_bytes()).hexdigest() == STOCK_HASHES[str(PARTS)]
    native = Binder.from_path(original)
    stock = read_model(next(e for e in native.entries if e.path.endswith('.flver')).get_uncompressed_data())
    reference = [facing(mesh) for mesh in stock.meshes]
    assert all(r['positive'] == 0 and r['negative'] > 0 for r in reference)
    reports = []
    for variant in ('base', 'suppressed'):
        old = WORKSPACE / 'converted/dsr/m9-upright-v1' / variant
        report, data = read_candidate(old)
        binder = Binder.from_bytes(data)
        entry = next(e for e in binder.entries if e.path.endswith('.flver'))
        before = read_model(entry.get_uncompressed_data())
        model = read_model(entry.get_uncompressed_data())
        previous = [facing(mesh) for mesh in before.meshes]
        assert all(r['positive'] > 0 and r['negative'] == 0 for r in previous)
        for mesh in model.meshes:
            for fs in mesh.face_sets:
                assert not fs.is_triangle_strip
                fs.vertex_indices = fs.vertex_indices[:, ::-1].copy()
        entry.set_uncompressed_data(bytes(model))
        payload = bytes(binder)
        check_binder = Binder.from_bytes(payload)
        check = read_model(next(e for e in check_binder.entries if e.path.endswith('.flver')).get_uncompressed_data())
        current = [facing(mesh) for mesh in check.meshes]
        assert all(r['positive'] == 0 and r['negative'] > 0 for r in current)
        for a,b in zip(before.meshes, check.meshes, strict=True):
            assert a.material == b.material and np.array_equal(a.bone_indices, b.bone_indices)
            assert a.default_bone_index == b.default_bone_index
            assert np.array_equal(a.vertex_arrays[0].array, b.vertex_arrays[0].array)
            for x,y in zip(a.face_sets,b.face_sets,strict=True):
                assert np.array_equal(x.vertex_indices[:, ::-1], y.vertex_indices)
                assert x.flags == y.flags and x.use_backface_culling == y.use_backface_culling
        for a,b in zip(Binder.from_bytes(data).entries,check_binder.entries,strict=True):
            assert (a.path,a.entry_id,a.flags)==(b.path,b.entry_id,b.flags)
            if not a.path.endswith('.flver'): assert a.data == b.data
        # Bone/dummy dataclasses use identity equality. Undo just our face edits
        # and require the entire original FLVER byte-for-byte, including them.
        for mesh in check.meshes:
            for fs in mesh.face_sets:fs.vertex_indices = fs.vertex_indices[:, ::-1].copy()
        original_flver = next(e for e in Binder.from_bytes(data).entries if e.path.endswith('.flver'))
        assert bytes(check) == original_flver.get_uncompressed_data()
        report['derivation'] = {'previous_model_sha256':report['output_sha256'],
            'correction':'Reverse triangle indices to match measured native clockwise facing; vertex data, materials, bones and animations unchanged'}
        report['output_sha256'] = hashlib.sha256(payload).hexdigest()
        folder = WORKSPACE / 'converted/dsr/m9-winding-v2' / variant
        texts = json.loads((old / 'equipment-text/text-report.json').read_text())
        texts['model_candidate_sha256'] = report['output_sha256']
        files = {str(PARTS):payload, 'model-report.json':(json.dumps(report,indent=2)+'\n').encode(),
            'equipment-text/text-report.json':(json.dumps(texts,indent=2)+'\n').encode(),
            'equipment-text/msg/ENGLISH/item.msgbnd.dcx':(old/'equipment-text/msg/ENGLISH/item.msgbnd.dcx').read_bytes()}
        for rel, content in files.items():
            dest=folder/rel
            assert dest.resolve().is_relative_to(WORKSPACE/'converted') and not dest.is_symlink()
            if dest.exists() and dest.read_bytes()!=content:raise ValueError('Preserving different v2 data')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
        reports.append({'variant':variant,'before':previous,'after':current,
            'sha256':report['output_sha256'],'vertex_material_skeleton_animation_data_unchanged':True})
    for preset in PRESETS:
        variant='suppressed' if preset.endswith('-suppressed') else 'base'
        package(WORKSPACE/'loadouts'/(preset.removesuffix('-suppressed')+'.json'),
            output=WORKSPACE/'converted/packages/winding-v2'/preset,
            model=WORKSPACE/'converted/dsr/m9-winding-v2'/variant)
        checked_package(WORKSPACE,preset,'winding-v2')
    result={'native_reference':reference,'variants':reports,'game_launched':False,
        'runtime_visual_quality_verified':False,'handling_changed':False,'installed':False,
        'limitation':'Still lower-detail world mesh with native crossbow actions; not an accepted MW2 gameplay build'}
    (WORKSPACE/'evidence/m9-winding-correction.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
