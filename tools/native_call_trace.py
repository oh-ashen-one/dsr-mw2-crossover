"""Build/stage or run our bounded debugger trace in disposable native DSR only.

Unlike the ordinary observer, this temporarily edits thread debug registers.
It never injects, patches executable bytes or writes gameplay inventory/health.
It is explicit diagnostics, never automatically run in an owner session.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dsr_mw2.install_private import atomic_write
from dsr_mw2.profile import guard,command,environment
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.validation_session import require_active
from dsr_mw2.launch import game_processes,network_wrapper
from dsr_mw2.native_interfaces import inspect

ROOT=Path(__file__).resolve().parents[1]
SOURCES=['native/src/native_call_trace.cpp','native/src/dsr_snapshot.cpp','native/include/dsr_snapshot.hpp']
OUT=ROOT/'tooling-local/native-call-trace'
RECEIPT=ROOT/'evidence/native-call-trace-build.json'
NAME='native_call_trace_v1.exe'
WIN=r'C:\Tools\DSR-MW2\native-call-trace-v1\native_call_trace_v1.exe'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def stage():
    bottle=bottle_path()
    if guard(bottle):raise ValueError('Private profile isolation failed')
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if bottle_processes(bottle):raise ValueError('Stage only with private session closed')
        inspect((bottle/'drive_c/Games/Dark Souls Remastered/DarkSoulsRemastered.exe').read_bytes())
        OUT.mkdir(exist_ok=True)
        exe=OUT/NAME
        subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++','-std=c++17','-Wall','-Wextra','-Werror',
            '-Wconversion','-O2','-static','-fno-exceptions','-fno-rtti','-I',str(ROOT/'native/include'),
            *[str(ROOT/s) for s in SOURCES[:2]],'-lbcrypt','-Wl,--no-insert-timestamp','-o',str(exe)],check=True)
        imports=subprocess.check_output(['/opt/homebrew/bin/x86_64-w64-mingw32-objdump','-p',str(exe)],text=True)
        for forbidden in ('WriteProcessMemory','CreateRemoteThread','VirtualAllocEx','VirtualProtectEx','SendInput','CreateProcessW'):
            if forbidden in imports:raise ValueError('Unexpected mutation/injection/input import: '+forbidden)
        for expected in ('DebugActiveProcess','GetThreadContext','SetThreadContext','DebugActiveProcessStop'):
            if expected not in imports:raise ValueError('Missing trace API: '+expected)
        target=bottle/'drive_c/Tools/DSR-MW2/native-call-trace-v1'/NAME
        if target.is_symlink() or not target.resolve().is_relative_to(bottle):raise ValueError('Staging redirect')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)!=sha(exe):raise ValueError('Existing differing trace executable preserved')
        atomic_write(target,exe.read_bytes())
        report={'sha256':sha(exe),'bytes':exe.stat().st_size,'sources':{s:sha(ROOT/s) for s in SOURCES},
            'max_seconds':20,'debug_register_mutation':True,'inventory_mutation':False,'executable_patches':False,
            'executed':False,'runtime_verified':False,'native_feature_installed':False}
        RECEIPT.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


def run():
    raise RuntimeError('Trace v1 is blocked: native game exited during the 2026-10-06 trial with zero callback hits; see evidence/native-call-trace-runtime.json')
    require_active()
    if len(game_processes())!=1:raise ValueError('Expected one owned game')
    report=json.loads(RECEIPT.read_text())
    for path,h in report['sources'].items():
        if sha(ROOT/path)!=h:raise ValueError('Trace source changed; explicit rebuild required')
    exe=bottle_path()/'drive_c/Tools/DSR-MW2/native-call-trace-v1'/NAME
    if sha(exe)!=report['sha256']:raise ValueError('Trace executable changed')
    env=environment();env['DSR_MW2_DISPOSABLE_TRACE']='validation-20-seconds'
    log=OUT/('trace-'+str(time.time_ns())+'.jsonl')
    print(json.dumps({'log':str(log),'maximum_active_seconds':20}),flush=True)
    with log.open('w') as out:
        # Let the debugger restore its thread state and detach itself. No generic
        # subprocess timeout kills it while it holds temporary debug registers.
        child=subprocess.Popen([*network_wrapper('m9-test'),*command(WIN)],env=env,stdout=out,stderr=out)
        code=child.wait()
    require_active()
    print(json.dumps({'exit':code,'log':str(log)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('stage','run'))
    stage() if p.parse_args().action=='stage' else run()
