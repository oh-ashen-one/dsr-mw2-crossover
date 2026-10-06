"""Add native-format stationary reference motion to the three player studies.

Original source, pinned local inputs only. The native player clips carry a
reference-frame object; our first generated player clips omitted it. This is a
compatibility hypothesis until native validation; weapon clips are unchanged.
"""
import copy
import hashlib
import json
from pathlib import Path
from tools.havok_offline_trial import main as approved_havok
from dsr_mw2.runtime_paths import bottle_path

ROOT=Path(__file__).resolve().parents[1]

def main():
    _,out=approved_havok()
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    native=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx')
    studies=json.loads((out/'m9-handling-studies.json').read_text())['clips']
    target=out/'player-reference-v2';target.mkdir(exist_ok=True)
    reports=[]
    for number,clip in ((463000,'fire'),(465502,'reload'),(465501,'reload_empty2')):
        entry=next(e for e in native.entries if e.entry_id==number)
        stock=AnimationHKX.from_bytes(entry.get_uncompressed_data())
        record=next(r for r in studies if r['source_clip']=='viewmodel_beretta_'+clip)
        raw=(ROOT/record['spline']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['spline_sha256']:
            raise ValueError('Prepared animation changed')
        study=AnimationHKX.from_bytes(raw);animation=study.animation_container.hkx_animation
        if animation.extractedMotion is not None:
            raise ValueError('Input already has reference motion')
        reference=copy.deepcopy(stock.animation_container.hkx_animation.extractedMotion)
        if reference is None:raise ValueError('Native player reference motion missing')
        reference.duration=animation.duration
        reference.referenceFrameSamples=np.zeros((animation.numFrames,4),dtype=np.float32)
        animation.extractedMotion=reference
        study.hsh_overrides.update(stock.hsh_overrides)
        data=bytes(study);restored=AnimationHKX.from_bytes(data).animation_container
        if restored.hkx_animation.data!=animation.data or np.any(restored.hkx_animation.extractedMotion.referenceFrameSamples):
            raise ValueError('Spline or stationary reference motion changed')
        path=target/(record['source_clip']+'.hkx');path.write_bytes(data)
        reports.append({'source_clip':record['source_clip'],'source_sha256':record['spline_sha256'],
            'spline':str(path.relative_to(ROOT)),'spline_sha256':hashlib.sha256(data).hexdigest(),
            'duration_seconds':record['duration_seconds'],'spline_payload_unchanged':True,
            'reference_motion':'stationary native-format object','runtime_verified':False})
    (target/'report.json').write_text(json.dumps({'clips':reports,'hypothesis_only':True},indent=2)+'\n')
    print(json.dumps({'prepared_clips':len(reports),'runtime_verified':False}))

if __name__=='__main__':main()
