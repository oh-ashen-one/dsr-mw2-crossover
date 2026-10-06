"""Exact, reversible assets for the explicitly gated disposable gun trial."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
from .runtime_paths import bottle_path
from .process_ownership import bottle_processes
from .profile import guard
from .validation_session import verify
from .install_private import atomic_write

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'converted/dsr/action-trial-v1'
BACKUP=ROOT/'tooling-local/action-backups'
PATHS=('chr/c0000.esd.dcx','chr/c0000.anibnd.dcx','chr/c0000_a4x.anibnd.dcx','parts/WP_A_1401.partsbnd.dcx','param/GameParam/GameParam.parambnd.dcx')
ARMORY_PATHS=('parts/WP_A_1406.partsbnd.dcx','script/talk/m18_01_00_00.talkesdbnd.dcx','msg/ENGLISH/menu.msgbnd.dcx','msg/ENGLISH/item.msgbnd.dcx')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def receipt(b):return b/'.dsr-mw2-action-trial.json'
def permitted(mode):
    return mode=='m9-test' and os.environ.get('DSR_MW2_NATIVE_INPUT_TRIAL')=='validation-v1' and os.environ.get('DSR_MW2_FRAME_TRIAL')=='observe-v3' and os.environ.get('DSR_MW2_GUN_TRIAL')=='play-v1'
def manifest():
    r=json.loads((OUT/'manifest.json').read_text())
    if set(r['files']) not in (set(PATHS),set(PATHS+ARMORY_PATHS)) or set(r['stock'])!=set(r['files']):raise ValueError('Unexpected action asset set')
    for p,h in r['files'].items():
        f=OUT/p
        if f.is_symlink() or not f.resolve().is_relative_to(OUT) or sha(f)!=h:raise ValueError('Action build changed: '+p)
    return r

def check(mode):
    b=bottle_path();r=receipt(b)
    if not r.exists():
        return ['Gun trial requested without its prepared action assets'] if permitted(mode) else []
    if not permitted(mode):return ['Disposable gun assets installed; normal owner launch is disabled until restoration']
    try:
        if set(json.loads(r.read_text())['installed'])==set(PATHS+ARMORY_PATHS) and os.environ.get('DSR_MW2_LOADOUT_TRIAL')!='bonfire-v1':
            return ['Native armory assets require the explicit bonfire-v1 disposable gate']
        expected_override(b/'drive_c/Games/DSR-MW2')
        return []
    except (ValueError,OSError,KeyError) as e:return [str(e)]

def expected_override(candidate):
    b=bottle_path();path=receipt(b)
    if path.is_symlink():raise ValueError('Redirected action receipt')
    r=json.loads(path.read_text());m=manifest()
    if r['installed']!=m['files'] or set(r['before'])!=set(m['files']):raise ValueError('Action receipt differs')
    for p,h in r['installed'].items():
        f=candidate/p
        if f.is_symlink() or not f.resolve().is_relative_to(candidate) or sha(f)!=h:raise ValueError('Installed action asset changed: '+p)
        stock=b/'drive_c/Games/Dark Souls Remastered'/p
        if stock.is_symlink() or (sha(stock) if stock.exists() else None)!=m['stock'][p]:raise ValueError('Private stock action baseline changed: '+p)
        if r['before'][p] is not None:
            backup=BACKUP/r['before'][p]
            if sha(backup)!=r['before'][p]:raise ValueError('Action backup changed')
        elif p!='parts/WP_A_1406.partsbnd.dcx':raise ValueError('Only the new armory model may have no baseline')
    return dict(r['installed'])

def mutate(action):
    b=bottle_path();candidate=b/'drive_c/Games/DSR-MW2'
    with (b/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if guard(b) or bottle_processes(b):raise ValueError('Action switch requires closed private profile')
        verify(b);r=receipt(b)
        if action=='install':
            from .install_private import inspect_install
            if r.exists() or not inspect_install()['installed']:raise ValueError('Existing candidate is not the managed baseline')
            m=manifest();BACKUP.mkdir(exist_ok=True);before={}
            for name in ('native-gun-trial-runtime.json','native-player-reference-runtime.json','native-type-table-runtime.json'):
                failed=json.loads((ROOT/'evidence'/name).read_text())
                if failed['result']=='startup_crash_before_character' and m['files']==failed['package']['files']:
                    raise ValueError('This exact package crashed native startup; isolate or fix it before retry')
            for p in m['files']:
                f=candidate/p
                if f.is_symlink() or not f.resolve().is_relative_to(candidate):raise ValueError('Redirected action target')
                if not f.exists():
                    if p!='parts/WP_A_1406.partsbnd.dcx' or m['stock'][p] is not None:raise ValueError('Missing native baseline: '+p)
                    before[p]=None;continue
                if p=='parts/WP_A_1406.partsbnd.dcx':raise ValueError('Preserving existing armory model')
                h=sha(f);before[p]=h;backup=BACKUP/h
                if backup.exists() and sha(backup)!=h:raise ValueError('Existing backup differs')
                if p.startswith('chr/') and h!=m['stock'][p]:raise ValueError('Unmanaged native action data')
                atomic_write(backup,f.read_bytes())
            atomic_write(r,(json.dumps({'before':before,'installed':m['files']},indent=2)+'\n').encode())
            changed=[]
            try:
                for p in m['files']:atomic_write(candidate/p,(OUT/p).read_bytes());changed.append(p)
                expected_override(candidate)
            except Exception:
                for p in changed:
                    if before[p] is None:(candidate/p).unlink()
                    else:atomic_write(candidate/p,(BACKUP/before[p]).read_bytes())
                r.unlink();raise
        else:
            expected_override(candidate);m=json.loads(r.read_text())
            for p,h in m['before'].items():
                if h is None:(candidate/p).unlink()
                else:atomic_write(candidate/p,(BACKUP/h).read_bytes())
            archived=BACKUP/('restored-'+sha(r)+'.json');atomic_write(archived,r.read_bytes());r.unlink()
        print(json.dumps({'action':action,'owner_saves':verify(b)}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('install','restore'));mutate(p.parse_args().action)
