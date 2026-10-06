"""Provide a full native-container weapon clip for the new player hold route."""
import hashlib
import json
from tools.havok_offline_trial import main as approved_havok
from tools.preserve_native_havok_types import preserve_types
from dsr_mw2.havok_study import single_block_layout


def main():
    _,out=approved_havok()
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.havok.spline_compression import SplineTransformTrack,TrackVector3,TrackQuaternion
    source=out/'weapon-native-bound-v1'
    report=json.loads((source/'report.json').read_text())
    proof=next(c for c in report['clips'] if c['source']=='viewmodel_beretta_fire')
    raw=(source/'viewmodel_beretta_fire.hkx').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=proof['sha256']:raise ValueError('Native weapon fire container changed')
    ready=AnimationHKX.from_bytes(raw);c=ready.animation_container;c.load_spline_data()
    if c.hkx_binding.transformTrackToBoneIndices!=list(range(16)):raise ValueError('Expected full16-track weapon binding')
    poses=[t.get_trs_transform_at_frame(0) for t in c.spline_data.blocks[0]]
    c.spline_data.blocks=[[SplineTransformTrack(TrackVector3(*tuple(p.translation)),TrackQuaternion(p.rotation),TrackVector3(*tuple(p.scale))) for p in poses]]
    data,_,_=c.spline_data.pack();a=c.hkx_animation;a.data=data
    for key,value in single_block_layout(61,16,60).items():setattr(a,key,value)
    a.duration=1.;a.floatBlockOffsets=[len(data)]
    encoded=preserve_types(raw,bytes(ready));check=AnimationHKX.from_bytes(encoded).animation_container;check.load_spline_data()
    error=0.
    for frame in (0,30,60):
        for p,t in zip(poses,check.spline_data.blocks[0],strict=True):
            q=t.get_trs_transform_at_frame(frame)
            for field in ('translation','rotation','scale'):
                error=max(error,max(abs(float(x)-float(y)) for x,y in zip(getattr(p,field),getattr(q,field))))
    if error>2e-4:raise ValueError('Static weapon pose roundtrip changed')
    target=out/'weapon-ready-v2';target.mkdir(exist_ok=True)
    path=target/'m9-ready-hold.hkx';path.write_bytes(encoded)
    (target/'report.json').write_text(json.dumps({'source':proof,'path':str(path.relative_to(out.parents[3])),
        'sha256':hashlib.sha256(encoded).hexdigest(),'full_tracks':16,'duration_seconds':1.,
        'max_component_roundtrip_error':error,'runtime_verified':False},indent=2)+'\n')
    print(json.dumps({'sha256':hashlib.sha256(encoded).hexdigest(),'error':error}))


if __name__=='__main__':main()
