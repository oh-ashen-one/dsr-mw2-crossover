"""Run the original frame-entry shim against an original toy, never a game."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dsr_mw2.profile import command,environment,guard
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.validation_session import verify
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.install_private import atomic_write
from dsr_mw2.launch import network_wrapper

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tooling-local/native-entry'
SOURCES=['native/src/entry_observer.cpp','native/src/entry_observer.S',
         'native/tests/entry_target.S','native/tests/entry_probe.cpp']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=True)
    exe=OUT/'entry_probe.exe'
    subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
        '-Wconversion','-static','-fno-exceptions','-fno-rtti','-Wl,--no-insert-timestamp','-I',str(ROOT/'native/include'),
        *[str(ROOT/s) for s in SOURCES],'-o',str(exe)],check=True)
    name='entry_probe_'+sha(exe)[:16]+'.exe';b=bottle_path()
    import sys
    redirect='--redirect' in sys.argv
    suffix='-redirect' if redirect else ''
    with (b/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if guard(b) or bottle_processes(b):raise ValueError('Original console trial requires a closed private profile')
        verify(b);target=b/'drive_c/Tools/DSR-MW2'/name
        if target.is_symlink() or (target.exists() and sha(target)!=sha(exe)):raise ValueError('Existing toy binary differs')
        atomic_write(target,exe.read_bytes());log=OUT/(name+suffix+'.jsonl')
        with log.open('w') as out:
            p=subprocess.run([*network_wrapper('m9-test'),*command('C:\\Tools\\DSR-MW2\\'+name, *(['--redirect'] if redirect else []))],
                             env=environment(),stdout=out,stderr=out,timeout=30)
        for _ in range(40):
            if not bottle_processes(b):break
            time.sleep(1)
        report={'exit':p.returncode,'log':str(log.relative_to(ROOT)),'binary_sha256':sha(exe),
            'sources':{s:sha(ROOT/s) for s in [*SOURCES,'native/include/entry_observer.hpp']},
            'result_text':log.read_text(),'owner_saves':verify(b),'remaining_private_processes':bottle_processes(b),
            'game_launched':False,'native_game_callback_verified':False}
        (ROOT/('evidence/entry-observer'+suffix+'-toy-trial.json')).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))

if __name__=='__main__':main()
