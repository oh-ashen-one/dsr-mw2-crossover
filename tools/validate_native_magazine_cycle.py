"""Bounded disposable-only input test driven by fresh native ammo receipts.

No game launch, state writes, save edits or hook changes. The caller supplies
the append-log offset captured before its gated m9-test launch.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.validation_session import require_active

ROOT=Path(__file__).resolve().parents[1]

class Trial:
    def __init__(self, start, output):
        self.start=start; self.output=output; self.steps=[]; self.deadline=time.monotonic()+110
        self.path=bottle_path()/'drive_c/Tools/DSR-MW2/native-gun-v1.jsonl'
    def rows(self):
        if time.monotonic()>self.deadline:raise TimeoutError('Bounded test deadline reached')
        data=self.path.read_bytes()
        if len(data)<self.start:raise ValueError('Native log was truncated')
        lines=data[self.start:].split(b'\n')[:-1]
        rows=[json.loads(line) for line in lines if line]
        if any('frame_hook_removed' in r for r in rows):raise ValueError('Native trial already expired')
        if any(r.get('fault') for r in rows):raise ValueError('Native driver fault')
        if any(r.get('elapsed_ms',0)>170000 for r in rows):raise ValueError('Native trial nearly expired')
        return rows
    def mark(self):return len(self.rows())
    def wait(self, predicate, after=0, seconds=5):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            for row in reversed(self.rows()[after:]):
                if predicate(row):return row
            time.sleep(.05)
        raise TimeoutError('Expected fresh native receipt/state not observed')
    def state(self, after=0, **values):
        return self.wait(lambda r:r.get('kind')=='magazine_control' and all(r.get(k)==v for k,v in values.items()),after)
    def input(self, kind, *args):
        require_active()
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/owned_dsr_input.py'),kind,*args],
                       cwd=ROOT,check=True,timeout=12,capture_output=True,text=True)
    def note(self, name, **fields):
        self.steps.append({'step':name,**fields});self.save(False)
        print(json.dumps(self.steps[-1]),flush=True)
    def save(self, passed, error=None):
        self.output.parent.mkdir(parents=True,exist_ok=True)
        self.output.write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),
            'start_byte':self.start,'passed':passed,'steps':self.steps,'error':error},indent=2)+'\n')
    def reload(self, loaded, total):
        at=self.mark();self.input('key','--key','r')
        self.wait(lambda r:r.get('kind')=='magazine_control' and r.get('request')==(38 if loaded else 39),at)
        result=self.state(at,loaded=min(15,total),native_total=total,reloading=False)
        self.note('tactical_reload' if loaded else 'empty_reload',state=result)
    def shot(self, loaded, total):
        at=self.mark();self.input('left-click','--x','500','--y','500')
        receipt=self.wait(lambda r:r.get('kind')=='native_post_ammo' and r.get('before')==total and
            r.get('after')==total-1 and r.get('native_return')==total-1 and r.get('identity_matches') is True,at)
        state=self.wait(lambda r:r.get('kind')=='magazine_control' and r.get('ms',0)>receipt['ms'] and
            r.get('loaded')==loaded-1 and r.get('native_total')==total-1,at)
        self.note('shot',receipt=receipt,state=state)
    def interrupted(self, loaded, total):
        at=self.mark();self.input('reload-interrupt')
        request=self.wait(lambda r:r.get('kind')=='magazine_control' and r.get('request')==(38 if loaded else 39),at)
        interrupted=self.wait(lambda r:r.get('kind')=='native_post_input' and
            any(r['actions'][i] for i in (10,15,42)),at)
        state=self.wait(lambda r:r.get('kind')=='magazine_control' and r.get('ms',0)>request['ms']+2200 and
            r.get('loaded')==loaded and r.get('native_total')==total and not r.get('reloading'),at)
        if any(r.get('kind')=='native_post_ammo' or r.get('credited') for r in self.rows()[at:]):
            raise AssertionError('Interrupted reload created credit or consumed ammo')
        self.note('interrupted_reload',request=request,native_interrupt=interrupted,state=state)
    def run(self):
        require_active();initial=self.state(loaded=0,reloading=False);total=initial['native_total']
        if total<32:raise ValueError('Not enough native ammo for bounded test')
        self.note('initial',state=initial)
        self.interrupted(0,total)
        self.reload(0,total)
        for loaded in range(15,0,-1):
            self.shot(loaded,total);total-=1
        at=self.mark();self.input('left-click','--x','500','--y','500')
        state=self.state(at,loaded=0,native_total=total,reloading=False)
        deadline=state['ms']+1000
        self.wait(lambda r:r.get('kind')=='magazine_control' and r.get('ms',0)>=deadline,at)
        if any(r.get('kind')=='native_post_ammo' or r.get('request')==37 for r in self.rows()[at:]):
            raise AssertionError('Empty trigger fired')
        self.note('empty_trigger_blocked',state=state)
        self.reload(0,total)
        self.shot(15,total);total-=1
        self.interrupted(14,total)
        self.reload(14,total)
        self.save(True);print('NATIVE_CYCLE_PASSED',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--start-byte',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.start_byte<0 or not a.output.resolve().is_relative_to(ROOT/'tooling-local'):
        raise ValueError('Expected nonnegative cursor and task-local test output')
    t=Trial(a.start_byte,a.output)
    try:t.run()
    except Exception as e:t.save(False,str(e));raise

if __name__=='__main__':main()
