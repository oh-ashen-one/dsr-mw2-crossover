"""Build/install/restore our original passthrough for disposable input validation.

Only the private candidate is mutable. Preserved backend bytes are the hash-pinned
retail DLL. Controller APIs use the installed CrossOver XInput 1.4 module; only
legacy audio/guide ordinals absent from Wine retain retail forwarding.
GetState forwards unchanged. A separately gated, bounded frame-entry observer
can patch the exact local prologue, record arguments and restore it. No writer.
"""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dsr_mw2.install_private import atomic_write
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.profile import guard,command,environment
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.validation_session import verify
from dsr_mw2.native_runtime import RUNTIME_HASHES

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tooling-local/native-input'
RECEIPT=ROOT/'evidence/native-input-build.json'
SOURCES=['native/src/xinput_observer.cpp','native/xinput_observer.def',
         'native/src/dsr_snapshot.cpp','native/include/dsr_snapshot.hpp',
         'native/src/entry_observer.cpp','native/src/entry_observer.S','native/include/entry_observer.hpp',
         'native/include/m9_magazine.hpp','native/include/m9_native_aim.hpp','native/include/m9_aim_latch.hpp',
         'native/include/m9_recoil_delta.hpp','native/include/m9_camera_angles.hpp',
         'native/include/iw4_view_kick.hpp','native/src/iw4_view_kick.cpp',
         'native/include/viewmodel_packet.hpp','native/include/packet_buffer.hpp','native/include/viewmodel_renderer.hpp','native/src/viewmodel_renderer.cpp']
BACKEND='xinput1_3_backend.dll'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    OUT.mkdir(exist_ok=True)
    binary=OUT/'xinput1_3.dll'
    subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++','-std=c++17','-Wall','-Wextra','-Werror','-Wconversion',
        '-O2','-shared','-static','-fno-exceptions','-fno-rtti','-Wl,--no-insert-timestamp','-I',str(ROOT/'native/include'),
        *[str(ROOT/s) for s in SOURCES if Path(s).suffix in {'.cpp','.S','.def'}],'-ld3dcompiler','-ldxgi','-ld3d11','-luuid','-o',str(binary)],check=True)
    imports=subprocess.check_output(['/opt/homebrew/bin/x86_64-w64-mingw32-objdump','-p',str(binary)],text=True)
    (OUT/'pe.txt').write_text(imports)
    for forbidden in ('WriteProcessMemory','CreateRemoteThread','DebugActiveProcess','SetThreadContext','SendInput','CreateProcessW'):
        if forbidden in imports:raise ValueError('Unexpected mutation/debug/input API: '+forbidden)
    for name in ('XInputGetState','xinput1_4.XInputSetState','xinput1_4.XInputGetCapabilities',
                 'xinput1_4.XInputEnable','xinput1_4.XInputGetBatteryInformation',
                 'xinput1_4.XInputGetKeystroke','xinput1_4.#100'):
        if name not in imports:raise ValueError('Missing passthrough: '+name)
    report={'at':datetime.now(timezone.utc).isoformat(),'sha256':sha(binary),
            'sources':{s:sha(ROOT/s) for s in SOURCES},'retail_backend_sha256':RUNTIME_HASHES['xinput1_3.dll'],
            'controller_backend':'installed CrossOver system32/xinput1_4.dll; unchanged state/capabilities',
            'input_modified':'only explicit play-v1 scoped M9 gun trial','memory_hooks':'exact entries only; observe-v1 frame 30 seconds; observe-v2 entries 60 seconds; observe-v3 typed post-input/ammo 90 seconds; play-v1 integrated gun trial 180 seconds; explicit bonfire-v1 plus loadout-600s-v1 session 600 seconds',
            'owner_test_limit_ms':7200000,'viewmodel_trial':'source-vm-v1; exact native render/visibility hooks; D3D11 deferred commands',
            'inventory_writes':False,'runtime_verified':False}
    RECEIPT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


def expected():
    report=json.loads(RECEIPT.read_text())
    for p,h in report['sources'].items():
        if sha(ROOT/p)!=h:raise ValueError('Native input source changed: '+p)
    if report['retail_backend_sha256']!=RUNTIME_HASHES['xinput1_3.dll']:
        raise ValueError('Unexpected native controller backend')
    return {**RUNTIME_HASHES,'xinput1_3.dll':report['sha256'],BACKEND:RUNTIME_HASHES['xinput1_3.dll']}


def mutate(action):
    bottle=bottle_path();root=bottle/'drive_c/Games/DSR-MW2'
    if guard(bottle):raise ValueError('Private profile guard failed')
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if bottle_processes(bottle):raise ValueError('Private processes active')
        verify(bottle)
        wanted=expected()
        target=root/'xinput1_3.dll';backend=root/BACKEND
        if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in (target,backend)):
            raise ValueError('Native input target redirect')
        original=RUNTIME_HASHES['xinput1_3.dll']
        if action=='install':
            if sha(target)!=original or backend.exists():raise ValueError('Preserving existing native input install')
            binary=OUT/'xinput1_3.dll'
            if sha(binary)!=wanted['xinput1_3.dll']:raise ValueError('Build bytes changed')
            atomic_write(backend,target.read_bytes());atomic_write(target,binary.read_bytes())
        else:
            if sha(backend)!=original or sha(target)!=wanted['xinput1_3.dll']:
                raise ValueError('Preserving changed native input trial files')
            atomic_write(target,backend.read_bytes())
            # Retain the verified duplicate backend in task outputs, outside game loading.
            saved=OUT/'retail-backend-preserved.dll'
            if saved.exists() and sha(saved)!=original:raise ValueError('Existing backend archive differs')
            atomic_write(saved,backend.read_bytes());backend.unlink()
        print(json.dumps({'action':action,'owner_saves':verify(bottle),'native_input_sha256':sha(target)}))


def console():
    from dsr_mw2.launch import network_wrapper
    from dsr_mw2.native_runtime import check
    source=ROOT/'native/src/input_module_probe.cpp'
    binary=OUT/'input_module_probe.exe'
    subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
        '-Wconversion','-static','-fno-exceptions','-fno-rtti','-Wl,--no-insert-timestamp',str(source),'-o',str(binary)],check=True)
    tag=sha(binary)[:16];name='input_module_probe_'+tag+'.exe'
    bottle=bottle_path()
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if guard(bottle) or bottle_processes(bottle) or check(bottle/'drive_c/Games/DSR-MW2',input_trial=True):
            raise ValueError('Expected closed isolated profile and exact observer trial')
        verify(bottle)
        target=bottle/'drive_c/Tools/DSR-MW2'/name
        if target.is_symlink() or (target.exists() and sha(target)!=sha(binary)):
            raise ValueError('Console target changed')
        atomic_write(target,binary.read_bytes())
        logfile=OUT/('console-'+tag+'.jsonl')
        with logfile.open('w') as output:
            p=subprocess.run([*network_wrapper('m9-test'),*command('C:\\Tools\\DSR-MW2\\'+name,
                dll_overrides='xinput1_3=n,b')],env=environment(),cwd=bottle/'drive_c/Games/DSR-MW2',
                stdout=output,stderr=output,timeout=30)
        for _ in range(40):
            if not bottle_processes(bottle):break
            time.sleep(1)
        report={'exit':p.returncode,'log':str(logfile.relative_to(ROOT)),
                'probe_sha256':sha(binary),'source_sha256':sha(source),'source':str(source.relative_to(ROOT)),
                'owner_saves':verify(bottle),'remaining_private_processes':bottle_processes(bottle),
                'game_launched':False,'native_game_callback_verified':False}
        (OUT/('console-'+tag+'-receipt.json')).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('build','install','restore','console'))
    action=parser.parse_args().action
    if action=='build':build()
    elif action=='console':console()
    else:mutate(action)
