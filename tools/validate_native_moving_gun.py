"""Disposable native moving-aim regression; one genuine shot, no game-state writes."""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from tools.validate_native_magazine_cycle import Trial


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--marker',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--moving-reload',action='store_true')
    p.add_argument('--moving-empty-reload',action='store_true')
    p.add_argument('--strafe-key',choices=('a','d'),default='a')
    a=p.parse_args()
    for path in (a.marker,a.output):
        if not path.resolve().is_relative_to(Path('tooling-local').resolve()):
            raise ValueError('Expected task-local evidence')
    marker=json.loads(a.marker.read_text());t=Trial(marker['start_byte'],a.output)
    def scenario(name,kind,*args):
        at=t.mark();started=datetime.now(timezone.utc).isoformat()
        before=t.wait(lambda r:r.get('kind')=='position_observation',at)
        t.input(kind,*args)
        last=t.wait(lambda r:r.get('kind')=='position_observation',len(t.rows()))
        after=t.wait(lambda r:r.get('kind')=='position_observation' and r['ms']>=last['ms']+600,len(t.rows()))
        rows=t.rows()[at:];positions=[r for r in rows if r.get('kind')=='position_observation']
        held=[r for r in positions if r['aim_owned']]
        inputs=[r for r in rows if r.get('kind')=='native_post_input']
        pose=[r for r in inputs if any(v[0]==465500 for v in r['animations'])]
        firing=[r for r in inputs if any(v[0]==463000 for v in r['animations'])]
        firing_walk=[r for r in firing if r['animations'][3][0]==300 and r['animations'][21][0]==300]
        reloading=[r for r in inputs if any(v[0] in (465501,465502) for v in r['animations'])]
        reload_walk=[r for r in reloading if r['animations'][3][0] in (300,301,302,303,550,551) and r['animations'][21][0] in (300,301,302,303,550,551)]
        reload_positions=[r for r in positions if r['animation'] in (465501,465502)]
        receipts=[r for r in rows if r.get('kind')=='native_post_ammo']
        t.note(name,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
            before=before,after=after,displacement_m=math.dist(before['xyz'],after['xyz']),
            positions=positions,owned_aim_samples=len(held),
            held_position_span_m=max((math.dist(x['xyz'],y['xyz']) for x in held for y in held),default=0),
            animation_slot_signatures=[list(v) for v in sorted({tuple(v[0] for v in r['animations']) for r in inputs})],
            pose_samples=len(pose),pose_span_ms=pose[-1]['ms']-pose[0]['ms'] if pose else 0,receipts=receipts,
            firing_samples=len(firing),firing_with_walk_samples=len(firing_walk),
            reload_samples=len(reloading),reload_with_walk_samples=len(reload_walk),
            reload_position_samples=len(reload_positions),reload_aim_owned_samples=sum(r['aim_owned'] for r in reload_positions),
            native_turn690_samples=sum(any(v[0]==690 for v in r['animations']) for r in inputs),
            pose_after_shot=bool(receipts) and any(r['ms']>receipts[-1]['ms']+300 for r in pose),
            requests=[r for r in rows if r.get('kind')=='magazine_control' and r['request'] in (37,38,39)],
            last_state=next((r for r in reversed(rows) if r.get('kind')=='magazine_control'),None),
            aim_released=not after['aim_owned'])
    try:
        initial=t.state(loaded=0,reloading=False);total=initial['native_total']
        if total<2:raise ValueError('Insufficient native ammo for one-shot control')
        t.note('initial',state=initial)
        if a.moving_empty_reload:
            scenario('empty_reload_reentry_release','aim-move-reload','--keep-pointer')
        else:t.reload(0,total)
        scenario('aim_strafe_release','aim-move','--keep-pointer','--key',a.strafe_key)
        scenario('moving_shot_reentry_release','aim-move-fire','--keep-pointer')
        if not a.moving_empty_reload:
            scenario('reload_reentry_release','aim-move-reload' if a.moving_reload else 'aim-reload','--keep-pointer')
        scenario('fresh_hold_release','right-click','--keep-pointer','--seconds','3')
        scenario('ordinary_forward_after','key','--key','w','--seconds','.4')
        d={r['step']:r for r in t.steps};shot=d['moving_shot_reentry_release'];reload=d['empty_reload_reentry_release' if a.moving_empty_reload else 'reload_reentry_release']
        reload_total=total if a.moving_empty_reload else total-1
        receipts=shot['receipts']
        passed=(d['aim_strafe_release']['held_position_span_m']>.2 and shot['held_position_span_m']>.2
            and len(receipts)==1 and receipts[0]['before']==total and receipts[0]['after']==total-1
            and receipts[0]['native_return']==total-1 and receipts[0]['identity_matches'] is True
            and shot['last_state']['loaded']==min(15,total)-1 and shot['pose_after_shot']
            and shot['firing_samples']>=2 and shot['firing_with_walk_samples']==shot['firing_samples']
            and any(r['request']==(39 if a.moving_empty_reload else 38) for r in reload['requests'])
            and reload['last_state']['loaded']==min(15,reload_total) and reload['last_state']['native_total']==reload_total
            and d['fresh_hold_release']['pose_span_ms']>=1000 and d['ordinary_forward_after']['displacement_m']>.2
            and all(r['aim_released'] for r in t.steps if 'aim_released' in r))
        if a.moving_reload or a.moving_empty_reload:
            passed=(passed and reload['displacement_m']>.5 and reload['reload_samples']>20
                and reload['reload_with_walk_samples']==reload['reload_samples']
                and reload['reload_position_samples']>=3 and reload['reload_aim_owned_samples']==reload['reload_position_samples']
                and reload['native_turn690_samples']==0)
        t.save(passed,None if passed else 'A moving-aim lifecycle requirement failed; inspect each phase')
        print('MOVING_GUN_PASS' if passed else 'MOVING_GUN_FAILED')
    except Exception as e:
        t.save(False,str(e));raise


if __name__=='__main__':main()
