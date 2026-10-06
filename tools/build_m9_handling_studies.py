"""Sequential approved offline conversions; never launches a game or installer."""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'converted/mw2-2009/m9/havok'


def main(attachment_report="evidence/m9-attachment-review.json"):
    OUT.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ, PYTHONPATH=str(ROOT), OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    reports=[]
    # Reload last keeps the existing wireframe-review entry point focused on
    # that longer action. The zero-frame idle and one-track ADS transitions
    # are deliberately excluded from this player-rig conversion.
    for clip in ('fire','lastfire','fire_ads','reload_empty2','pullout','putaway','reload'):
        stem='m9-'+clip+'-native-grip-axial-study'
        steps=[['tools/convert_m9_reload_study.py','--clip',clip,'--finger-mode','native-grip'],
               ['tools/pack_m9_animation_study.py',stem+'-report.json'],
               ['tools/review_m9_reload_geometry.py','--attachment-report',attachment_report]]
        log=OUT/(stem+'-build.log')
        with log.open('w') as stream:
            for step in steps:
                subprocess.run([sys.executable,'-B',*step],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                               check=True,timeout=30)
        report=json.loads((OUT/(stem+'-report.json')).read_text())
        codec=json.loads((OUT/(stem+'-spline-report.json')).read_text())
        geometry=json.loads((OUT/(stem+'-geometry-report.json')).read_text())
        reports.append({'source_clip':report['source_clip'],'source_sha256':report['source_sha256'],
            'frame_count':report['frame_count'],'duration_seconds':report['duration_seconds'],
            'interleaved':report['output'],'interleaved_sha256':report['output_sha256'],
            'spline':codec['output'],'spline_sha256':codec['sha256'],
            'codec_error_degrees':codec['maximum_rotation_error_degrees'],
            'geometry_maximum_edge_stretch':geometry['worst_frame']['maximum_edge_stretch'],
            'geometry_maximum_edge_length_increase_from_native_anchor_m':geometry['maximum_edge_length_increase_from_native_anchor_m'],
            'geometry_finite':geometry['all_frames_finite'], 'source_cues':report['source_cues']})
        print(json.dumps({'clip':clip,'frames':report['frame_count'],'roundtrip_passed':True}),flush=True)
    manifest={'at':datetime.now(timezone.utc).isoformat(),'clips':reports,'frame_rate':60,'attachment_report':attachment_report,
        'finger_policy':'Native DSR grip retained; no MW2 finger articulation claim',
        'foretwist_policy':'Native elbow swing with half axial wrist roll',
        'total_frames':sum(r['frame_count'] for r in reports),'runtime_verified':False,'installed':False,
        'ready_for_installation':False,'game_launched':False,'helper_executable_run':False,
        'exclusions':['Zero-frame source idle is used only as the retarget anchor',
                      'One-track ADS up/down assets require separate weapon/camera treatment'],
        'remaining':['Gun/hand contact and weapon slide/magazine coupling',
                     'Native action, inventory, input, camera, event and locomotion integration',
                     'Independent native playback, actual saves and combat verification']}
    (OUT/'m9-handling-studies.json').write_text(json.dumps(manifest,indent=2)+'\n')
    subprocess.run([sys.executable,'-B','tools/plot_m9_reload_geometry.py'],cwd=ROOT,env=env,check=True,timeout=15)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attachment-report',default='evidence/m9-attachment-review.json')
    main(parser.parse_args().attachment_report)
