"""Inspect the actual installed M9 route and private saved equipment, offline."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from dsr_mw2.install_private import WORKSPACE, inspect_install, layout
from dsr_mw2.install_audio import check as check_audio
from dsr_mw2.launch import preflight
from dsr_mw2.loadouts import load
from dsr_mw2.native_audit import verify_parameters, verify_equipment_text
from dsr_mw2.owner_launch import equipment_message
from dsr_mw2.save_inspect import inspect_private
from dsr_mw2.soulstruct_tools import configure


def main():
    state = inspect_install()
    if not state['installed'] or not state['stock_baseline_preserved']:
        raise ValueError('Installed package or stock baseline does not match')
    bottle, stock, candidate = layout(WORKSPACE)
    alias = bottle/'drive_c/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED'
    if not alias.is_symlink() or alias.resolve() != candidate.resolve():
        raise ValueError('Private Steam alias is not selecting the M9 copy')
    configure()
    import numpy as np
    from soulstruct.containers import Binder, TPF
    from tools.review_m9_attachment import read_model, geometry, measure

    rel = 'param/GameParam/GameParam.parambnd.dcx'
    definition = load(WORKSPACE/'loadouts'/(state['preset'].removesuffix('-suppressed')+'.json'))
    params = verify_parameters((stock/rel).read_bytes(),(candidate/rel).read_bytes(),definition)
    rel = 'msg/ENGLISH/item.msgbnd.dcx'
    text = verify_equipment_text((stock/rel).read_bytes(),(candidate/rel).read_bytes(),state['preset'].endswith('-suppressed'))
    rel = 'parts/WP_A_1401.partsbnd.dcx'
    data = (candidate/rel).read_bytes()
    model_binder = Binder.from_bytes(data)
    original = Binder.from_path(stock/rel)
    for before, after in zip(original.entries, model_binder.entries, strict=True):
        if (before.path,before.entry_id,before.flags) != (after.path,after.entry_id,after.flags):
            raise ValueError('Native parts binder identity changed')
        if not before.path.endswith(('.flver','.tpf')) and before.data != after.data:
            raise ValueError('Native animation binder member changed')
    model = read_model(next(e for e in model_binder.entries if e.path.endswith('.flver')).get_uncompressed_data())
    tpf = TPF.from_bytes(next(e for e in model_binder.entries if e.path.endswith('.tpf')).get_uncompressed_data())
    stems = {t.stem.lower() for t in tpf.textures}
    for mesh in model.meshes:
        array = mesh.vertex_arrays[0].array
        if not np.isfinite(array['position']).all() or not np.isfinite(array['normal']).all():
            raise ValueError('Non-finite M9 geometry')
        for texture in mesh.material.textures:
            if texture.path and Path(texture.path.replace('\\','/')).stem.lower() not in stems:
                raise ValueError('M9 material lacks its native texture')
    review = json.loads((WORKSPACE/'converted/dsr/m9-upright-review/report.json').read_text())
    attachment_sha = hashlib.sha256(data).hexdigest()
    if state.get('revision') == 'winding-v2':
        from dsr_mw2.model_candidate import read as read_candidate
        variant = 'suppressed' if state['preset'].endswith('-suppressed') else 'base'
        revision, checked = read_candidate(WORKSPACE/'converted/dsr/m9-winding-v2'/variant)
        if checked != data:
            raise ValueError('Installed winding correction differs from verified source')
        attachment_sha = revision['derivation']['previous_model_sha256']
    matching = [v for v in review['variants'] if v['candidate_sha256']==attachment_sha]
    if len(matching) != 1:
        raise ValueError('Installed model has no exact attachment review')
    placement = measure(model,tuple(matching[0]['source_muzzle_in_mesh_space_m']),driving_bone=1)
    positions, _, triangles = geometry(model)
    for p in positions:
        if not all(lo-1e-6 <= v <= hi+1e-6 for lo,v,hi in zip(model.bounding_box.min,p,model.bounding_box.max)):
            raise ValueError('Native model culling bounds exclude geometry')
    save = inspect_private()
    audio = check_audio()
    if not audio['valid'] or audio['enabled']:
        raise ValueError('Expected working stock audio')
    report = {'at':datetime.now(timezone.utc).isoformat(),'installed':state,
        'steam_alias_matches_candidate':True,'actual_native_parameters':params,'equipment_text':text,
        'actual_model':{'sha256':hashlib.sha256(data).hexdigest(),'vertices':len(positions),
            'triangles':len(triangles),'textures':len(tpf.textures),'all_textures_bound':True,
            'native_animation_members_preserved':True,'model_bounds_include_vertices':True,
            'offline_attachment_checks':placement},'saved_equipment':save,'audio':audio,
        'launch_preflight':preflight('m9'),'game_launched':False,'save_written':False,
        'rendered_model_verified':False,'runtime_combat_verified':False,
        'saved_equipment_guidance':equipment_message(save),
        'rollback':'tooling-local/backups/m9-primary-slot-2026-10-04'}
    (WORKSPACE/'evidence/m9-installed-route-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':'evidence/m9-installed-route-audit.json','saved_m9':save['characters'],
                      'model':report['actual_model'],'launch_gate':report['launch_preflight'],
                      'game_launched':False},indent=2))


if __name__=='__main__':
    main()
