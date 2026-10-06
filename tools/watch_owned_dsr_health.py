"""Bounded desktop-health guard; can stop only this task's native DSR process."""
import ctypes
import json
import os
import signal
import subprocess
import time
from dsr_mw2.launch import WORKSPACE,GPU,OWNER_RESERVATION,gpu_percent,game_processes


def main():
    root=WORKSPACE/'tooling-local/launch'
    cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cg.CGPreflightScreenCaptureAccess.restype=ctypes.c_bool
    if not cg.CGPreflightScreenCaptureAccess():raise RuntimeError('Desktop probe permission absent')
    start=time.monotonic();failures=0;seen=False
    with (root/'owned-health.jsonl').open('a') as log:
        while time.monotonic()-start<1200:
            games=game_processes();seen=seen or bool(games)
            value=gpu_percent();probe=None
            if games or (value is not None and value>=98):
                try:
                    r=subprocess.run(['/usr/sbin/screencapture','-x','-t','png','-R0,0,8,8',str(root/'owned-health-probe.png')],
                                     capture_output=True,timeout=6)
                    probe=r.returncode==0
                except subprocess.TimeoutExpired:probe=False
            failures=failures+1 if probe is False else 0
            record={'at':time.time(),'owned_native_pids':games,'gpu_percent':value,'desktop_probe_passed':probe}
            log.write(json.dumps(record)+'\n');log.flush()
            if failures>=2:
                pause=GPU/'PAUSED'
                if pause.read_text()==OWNER_RESERVATION:
                    pause.write_text('DSR-MW2 health pause: desktop probe failed twice; preserve native runtime for investigation.\n')
                verified=game_processes()
                for pid in games:
                    if pid in verified:os.kill(pid,signal.SIGTERM)
                print(json.dumps({'desktop_fault':True,'sigterm_task_pids':[p for p in games if p in verified],'forced_kill':False}),flush=True)
                return 75
            if seen and not games:return 0
            time.sleep(5)
    return 0


if __name__=='__main__':raise SystemExit(main())
