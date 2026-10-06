"""Disposable native validation bank; original owner save bytes stay untouched."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone

from .audit import is_within
from .install_private import WORKSPACE, atomic_write
from .profile import guard
from .process_ownership import bottle_processes
from .runtime_paths import bottle_path
from . import save_banks

SCOPE = 'native-offline-dsr-disposable-validation'


def authorized():
    from .local_config import require_permission
    require_permission('allow_owner_test')


def fingerprint(tree):
    """No names, account IDs or plaintext save fields in the public digest."""
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError('Save fingerprint requires a physical directory')
    digest = hashlib.sha256(); count = 0
    for file in sorted(tree.rglob('*')):
        if file.is_symlink() or not is_within(file, tree):
            raise ValueError('Save fingerprint contains a redirect')
        if file.is_file():
            digest.update(str(file.relative_to(tree)).encode() + b'\0')
            digest.update(hashlib.sha256(file.read_bytes()).digest())
            count += 1
    return {'file_count': count, 'tree_sha256': digest.hexdigest()}


def receipt_path(bottle):
    path = bottle / '.dsr-mw2-validation.json'
    if path.is_symlink() or not is_within(path, bottle):
        raise ValueError('Validation receipt escapes private profile')
    return path


def verify(bottle, *, active=False):
    authorized()
    info = save_banks.inspect(bottle)
    live, root = save_banks.paths(bottle)
    receipt = json.loads(receipt_path(bottle).read_text())
    if receipt.get('version') != 1 or receipt.get('scope') != SCOPE:
        raise ValueError('Unknown disposable validation receipt')
    if active and info['active'] != 'validation':
        raise RuntimeError('Agent input requires the disposable validation bank; owner play is protected')
    for bank in ('m9', 'stock'):
        path = live if info['active'] == bank else root / bank
        if fingerprint(path) != receipt['preserved'][bank]:
            raise ValueError('Preserved owner bank changed; stop validation: ' + bank)
    candidate = live if info['active'] == 'validation' else root / 'validation'
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError('Disposable validation bank is absent')
    return {'id': receipt['id'], 'active': info['active'], 'owner_banks_unchanged': True}


def prepare(bottle):
    authorized()
    blockers = guard(bottle)
    if blockers:
        raise ValueError('; '.join(blockers))
    lock_path = bottle / '.dsr-mw2-session.lock'
    if lock_path.is_symlink() or not is_within(lock_path, bottle):
        raise ValueError('Validation session lock escapes profile')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError('Private session is active; preserving all saves')
        if receipt_path(bottle).exists():
            return verify(bottle)
        if save_banks.inspect(bottle)['active'] != 'm9':
            raise ValueError('Prepare only from the closed owner M9 bank')
        live, root = save_banks.paths(bottle)
        target = root / 'validation'
        temp = bottle / '.dsr-mw2-validation-preparing'
        if target.exists() or temp.exists() or temp.is_symlink():
            raise ValueError('Existing validation material is preserved; explicit recovery required')
        before = {'m9': fingerprint(live), 'stock': fingerprint(root / 'stock')}
        shutil.copytree(live, temp, copy_function=shutil.copy2)
        if fingerprint(temp) != before['m9'] or fingerprint(live) != before['m9']:
            raise ValueError('Validation copy did not match the preserved source')
        os.rename(temp, target)
        receipt = {'version': 1, 'id': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                   'scope': SCOPE, 'source_bank': 'm9', 'preserved': before,
                   'seed': before['m9'], 'owner_progress_edited': False}
        atomic_write(receipt_path(bottle), (json.dumps(receipt, indent=2)+'\n').encode())
        return verify(bottle)


def require_active():
    bottle = bottle_path()
    if (bottle / '.dsr-mw2-owner-testing.json').exists():
        raise RuntimeError('Owner test in progress: agent input is disabled')
    from .local_config import require_permission
    require_permission('allow_agent_gameplay')
    blockers = guard(bottle)
    if blockers:
        raise RuntimeError('Private validation profile check failed: ' + '; '.join(blockers))
    return verify(bottle, active=True)
