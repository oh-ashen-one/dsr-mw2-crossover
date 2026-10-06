"""Re-anchor the existing MW2 motions to a raised native arm pose.

Offline, disposable candidate only. Geometry, skin weights, weapon animation,
timing and action routing are untouched. This is an authored third-person
stance, not a recovered MW2 ADS animation or runtime visual acceptance.
"""
import copy
import hashlib
import json
import math
from dsr_mw2.animation_pose import Transform, inverse, multiply
from dsr_mw2.animation_retarget import retarget_global_rotations, OrthogonalBasis
from dsr_mw2.skin_geometry import world_transforms
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import WORKSPACE as ROOT
from tools.havok_offline_trial import main as approved_havok
from tools.preserve_native_havok_types import preserve_types
from dsr_mw2.havok_study import make_spline_study


def main():
    skeleton,out=approved_havok()
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.havok.utilities.maths import TRSTransform, Vector3, Quaternion
    native=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx')
    sk=skeleton.skeleton.skeleton
    names=[b.name for b in sk.bones];parents=[int(p) for p in sk.parentIndices]
    anchors=[];anchor_hashes=[]
    for number in (464000,463030):
        raw=next(e for e in native.entries if e.entry_id==number).get_uncompressed_data()
        a=AnimationHKX.from_bytes(raw).animation_container;a.load_spline_data()
        if a.hkx_binding.transformTrackToBoneIndices!=list(range(61)):raise ValueError('Anchor binding changed')
        pose=[t.get_trs_transform_at_frame(0) for t in a.spline_data.blocks[0]]
        if any(abs(float(s)-1)>2e-6 for p in pose for s in p.scale):raise ValueError('Scaled anchor needs separate treatment')
        anchors.append([Transform(tuple(p.rotation),tuple(p.translation)) for p in pose])
        anchor_hashes.append(hashlib.sha256(raw).hexdigest())
    if anchor_hashes[0]!='3ddb7906a607a61918943961cb5d1af691461962f95de064a1723034f04eb907':raise ValueError('Original anchor changed')
    if anchor_hashes[1]!='978cb845fc933aa0079d78568b5102eb40906ecceeb50f723a6bc80b76aef643':raise ValueError('Raised anchor changed')
    old,new=anchors;old_world=world_transforms(parents,old);new_world=world_transforms(parents,new)
    # Native frame zero raises the right gun hand forward without any mesh
    # scaling or translated limb endpoints. Retarget the already converted
    # animation's world rotation deltas onto this same full-body anchor.
    source=out/'player-continuous-v6';target=out/'player-raised-v7';target.mkdir(exist_ok=True)
    reports=[]
    identity=OrthogonalBasis(((1,0,0),(0,1,0),(0,0,1)))
    mapping={i:i for i in range(61)}
    for record in json.loads((source/'report.json').read_text())['clips']:
        raw=(ROOT/record['spline']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['spline_sha256']:raise ValueError('Source animation changed')
        hk=AnimationHKX.from_bytes(raw);c=hk.animation_container;c.load_spline_data()
        if c.hkx_binding.transformTrackToBoneIndices!=list(range(61)):raise ValueError('Full native binding required')
        frames=[];max_delta_error=0.
        for frame in range(c.hkx_animation.numFrames):
            native_pose=[t.get_trs_transform_at_frame(frame) for t in c.spline_data.blocks[0]]
            posed=[Transform(tuple(t.rotation),tuple(t.translation)) for t in native_pose]
            world=world_transforms(parents,posed)
            result=retarget_global_rotations(old_world,world,new,parents,mapping,identity)
            result_world=world_transforms(parents,result)
            for i in range(61):
                before=multiply(world[i].rotation,inverse(old_world[i].rotation))
                after=multiply(result_world[i].rotation,inverse(new_world[i].rotation))
                max_delta_error=max(max_delta_error,1-abs(sum(a*b for a,b in zip(before,after))))
                if result[i].translation!=new[i].translation:raise ValueError('Limb translation changed')
            frames.append([TRSTransform(Vector3(p.translation),Quaternion(p.rotation),Vector3((1,1,1))) for p in result])
        if max_delta_error>1e-8:raise ValueError('Animation world rotation deltas changed')
        packed=make_spline_study(frames,list(range(61)),names,60,translating=True).animation_container
        packed.load_spline_data()
        # Use the writer's first encoded payload. Decoding near-identity
        # splines and repacking them can leave a zero-flag spline header in
        # the pinned codec; no second quantization pass is necessary here.
        data=copy.deepcopy(packed.hkx_animation.data)
        if packed.hkx_animation.numberOfTransformTracks!=61 or packed.hkx_animation.numBlocks!=1:
            raise ValueError('Full single-block container required')
        c.hkx_animation.data=data;c.hkx_animation.floatBlockOffsets=[len(data)]
        encoded=preserve_types(raw,bytes(hk));check=AnimationHKX.from_bytes(encoded).animation_container;check.load_spline_data()
        error=0.;angular_error=0.;position_error=0.
        for frame,expected in enumerate(frames):
            for i,p in enumerate(expected):
                actual=check.spline_data.blocks[0][i].get_trs_transform_at_frame(frame)
                for field in ('translation','rotation','scale'):
                    left,right=getattr(p,field),getattr(actual,field)
                    delta=max(abs(float(a)-float(b)) for a,b in zip(left,right))
                    if field=='rotation':delta=min(delta,max(abs(float(a)+float(b)) for a,b in zip(left,right)))
                    error=max(error,delta)
                    if field=='translation':position_error=max(position_error,delta)
                dot=abs(sum(float(a)*float(b) for a,b in zip(p.rotation,actual.rotation)))
                angular_error=max(angular_error,math.degrees(2*math.acos(min(1.,dot))))
        # Re-anchoring changes quaternion components, so qualify the 40-bit
        # output by angular/positional error, not the earlier pose's observed
        # component maximum. Less than0.1 degree and2micrometers are required.
        if angular_error>.1 or position_error>2e-6 or check.hkx_animation.duration!=c.hkx_animation.duration:
            raise ValueError('Round trip changed motion/timing: '+str((record['source_clip'],error,check.hkx_animation.duration,c.hkx_animation.duration)))
        path=target/(record['source_clip']+'.hkx');path.write_bytes(encoded)
        reports.append({**record,'spline':str(path.relative_to(ROOT)),'spline_sha256':hashlib.sha256(encoded).hexdigest(),
            'source_spline_sha256':record['spline_sha256'],'max_component_roundtrip_error':error,
            'max_rotation_roundtrip_error_degrees':angular_error,'max_translation_roundtrip_error_m':position_error,
            'max_world_rotation_delta_error':max_delta_error,'native_unmapped_bones':'raised a46_3030 frame0 anchor',
            'runtime_verified':False})
    report={'clips':reports,'anchor_ids':[464000,463030],'anchor_sha256':anchor_hashes,
        'hand_before_m':old_world[names.index('R_Hand')].translation,'hand_after_m':new_world[names.index('R_Hand')].translation,
        'weapon_before_m':old_world[names.index('R_Weapon')].translation,'weapon_after_m':new_world[names.index('R_Weapon')].translation,
        'scope':'Offline authored stance preserving existing MW2 rotation deltas and durations; native visuals unverified',
        'geometry_weights_and_weapon_clips_unchanged':True,'runtime_verified':False}
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='clips'},indent=2))


if __name__=='__main__':main()
