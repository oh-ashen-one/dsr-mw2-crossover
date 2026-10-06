"""Compile/test original viewmodel source without starting a game or renderer."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dsr_mw2.pe_image import PEImage
from dsr_mw2.profile import command, environment, guard
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.validation_session import verify
from dsr_mw2.install_private import atomic_write
from dsr_mw2.launch import network_wrapper

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tooling-local/viewmodel-check'
SHA='a45aaa36dd2f6cc151670a639ea5547043cf38ea79ff4178b963c6ed71f98d7b'


def main(console=False):
    OUT.mkdir(parents=True,exist_ok=True)
    flags=['-std=c++17','-Wall','-Wextra','-Werror','-Wconversion','-I',str(ROOT/'native/include')]
    test=OUT/'packet-test'
    subprocess.run(['/usr/bin/clang++',*flags,'-g','-fsanitize=address,undefined',str(ROOT/'native/tests/viewmodel_packet_test.cpp'),'-o',str(test)],check=True)
    result=json.loads(subprocess.check_output([test,ROOT/'converted/mw2-2009/viewmodel-v1/m9.dsrvm'],text=True))
    image=(ROOT/'tooling-local/native-research'/SHA/'DarkSoulsRemastered.exe').read_bytes()
    if hashlib.sha256(image).hexdigest()!=SHA:raise ValueError('Static image changed')
    pe=PEImage(image)
    contracts={
        'visibility':(0x3549e0,'48895c2408574883ec2080b9a602000080488bd9'),
        'render_frame_end':(0xcd4630,'48895c242055574155415641574883ec40'),
        'present_call':(0xcd4683,'488b4d304533c00fb695c0010000488b01ff5040'),
        'renderer_vtable_constructor':(0xcd2af9,'488d0548697d00488907'),
    }
    for name,(rva,expected) in contracts.items():
        if pe.at(rva,len(bytes.fromhex(expected))).hex()!=expected:raise ValueError('Native render contract differs: '+name)
    report={'at':datetime.now(timezone.utc).isoformat(),'sanitized_packet_test':result,'retail_exe_sha256':SHA,
            'static_contracts':{k:{'rva':hex(v[0]),'bytes_match':True} for k,v in contracts.items()},
            'game_launched':False,'renderer_started':False,'runtime_verified':False}
    shader=OUT/'shader-check.exe'
    subprocess.run(['/opt/homebrew/bin/x86_64-w64-mingw32-g++',*flags,'-O2','-static','-fno-exceptions','-fno-rtti',
        '-Wl,--no-insert-timestamp','-DDSR_MW2_SHADER_CHECK',str(ROOT/'native/src/viewmodel_renderer.cpp'),
        '-ld3dcompiler','-ld3d11','-ldxgi','-luuid','-o',str(shader)],check=True)
    report['shader_check_sha256']=hashlib.sha256(shader.read_bytes()).hexdigest()
    if console:
        bottle=bottle_path();name='shader_check_'+report['shader_check_sha256'][:16]+'.exe'
        with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if guard(bottle) or bottle_processes(bottle):raise ValueError('Console check requires closed private profile')
            verify(bottle);target=bottle/'drive_c/Tools/DSR-MW2'/name
            if target.is_symlink() or (target.exists() and target.read_bytes()!=shader.read_bytes()):raise ValueError('Different existing shader check')
            atomic_write(target,shader.read_bytes())
            output=OUT/(name+'.log')
            with output.open('w') as log:
                p=subprocess.run([*network_wrapper('m9-test'),*command('C:\\Tools\\DSR-MW2\\'+name)],env=environment(),stdout=log,stderr=log,timeout=30)
            report['shader_console']={'exit':p.returncode,'output':output.read_text(),'game_launched':False,'device_created':False}
            for _ in range(40):
                if not bottle_processes(bottle):break
                time.sleep(1)
            report['remaining_private_processes']=bottle_processes(bottle);report['owner_saves']=verify(bottle)
    (ROOT/'evidence/viewmodel-offline-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if console and (report['shader_console']['exit'] or report['remaining_private_processes']):raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--console',action='store_true');main(p.parse_args().console)
