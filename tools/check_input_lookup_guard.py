"""Execute our original empty-input-lookup regression fixture, without a game."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dsr_mw2.install_private import atomic_write
from dsr_mw2.launch import network_wrapper
from dsr_mw2.profile import guard, command, environment
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path, WORKSPACE
from dsr_mw2.validation_session import verify


def run():
    bottle=bottle_path()
    if guard(bottle) or bottle_processes(bottle):raise RuntimeError('Expected closed private profile')
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        binary=WORKSPACE/'tooling-local/native-input/input_lookup_guard_fixture.exe'
        sources=['native/tests/input_lookup_guard_fixture.cpp','native/tests/input_lookup_guard_fixture.S']
        subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++','-std=c++17','-Wall','-Wextra','-Werror',
            '-Wconversion','-O2','-static','-fno-exceptions','-fno-rtti','-Wl,--no-insert-timestamp',
            '-I',str(WORKSPACE/'native/include'),*[str(WORKSPACE/s) for s in sources],'-o',str(binary)],check=True)
        digest=hashlib.sha256(binary.read_bytes()).hexdigest()
        name='input_lookup_guard_fixture_'+digest[:16]+'.exe'
        target=bottle/'drive_c/Tools/DSR-MW2'/name
        if target.is_symlink() or not target.resolve().is_relative_to(bottle.resolve()):raise ValueError('Fixture path redirect')
        atomic_write(target,binary.read_bytes())
        result=subprocess.run([*network_wrapper('m9-test'),*command('C:\\Tools\\DSR-MW2\\'+name)],
            env=environment(),capture_output=True,text=True,timeout=25)
        if result.returncode:raise RuntimeError('Input guard fixture failed: '+str(result.returncode))
        checks=json.loads(result.stdout)
        if set(checks)!={'empty_completed','valid_preserved','reserved_preserved','flags_preserved'} or not all(checks.values()):
            raise ValueError('Input guard behavior failed')
        for _ in range(15):
            if not bottle_processes(bottle):break
            time.sleep(1)
        remaining=bottle_processes(bottle)
        report={'checks':checks,'exit_code':result.returncode,'fixture_sha256':digest,
            'source_sha256':{s:hashlib.sha256((WORKSPACE/s).read_bytes()).hexdigest()
                for s in [*sources,'native/include/input_lookup_guard.hpp']},
            'owner_saves':verify(bottle),'game_launched':False,'agent_game_input':False,
            'remaining_private_processes':remaining,'native_game_fix_verified':False}
        (WORKSPACE/'evidence/input-lookup-guard-fixture.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        if remaining:raise RuntimeError('Private fixture process cleanup still pending')


if __name__=='__main__':run()
