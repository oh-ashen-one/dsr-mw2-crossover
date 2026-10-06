"""Bounded disposable native aim lifecycle test; reads receipts, never edits state."""
import json
import argparse
import math
from pathlib import Path
from datetime import datetime, timezone
from tools.validate_native_magazine_cycle import Trial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--marker',type=Path,default=Path('tooling-local/native-input/precision-start.json'))
    parser.add_argument('--output',type=Path,default=Path('tooling-local/native-input/precision-lifecycle.json'))
    args=parser.parse_args()
    for p in (args.marker,args.output):
        if not p.resolve().is_relative_to(Path('tooling-local').resolve()):raise ValueError('Expected task-local trial paths')
    marker=json.loads(args.marker.read_text())
    t=Trial(marker['start_byte'],args.output)
    def scenario(name,kind,*args):
        at=t.mark();started=datetime.now(timezone.utc).isoformat()
        t.input(kind,*args)
        t.wait(lambda r:r.get('kind')=='magazine_control',len(t.rows()),seconds=3)
        rows=t.rows()[at:]
        pose=[r for r in rows if r.get('kind')=='native_post_input' and r['animations'][7][0]==465500]
        runs=[]
        for r in pose:
            if not runs or r['ms']-runs[-1][-1]>50:runs.append([])
            runs[-1].append(r['ms'])
        t.note(name,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
               hold_frames=len(pose),longest_hold_ms=max((r[-1]-r[0] for r in runs),default=0),
               aim_transitions=[r for r in rows if r.get('kind')=='native_aim_trial' and r['before']!=r['after']],
               receipts=[r for r in rows if r.get('kind')=='native_post_ammo'],
               requests=[r for r in rows if r.get('kind')=='magazine_control' and r['request'] in (37,38,39)],
               positions=[r for r in rows if r.get('kind')=='position_observation'],
               position_span_m=max((math.dist(a['xyz'],b['xyz']) for a in rows for b in rows
                    if a.get('kind')==b.get('kind')=='position_observation' and a['aim_owned'] and b['aim_owned']),default=0),
               pose_after_last_shot=any(r['ms']>max((a['ms'] for a in rows if a.get('kind')=='native_post_ammo'),default=10**20)+300 for r in pose),
               last_state=next((r for r in reversed(rows) if r.get('kind')=='magazine_control'),None))
    try:
        initial=t.state(loaded=0,reloading=False);total=initial['native_total']
        t.note('initial',state=initial);t.reload(0,total)
        scenario('hold_release','right-click','--keep-pointer','--seconds','3')
        scenario('movement_release','aim-move','--keep-pointer')
        scenario('five_shots_reentry_release','aim-five-shots','--keep-pointer')
        scenario('reload_interrupt_release','aim-reload-interrupt','--keep-pointer')
        scenario('reload_reentry_release','aim-reload','--keep-pointer')
        scenario('fresh_hold_release','right-click','--keep-pointer','--seconds','3')
        by_name={s['step']:s for s in t.steps}
        passed=(all(by_name[n]['longest_hold_ms']>=1000 for n in ('hold_release','fresh_hold_release'))
                and by_name['five_shots_reentry_release']['pose_after_last_shot']
                and len(by_name['five_shots_reentry_release']['receipts'])==5
                and any(r['request']==38 for r in by_name['reload_interrupt_release']['requests'])
                and by_name['reload_interrupt_release']['last_state']['loaded']==10
                and any(r['request']==38 for r in by_name['reload_reentry_release']['requests'])
                and by_name['reload_reentry_release']['last_state']['loaded']==15)
        t.save(passed,None if passed else 'A lifecycle requirement failed; inspect per-phase native receipts')
        print('POSE_LIFECYCLE_PASS' if passed else 'POSE_LIFECYCLE_FAILED',flush=True)
    except Exception as e:
        t.save(False,str(e));raise


if __name__=='__main__':main()
