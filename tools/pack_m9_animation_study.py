"""Encode/check a staged player clip in native spline storage, offline only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from dsr_mw2.animation_pose import slerp, unit
from dsr_mw2.havok_study import make_spline_study, single_block_layout
from tools.havok_offline_trial import main as skeleton_trial

ROOT=Path(__file__).resolve().parents[1]


def main(report_name):
    if Path(report_name).name != report_name or not report_name.endswith('-report.json'):
        raise ValueError('Expected a candidate report filename')
    _, output=skeleton_trial()
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    report=json.loads((output/report_name).read_text())
    source=(ROOT/report['output']).resolve()
    if not source.is_relative_to(output.resolve()):raise ValueError('Candidate outside private output')
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report['output_sha256']:raise ValueError('Candidate hash changed')
    original=AnimationHKX.from_bytes(raw).animation_container
    if not original.is_interleaved:raise ValueError('Expected checked interleaved candidate')
    frames=original.interleaved_data
    indices=list(original.hkx_binding.transformTrackToBoneIndices)
    names=[t.trackName for t in original.hkx_animation.annotationTracks]
    hkx=make_spline_study(frames,indices,names,report['frame_rate'])
    hkx.animation_container.hkx_animation.annotationTracks=original.hkx_animation.annotationTracks
    encoded=bytes(hkx)
    restored=AnimationHKX.from_bytes(encoded).animation_container
    restored.load_spline_data()
    a=restored.hkx_animation
    layout=single_block_layout(len(frames),len(indices),report['frame_rate'])
    for field,expected in layout.items():
        actual=getattr(a,field)
        if isinstance(expected,float):
            if abs(actual-expected)>1e-6:raise ValueError('Spline timing changed: '+field)
        elif actual!=expected:raise ValueError('Spline structure changed: '+field)
    if list(restored.hkx_binding.transformTrackToBoneIndices)!=indices:raise ValueError('Binding changed')
    if a.floatBlockOffsets!=[len(a.data)] or len(a.data)%16:raise ValueError('Invalid spline payload layout')
    if encoded[4:8]!=b'TAG0' or b'20150100' not in encoded[:32]:raise ValueError('Wrong native tagfile version')
    # Every integer and halfway sample, not just frame count/file round trips.
    rotation_error=vector_error=0.0
    for half in range(2*len(frames)-1):
        frame=half/2;lo=half//2;hi=min(lo+1,len(frames)-1)
        for index,track in enumerate(restored.spline_data.blocks[0]):
            t=track.get_trs_transform_at_frame(frame)
            expected=slerp(tuple(frames[lo][index].rotation),tuple(frames[hi][index].rotation),frame-lo)
            dot=min(1.0,abs(sum(x*y for x,y in zip(expected,unit(tuple(t.rotation))))))
            rotation_error=max(rotation_error,2*math.acos(dot))
            for field in ('translation','scale'):
                vector_error=max(vector_error,max(abs(float(x)-float(y)) for x,y in zip(getattr(t,field),getattr(frames[lo][index],field))))
    if rotation_error>.002 or vector_error>2e-6:raise ValueError('Spline pose error exceeded study bound')
    cues=[[(float(c.time),c.text) for c in t.annotations] for t in a.annotationTracks]
    expected_cues=[[(float(c.time),c.text) for c in t.annotations] for t in original.hkx_animation.annotationTracks]
    if cues!=expected_cues:raise ValueError('Source cue annotations changed')
    path=source.with_name(source.stem+'-spline.hkx')
    if path.is_symlink():raise ValueError('Candidate cannot be a symlink')
    path.write_bytes(encoded)
    result={'at':datetime.now(timezone.utc).isoformat(),'source_clip':report['source_clip'],
        'input_sha256':report['output_sha256'],'output':str(path.relative_to(ROOT)),
        'sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded),'interleaved_bytes':len(raw),
        'frames':len(frames),'tracks':len(indices),'samples_checked':2*len(frames)-1,
        'maximum_rotation_error_degrees':math.degrees(rotation_error),'maximum_vector_component_error':vector_error,
        'codec':'single-block degree-1 spline, ThreeComp40 rotations; all sampled control points retained',
        'timing_metadata':layout,'cues_preserved_as_metadata':True,'roundtrip_passed':True,
        'helper_executable_run':False,'game_launched':False,'installed':False,'runtime_verified':False,
        'ready_for_installation':False,'limits':['Does not repair pose/contact authoring or integrate native actions',
        'Native acceptance remains unverified; metadata annotations do not trigger sound/ammo events']}
    (output/(source.stem+'-spline-report.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_name')
    main(parser.parse_args().report_name)
