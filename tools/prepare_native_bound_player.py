"""Place the prepared MW2 tracks inside a complete native player animation.

Preserves the native61-track identity binding/container/annotations. Unmapped
bones hold the native first-frame pose;26 mapped tracks retain the authored MW2
motion. No installer or native execution; compatibility remains unverified.
"""
import copy
import hashlib
import json
from tools.havok_offline_trial import main as approved_havok
from tools.preserve_native_havok_types import preserve_types
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.havok_study import single_block_layout,make_spline_study
from dsr_mw2.animation_pose import multiply,inverse
from dsr_mw2.soulstruct_tools import WORKSPACE as ROOT

def main(aligned=False,continuous=False):
    skeleton,out=approved_havok()
    aligned=aligned or continuous
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.havok.spline_compression import SplineTransformTrack,TrackVector3,TrackQuaternion
    from soulstruct.havok.utilities.maths import Quaternion
    binder=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx')
    source=json.loads((out/'player-reference-v2/report.json').read_text())['clips']
    target=out/('player-continuous-v6' if continuous else 'player-native-aligned-v5' if aligned else 'player-native-bound-v4');target.mkdir(exist_ok=True)
    # The converted arm tracks were authored against a46_4000 frame0. Mixing
    # those with a46_3000's torso rotates the muzzle roughly26 degrees sideways.
    # Preserve that one full-body anchor for all unmapped tracks.
    anchor_raw=next(e for e in binder.entries if e.entry_id==464000).get_uncompressed_data()
    if hashlib.sha256(anchor_raw).hexdigest()!='3ddb7906a607a61918943961cb5d1af691461962f95de064a1723034f04eb907':
        raise ValueError('Retarget anchor changed')
    anchor=AnimationHKX.from_bytes(anchor_raw).animation_container;anchor.load_spline_data()
    if anchor.hkx_binding.transformTrackToBoneIndices!=list(range(61)):
        raise ValueError('Expected full native anchor binding')
    anchor_poses=[t.get_trs_transform_at_frame(0) for t in anchor.spline_data.blocks[0]]
    reports=[]
    for number,clip in ((463000,'fire'),(465502,'reload'),(465501,'reload_empty2')):
        raw=next(e for e in binder.entries if e.entry_id==number).get_uncompressed_data()
        native=AnimationHKX.from_bytes(raw);container=native.animation_container
        container.load_spline_data();animation=container.hkx_animation
        if container.hkx_binding.transformTrackToBoneIndices!=list(range(61)) or animation.numberOfTransformTracks!=61:
            raise ValueError('Expected complete identity native player binding')
        record=next(r for r in source if r['source_clip']=='viewmodel_beretta_'+clip)
        converted=(ROOT/record['spline']).read_bytes()
        if hashlib.sha256(converted).hexdigest()!=record['spline_sha256']:raise ValueError('Prepared motion changed')
        mw2=AnimationHKX.from_bytes(converted).animation_container;mw2.load_spline_data()
        if len(container.spline_data.blocks)!=1 or len(mw2.spline_data.blocks)!=1:raise ValueError('Expected one block')
        mapped=dict(zip(mw2.hkx_binding.transformTrackToBoneIndices,mw2.spline_data.blocks[0],strict=True))
        tracks=[]
        for i,t in enumerate(container.spline_data.blocks[0]):
            pose=anchor_poses[i] if aligned else t.get_trs_transform_at_frame(0)
            tracks.append(copy.deepcopy(mapped[i]) if i in mapped else SplineTransformTrack(
                TrackVector3(*tuple(pose.translation)),TrackQuaternion(pose.rotation),TrackVector3(*tuple(pose.scale))))
        auxiliary=[]
        if continuous:
            names=[b.name for b in skeleton.skeleton.skeleton.bones]
            parents=skeleton.skeleton.skeleton.parentIndices
            for side in ('L','R'):
                upper=names.index(side+'_UpperArm');twist=names.index(side+'UpArmTwist')
                if parents[upper]!=parents[twist] or tuple(anchor_poses[upper].translation)!=tuple(anchor_poses[twist].translation):
                    raise ValueError('Native humerus helper no longer shares shoulder origin')
                frames=[]
                relative=multiply(inverse(tuple(anchor_poses[upper].rotation)),tuple(anchor_poses[twist].rotation))
                for frame in range(mw2.hkx_animation.numFrames):
                    pose=copy.deepcopy(anchor_poses[twist])
                    pose.rotation=Quaternion(multiply(tuple(tracks[upper].get_trs_transform_at_frame(frame).rotation),relative))
                    frames.append([pose])
                helper=make_spline_study(frames,[twist],[names[twist]],60).animation_container
                helper.load_spline_data()
                tracks[twist]=helper.spline_data.blocks[0][0]
                auxiliary.append(twist)
        container.spline_data.blocks=[tracks]
        data,blocks,count=container.spline_data.pack()
        animation.data=data;animation.numberOfTransformTracks=count
        for key,value in single_block_layout(mw2.hkx_animation.numFrames,61,60).items():setattr(animation,key,value)
        animation.duration=mw2.hkx_animation.duration;animation.floatBlockOffsets=[len(data)]
        animation.extractedMotion.duration=animation.duration
        animation.extractedMotion.referenceFrameSamples=np.zeros((animation.numFrames,4),dtype=np.float32)
        encoded=preserve_types(raw,bytes(native));check=AnimationHKX.from_bytes(encoded).animation_container
        check.load_spline_data()
        error=0.
        for frame in range(animation.numFrames):
            for bone,track in mapped.items():
                a=track.get_trs_transform_at_frame(frame);b=check.spline_data.blocks[0][bone].get_trs_transform_at_frame(frame)
                for field in ('translation','rotation','scale'):
                    error=max(error,max(abs(float(x)-float(y)) for x,y in zip(getattr(a,field),getattr(b,field))))
        if error>2e-4:raise ValueError('Mapped motion changed excessively')
        path=target/(record['source_clip']+'.hkx');path.write_bytes(encoded)
        reports.append({**record,'source_sha256':record['spline_sha256'],'spline':str(path.relative_to(ROOT)),
            'spline_sha256':hashlib.sha256(encoded).hexdigest(),'native_binding_tracks':61,'mw2_tracks':len(mapped),
            'native_unmapped_bones':'hold a46_4000 retarget anchor' if aligned else 'hold native first-frame pose',
            'native_type_section_exact':True,
            'moving_upperarm_skin_helpers':auxiliary,
            'max_component_roundtrip_error':error,'runtime_verified':False})
    if continuous:
        # Dedicated loop uses an existing unused two-hand reload slot in this
        # disposable category. Its TAE is emptied separately: no ammo/sound cue.
        raw=next(e for e in binder.entries if e.entry_id==465500).get_uncompressed_data()
        ready=AnimationHKX.from_bytes(raw);c=ready.animation_container;c.load_spline_data()
        if c.hkx_binding.transformTrackToBoneIndices!=list(range(61)):raise ValueError('Ready container binding changed')
        c.spline_data.blocks=[[SplineTransformTrack(TrackVector3(*tuple(p.translation)),TrackQuaternion(p.rotation),TrackVector3(*tuple(p.scale))) for p in anchor_poses]]
        data,blocks,count=c.spline_data.pack();a=c.hkx_animation;a.data=data
        for key,value in single_block_layout(61,61,60).items():setattr(a,key,value)
        a.duration=1.;a.floatBlockOffsets=[len(data)];a.extractedMotion.duration=1.
        a.extractedMotion.referenceFrameSamples=np.zeros((61,4),dtype=np.float32)
        encoded=preserve_types(raw,bytes(ready));check=AnimationHKX.from_bytes(encoded).animation_container;check.load_spline_data()
        if len(check.spline_data.blocks[0])!=61:raise ValueError('Ready pose lost tracks')
        path=target/'m9-ready-hold.hkx';path.write_bytes(encoded)
        reports.append({'source_clip':'m9_ready_hold','spline':str(path.relative_to(ROOT)),'spline_sha256':hashlib.sha256(encoded).hexdigest(),
            'duration_seconds':1.,'native_anchor_sha256':hashlib.sha256(anchor_raw).hexdigest(),'native_binding_tracks':61,'mw2_tracks':0,
            'note':'Native a46_4000 anchor pose for raising the authentic M9; not recovered MW2 ADS animation','runtime_verified':False})
    (target/'report.json').write_text(json.dumps({'clips':reports,'hypothesis_only':True},indent=2)+'\n')
    print(json.dumps([{'clip':r['source_clip'],'tracks':61,'mapped':r['mw2_tracks'],'error':r.get('max_component_roundtrip_error')} for r in reports]))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aligned',action='store_true')
    parser.add_argument('--continuous',action='store_true')
    args=parser.parse_args();main(args.aligned,args.continuous)
