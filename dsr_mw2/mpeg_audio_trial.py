"""Disposable-only mono MPEG shot-bank trial; rejected stereo PCM stays blocked.

Native playback is unverified. Only the isolated candidate's two sound-bank
files can change, with exact baseline/installed hashes and paired rollback.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
from .install_audio import STOCK, RECEIPT as OWNER_AUDIO_RECEIPT
from .install_private import WORKSPACE, atomic_write, layout
from .process_ownership import bottle_processes
from .profile import guard
from .validation_session import verify

CANDIDATE={
    'sound/frpg_main.fsb':'cb12b51140d99884490f287cf8e80732213916247290d8c41fb99629447f1701',
    'sound/frpg_main.fev':'04f05841260d130bfcd262d037bf5129430543aea5f1e69ff77996c9db1a9db0',
}
RECEIPT='.dsr-mw2-mpeg-trial.json'


def permitted(mode):
    from .action_trial import permitted as gun_permitted
    return gun_permitted(mode) and os.environ.get('DSR_MW2_AUDIO_TRIAL')=='mono-mpeg-v1'


def digest(data):return hashlib.sha256(data).hexdigest()


def verified_payload(root,expected):
    result={}
    for name,sha in expected.items():
        p=root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError('Redirected audio path: '+name)
        result[name]=p.read_bytes()
        if digest(result[name])!=sha:raise ValueError('Changed audio bytes: '+name)
    return result


def replace_pair(root,before_hashes,payload):
    """Preflight both files before the first write; roll back partial writes."""
    if set(payload)!=set(STOCK) or set(before_hashes)!=set(STOCK):
        raise ValueError('Unexpected audio file set')
    before=verified_payload(root,before_hashes);changed=[]
    try:
        for name,data in payload.items():
            changed.append(name);atomic_write(root/name,data)
        verified_payload(root,{name:digest(data) for name,data in payload.items()})
    except Exception:
        for name in reversed(changed):atomic_write(root/name,before[name])
        raise


def check(mode,workspace=WORKSPACE):
    bottle,stock,game=layout(workspace);receipt=bottle/RECEIPT
    if not receipt.exists() and not receipt.is_symlink():return None
    try:
        if receipt.is_symlink():raise ValueError('Redirected MPEG trial receipt')
        if not permitted(mode):raise ValueError('Disposable MPEG audio installed; restore before owner launch')
        if json.loads(receipt.read_text()).get('installed')!=CANDIDATE:raise ValueError('MPEG trial receipt changed')
        verified_payload(stock,STOCK);verified_payload(game,CANDIDATE)
        return {'valid':True,'enabled':True,'disposable_mpeg_trial':True,'runtime_verified':False}
    except (OSError,ValueError,TypeError) as exc:
        return {'valid':False,'error':str(exc),'runtime_verified':False}


def mutate(action,workspace=WORKSPACE):
    bottle,stock,game=layout(workspace);receipt=bottle/RECEIPT
    lock_path=bottle/'.dsr-mw2-session.lock'
    if lock_path.is_symlink() or receipt.is_symlink():raise ValueError('Redirected private trial state')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if guard(bottle) or bottle_processes(bottle):raise ValueError('Close the private profile before audio changes')
        owner=verify(bottle);stock_data=verified_payload(stock,STOCK)
        if action=='install':
            if receipt.exists():raise ValueError('Preserving existing MPEG trial')
            # Keep the separately managed/rejected owner audio path untouched.
            if (bottle/OWNER_AUDIO_RECEIPT).exists():
                from .install_audio import read_receipt
                if read_receipt(bottle):raise ValueError('Restore existing owner audio first')
            source=workspace/'converted/dsr/m9-mpeg-audio-study'
            data=verified_payload(source,{Path(p).name:h for p,h in CANDIDATE.items()})
            payload={p:data[Path(p).name] for p in CANDIDATE}
            replace_pair(game,STOCK,payload)
            try:atomic_write(receipt,(json.dumps({'installed':CANDIDATE,'before':STOCK,'runtime_verified':False},indent=2)+'\n').encode())
            except Exception:
                replace_pair(game,CANDIDATE,stock_data);raise
        else:
            r=json.loads(receipt.read_text())
            if r.get('installed')!=CANDIDATE or r.get('before')!=STOCK:raise ValueError('Changed MPEG receipt')
            replace_pair(game,CANDIDATE,stock_data)
            receipt.unlink()
        return {'action':action,'owner_saves':owner,'runtime_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','restore'));args=parser.parse_args()
    print(json.dumps(mutate(args.action)))
