"""One-factor disposable precision/hold movement comparison; no firing or reload."""
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
    a=p.parse_args()
    for path in (a.marker,a.output):
        if not path.resolve().is_relative_to(Path('tooling-local').resolve()):
            raise ValueError('Expected task-local evidence')
    marker=json.loads(a.marker.read_text());t=Trial(marker['start_byte'],a.output)
    def scenario(name,kind,*args):
        at=t.mark();started=datetime.now(timezone.utc).isoformat()
        before=t.wait(lambda r:r.get('kind')=='position_observation',at)
        t.input(kind,*args)
        # Read after a further0.6s of native samples so walking has settled.
        last=t.wait(lambda r:r.get('kind')=='position_observation',len(t.rows()))
        after=t.wait(lambda r:r.get('kind')=='position_observation' and r['ms']>=last['ms']+600,len(t.rows()))
        rows=t.rows()[at:]
        positions=[r for r in rows if r.get('kind')=='position_observation']
        held=[r for r in positions if r['aim_owned']]
        key=[r for r in positions if r['forward_key']]
        animation_rows=[r for r in rows if r.get('kind')=='native_post_input']
        signatures={tuple(v[0] for v in r['animations']) for r in animation_rows}
        t.note(name,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
            before=before,after=after,displacement_m=math.dist(before['xyz'],after['xyz']),
            positions=positions,owned_aim_samples=len(held),held_forward_samples=sum(r['aim_owned'] for r in key),
            held_position_span_m=max((math.dist(x['xyz'],y['xyz']) for x in held for y in held),default=0),
            animation_slot_signatures=[list(s) for s in sorted(signatures)],
            action_masks=sorted({tuple(i for i,v in enumerate(r['actions']) if v) for r in animation_rows}),
            native_states=sorted({(r['active_state'],r['passive_state']) for r in rows if r.get('kind')=='native_frame_entry'}),
            aim=[r for r in rows if r.get('kind')=='native_aim_trial' and (r['held'] or r['before']!=r['after'])])
    try:
        state=t.state(loaded=0,reloading=False);t.note('initial',state=state)
        scenario('ordinary_forward_before','key','--key','w','--seconds','.4')
        scenario('precision_hold','right-click','--keep-pointer','--seconds','3')
        scenario('precision_forward','aim-move','--keep-pointer')
        scenario('ordinary_forward_after','key','--key','w','--seconds','.4')
        phases={s['step']:s for s in t.steps}
        qualified=(all(phases[n]['displacement_m']>.2 for n in ('ordinary_forward_before','ordinary_forward_after'))
                   and phases['precision_forward']['held_forward_samples']>0)
        if any(r.get('kind')=='native_post_ammo' for r in t.rows()):raise ValueError('Unexpected ammunition event')
        t.save(qualified,None if qualified else 'Movement/aim control not qualified; inspect phases')
        print('MOVEMENT_COMPARISON_QUALIFIED' if qualified else 'MOVEMENT_COMPARISON_INCONCLUSIVE')
    except Exception as e:
        t.save(False,str(e));raise


if __name__=='__main__':main()
