"""Offline authentic M9 moving-part skeleton and seven source-time HKX studies.

No FLVER installer, native action mapping, input hook or game execution. This
preserves the authored conversion hypothesis separately from the playable
rigid-world-model prototype. All optional code is pinned/audited by the trial.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from dsr_mw2.animation_pose import Transform, sample_components, slerp, unit
from dsr_mw2.animation_retarget import OrthogonalBasis
from dsr_mw2.havok_study import make_spline_study
from dsr_mw2.weapon_articulation import relative_part_pose
from dsr_mw2.xmodel_geometry import read as read_model
from dsr_mw2.xanim import read as read_animation
from tools.havok_offline_trial import main as trial

ROOT = Path(__file__).resolve().parents[1]
CLIPS = ('fire', 'lastfire', 'fire_ads', 'reload', 'reload_empty2', 'pullout', 'putaway')


def pinned(path, digest):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=digest: raise ValueError('Source revision changed: '+path.name)
    return data


def main():
    _, out = trial()
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import SkeletonHKX, AnimationHKX
    from soulstruct.havok.types.hk2015 import hkaBone, hkQsTransform
    from soulstruct.havok.utilities.maths import TRSTransform, Vector3, Quaternion
    from soulstruct.dcx import DCXType

    output=out/'weapon-motion';output.mkdir(exist_ok=True)
    base=ROOT/'converted/mw2-2009/unlinked'
    model_sha='d7b64f119ea39e34d740dc34d48477fc9bb06d2e57b2e7671d0038d20177e96c'
    model=read_model(pinned(base/'m9-handling-models/model_export/viewmodel_beretta_lod0.xmodel_export',model_sha).decode())
    native_sha='e851d82ad7828ba0a3cec47885157d9964aaf3163635f370f148f35d57d6e833'
    binder=Binder.from_bytes(pinned(ROOT/'profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx',native_sha))
    nested=Binder.from_bytes(next(e for e in binder.entries if e.path.endswith('.anibnd')).get_uncompressed_data())
    skeleton=SkeletonHKX.from_bytes(next(e for e in nested.entries if e.entry_id==1000000).get_uncompressed_data())
    target=skeleton.skeleton.skeleton
    native_names=[b.name for b in target.bones]
    if native_names!=['move_poit','Model_Dmy','move_poit01','move_poit02','move_poit03','move_poit04']:
        raise ValueError('Native weapon skeleton changed')
    parents=list(target.parentIndices)
    original_poses=[t.to_trs_transform() for t in target.referencePose]
    basis=OrthogonalBasis(((-1,0,0),(0,0,1),(0,-1,0)))
    # Provisional authoring alignment measured from corresponding world/view UVs.
    # No baked vertex deformation: one uniform scale and a grip translation.
    scale=.0254/1.1
    grip=(-1.47367991,.07962251,-1.0460717)
    def converted(bone, pose):
        translation=pose.translation
        if bone.parent<0:translation=tuple(a-b for a,b in zip(translation,grip))
        return TRSTransform(translation=Vector3(tuple(v*scale for v in basis.vector(translation))),
                            rotation=Quaternion(basis.rotation(pose.rotation)),scale=Vector3((1,1,1)))
    for b in model.bones:
        target.bones.append(hkaBone(name=b.name,lockTranslation=False))
        target.parentIndices.append(1 if b.parent<0 else len(native_names)+b.parent)
        target.referencePose.append(hkQsTransform.from_trs_transform(converted(b,b.local_bind)))
    skeleton.skeleton.refresh_bones()
    skeleton.dcx_type=DCXType.Null
    raw=bytes(skeleton);check=SkeletonHKX.from_bytes(raw).skeleton.skeleton
    names=native_names+[b.name for b in model.bones]
    if [b.name for b in check.bones]!=names or check.parentIndices!=target.parentIndices:
        raise ValueError('Extended skeleton did not round trip')
    if check.parentIndices[:6]!=parents:raise ValueError('Native hierarchy changed')
    for a,b in zip(original_poses,check.referencePose[:6]):
        for field in ('translation','rotation','scale'):
            if max(abs(float(x)-float(y)) for x,y in zip(getattr(a,field),getattr(b.to_trs_transform(),field)))>1e-6:
                raise ValueError('Original native reference pose changed')
    (output/'m9-extended-weapon-skeleton.hkx').write_bytes(raw)
    indices=list(range(6,len(names)))
    moving={'j_gun','j_bolt','j_press_rear','tag_clip','tag_silencer'}
    manifest=json.loads((ROOT/'evidence/m9-animation-export-check.json').read_text())['clips']
    reports=[]
    for clip in CLIPS:
        name='viewmodel_beretta_'+clip
        proof=next(p for p in manifest if p['name']==name)
        animation=read_animation(pinned(base/'m9-handling-animation/xanim'/name,proof['sha256']))
        if (animation.fps,animation.asset_type,animation.looped)!=(30,1,False):raise ValueError('Source clip mode changed')
        frames=[]
        for i in range(animation.frames*2+1):
            local,_=relative_part_pose(model.bones,sample_components(animation,i/2),moving)
            frames.append([converted(b,p) for b,p in zip(model.bones,local)])
        hkx=make_spline_study(frames,indices,names[6:],60,translating=True,skeleton_name=target.name)
        encoded=bytes(hkx)
        restored=AnimationHKX.from_bytes(encoded).animation_container
        restored.load_spline_data()
        if list(restored.hkx_binding.transformTrackToBoneIndices)!=indices or restored.hkx_binding.originalSkeletonName!=target.name:
            raise ValueError('Weapon track binding changed')
        if abs(restored.hkx_animation.duration-animation.seconds)>1e-6:raise ValueError('Source clip duration changed')
        max_position=max_angle=0.
        for half in range(len(frames)*2-1):
            f=half/2;lo=half//2;hi=min(lo+1,len(frames)-1);alpha=f-lo
            for i,track in enumerate(restored.spline_data.blocks[0]):
                t=track.get_trs_transform_at_frame(f)
                expected=slerp(tuple(frames[lo][i].rotation),tuple(frames[hi][i].rotation),alpha)
                dot=min(1.,abs(sum(a*b for a,b in zip(expected,unit(tuple(t.rotation))))))
                max_angle=max(max_angle,2*math.acos(dot))
                for axis in range(3):
                    expected_p=frames[lo][i].translation[axis]*(1-alpha)+frames[hi][i].translation[axis]*alpha
                    max_position=max(max_position,abs(float(t.translation[axis])-expected_p))
                if max(abs(float(v)-1) for v in t.scale)>1e-6:raise ValueError('Weapon scale changed')
        if max_position>5e-6 or max_angle>.002:raise ValueError('Moving-part spline exceeds error bound')
        path=output/(name+'-weapon-spline.hkx');path.write_bytes(encoded)
        reports.append({'source':name,'source_sha256':proof['sha256'],'path':str(path.relative_to(ROOT)),
                        'sha256':hashlib.sha256(encoded).hexdigest(),'frames':len(frames),'tracks':len(indices),
                        'duration_seconds':animation.seconds,'max_translation_error_m':max_position,
                        'max_rotation_error_degrees':math.degrees(max_angle),'samples_checked':len(frames)*2-1})
    report={'at':datetime.now(timezone.utc).isoformat(),'source_model_sha256':model_sha,'native_binder_sha256':native_sha,
            'native_reference_pose_and_indices_preserved':True,'skeleton_bones':len(names),'source_vertices':len(model.positions),
            'source_triangles':len(model.faces),'source_degenerate_triangles':sum(len({c.vertex for c in f.corners})<3 for f in model.faces),
            'source_weighted_bones':sorted({model.bones[i].name for ws in model.influences for i,w in ws}),
            'moving_bones':sorted(moving),'unit_scale_m':scale,'provisional_grip_source_inches':grip,
            'skeleton_sha256':hashlib.sha256(raw).hexdigest(),'clips':reports,
            'roundtrip_passed':True,'installed':False,'ready_for_installation':False,'runtime_verified':False,
            'limits':['Moving-part relative-offset semantics and grip alignment remain authoring hypotheses requiring visual validation.',
                      'No converted weighted FLVER is paired with these studies yet.',
                      'No native action/TAE mapping, contact solver, inventory, firing, reload or camera hooks are installed.',
                      'Unweighted effect and knife bones remain bound; their source track semantics are not guessed.']}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'clips':len(reports),'frames':sum(r['frames'] for r in reports),'skeleton_bones':len(names),
                      'max_translation_error_m':max(r['max_translation_error_m'] for r in reports),
                      'roundtrip_passed':True,'installed':False}))


if __name__=='__main__':main()
