"""Place the native firing dummy on the authentic weighted M9 muzzle.

Preserves geometry, materials, weights and bone transforms. Only the native
dummy2 attachment changes from the long crossbow origin to MW2 tag_flash.
No game execution; actual projectile origin still requires native validation.
"""
import hashlib
import json
from pathlib import Path
from dsr_mw2.soulstruct_tools import configure
from dsr_mw2.animation_pose import rotate
from dsr_mw2.skin_geometry import undo, point
from tools.review_m9_attachment import read_model, native_rig

ROOT=Path(__file__).resolve().parents[1]

def main():
    configure()
    from soulstruct.utilities.maths import Vector3
    folder=ROOT/'converted/mw2-2009/m9/havok/weapon-motion'
    proof=json.loads((folder/'weighted-body-report.json').read_text())
    raw=(folder/'m9-weighted-body-study.flver').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=proof['flver_sha256']:raise ValueError('Weighted model changed')
    model=read_model(raw);_,_,binds=native_rig(model)
    index=next(i for i,b in enumerate(model.bones) if b.name=='tag_flash')
    if len(model.dummies)!=1 or model.dummies[0].reference_id!=2:
        raise ValueError('Native firing attachment changed')
    dummy=model.dummies[0]
    before={'parent':dummy.parent_bone_index,'attach':dummy.attach_bone_index,'translation':list(dummy.translate)}
    dummy.parent_bone_index=index;dummy.attach_bone_index=index;dummy.follows_attach_bone=True
    dummy.translate=Vector3((0,0,0))
    dummy.forward=Vector3(rotate(undo(binds[index]).rotation,(-1,0,0)))
    dummy.upward=Vector3(rotate(undo(binds[index]).rotation,(0,-1,0)))
    encoded=bytes(model);restored=read_model(encoded)
    check=restored.dummies[0]
    for name in ('reference_id','parent_bone_index','attach_bone_index','follows_attach_bone','use_upward_vector'):
        if getattr(check,name)!=getattr(dummy,name):raise ValueError('Dummy identity changed')
    for name in ('translate','forward','upward'):
        if max(abs(a-b) for a,b in zip(getattr(check,name),getattr(dummy,name)))>1e-6:
            raise ValueError('Dummy vector roundtrip changed')
    # Reverting the attachment must recover the exact original FLVER bytes.
    original=read_model(raw);restored.dummies=original.dummies
    if bytes(restored)!=raw:raise ValueError('Unrelated FLVER data changed')
    target=folder/'m9-weighted-muzzle-v2.flver';target.write_bytes(encoded)
    report={**proof,'flver_path':str(target.relative_to(ROOT)),
        'flver_sha256':hashlib.sha256(encoded).hexdigest(),'source_flver_sha256':proof['flver_sha256'],
        'muzzle_dummy_before':before,'muzzle_dummy_bone':'tag_flash','muzzle_dummy_index':index,
        'muzzle_bind_position_m':list(point(binds[index],(0,0,0))),
        'only_dummy_changed':True,'runtime_verified':False}
    (folder/'weighted-muzzle-v2-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('flver_sha256','muzzle_bind_position_m','only_dummy_changed')}))

if __name__=='__main__':main()
