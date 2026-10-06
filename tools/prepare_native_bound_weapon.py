"""Keep native weapon HKX containers while extending their full track binding.

Authentic MW2 moving-part tracks remain unchanged; native weapon tracks retain
their first pose. Outputs are local compatibility candidates, not acceptance.
"""
import copy
import hashlib
import json
from tools.havok_offline_trial import main as approved_havok
from tools.preserve_native_havok_types import preserve_types
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.havok_study import single_block_layout
from dsr_mw2.soulstruct_tools import WORKSPACE as ROOT

def main():
    _,out=approved_havok()
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX, SkeletonHKX
    from soulstruct.havok.spline_compression import SplineTransformTrack,TrackVector3,TrackQuaternion
    part=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx')
    binder=Binder.from_bytes(next(e for e in part.entries if e.path.endswith('.anibnd')).get_uncompressed_data())
    raw=next(e for e in binder.entries if e.entry_id==463000).get_uncompressed_data()
    native_skeleton=next(e for e in binder.entries if e.entry_id==1000000).get_uncompressed_data()
    folder=out/'weapon-motion';source=json.loads((folder/'report.json').read_text())
    skeleton_raw=(folder/'m9-extended-weapon-skeleton.hkx').read_bytes()
    if hashlib.sha256(skeleton_raw).hexdigest()!=source['skeleton_sha256']:raise ValueError('Skeleton changed')
    target=out/'weapon-native-bound-v1';target.mkdir(exist_ok=True)
    skeleton_raw=preserve_types(native_skeleton,skeleton_raw)
    skeleton=SkeletonHKX.from_bytes(skeleton_raw).skeleton.skeleton
    if len(skeleton.bones)!=16:raise ValueError('Expected16 weapon bones')
    skeleton_path=target/'skeleton.hkx';skeleton_path.write_bytes(skeleton_raw)
    reports=[]
    for suffix in ('fire','reload','reload_empty2'):
        name='viewmodel_beretta_'+suffix;record=next(c for c in source['clips'] if c['source']==name)
        data=(ROOT/record['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Motion changed')
        converted=AnimationHKX.from_bytes(data).animation_container;converted.load_spline_data()
        native=AnimationHKX.from_bytes(raw);container=native.animation_container;container.load_spline_data()
        animation=container.hkx_animation
        if container.hkx_binding.transformTrackToBoneIndices!=list(range(6)):raise ValueError('Native binding changed')
        mapped=dict(zip(converted.hkx_binding.transformTrackToBoneIndices,converted.spline_data.blocks[0],strict=True))
        if set(mapped)!=set(range(6,16)):raise ValueError('Unexpected MW2 weapon binding')
        tracks=[]
        for t in container.spline_data.blocks[0]:
            p=t.get_trs_transform_at_frame(0)
            tracks.append(SplineTransformTrack(TrackVector3(*tuple(p.translation)),TrackQuaternion(p.rotation),TrackVector3(*tuple(p.scale))))
        tracks.extend(copy.deepcopy(mapped[i]) for i in range(6,16))
        container.spline_data.blocks=[tracks];packed,blocks,count=container.spline_data.pack()
        animation.data=packed;animation.numberOfTransformTracks=count
        container.hkx_binding.transformTrackToBoneIndices=list(range(16))
        for key,value in single_block_layout(converted.hkx_animation.numFrames,16,60).items():setattr(animation,key,value)
        animation.duration=converted.hkx_animation.duration;animation.floatBlockOffsets=[len(packed)]
        for i in range(6,16):
            annotation=copy.deepcopy(animation.annotationTracks[0]);annotation.trackName=skeleton.bones[i].name
            annotation.annotations=[];animation.annotationTracks.append(annotation)
        encoded=preserve_types(raw,bytes(native));restored=AnimationHKX.from_bytes(encoded).animation_container
        restored.load_spline_data();error=0.
        for frame in range(animation.numFrames):
            for bone,track in mapped.items():
                a=track.get_trs_transform_at_frame(frame);b=restored.spline_data.blocks[0][bone].get_trs_transform_at_frame(frame)
                for field in ('translation','rotation','scale'):
                    error=max(error,max(abs(float(x)-float(y)) for x,y in zip(getattr(a,field),getattr(b,field))))
        if error>2e-4:raise ValueError('Weapon motion changed')
        path=target/(name+'.hkx');path.write_bytes(encoded)
        reports.append({**record,'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(encoded).hexdigest(),
            'native_container':True,'full_tracks':16,'max_component_error':error,'runtime_verified':False})
    report={**source,'skeleton_path':str(skeleton_path.relative_to(ROOT)),
        'skeleton_sha256':hashlib.sha256(skeleton_raw).hexdigest(),'clips':reports,'runtime_verified':False}
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'clips':len(reports),'tracks':16,'max_error':max(x['max_component_error'] for x in reports)}))

if __name__=='__main__':main()
