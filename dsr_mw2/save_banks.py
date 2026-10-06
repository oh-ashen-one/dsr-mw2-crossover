"""Keep private stock/cloud saves and offline M9 saves in separate physical banks.

Only move this task's Documents/NBGI folder while its session is closed. No
account identifiers are interpreted, no save bytes are edited, and no links
are created. Interrupted swaps fail closed for explicit agent recovery.
"""
import fcntl
import json
import os
from pathlib import Path

from .audit import is_within
from .install_private import atomic_write
from .process_ownership import bottle_processes

BANKS = {'stock', 'm9', 'validation'}


def paths(bottle):
    live = bottle / 'drive_c/users/crossover/Documents/NBGI'
    root = bottle / '.dsr-mw2-save-banks'
    for p in (live, root):
        if p.is_symlink() or not is_within(p, bottle):
            raise ValueError('Save bank escapes the private profile')
    return live, root


def inspect(bottle):
    live, root = paths(bottle)
    state = root / 'active.json'
    for tree in (live, root):
        if tree.exists():
            if not tree.is_dir() or any(p.is_symlink() for p in tree.rglob('*')):
                raise ValueError('Save bank contains an unverified redirect')
    if (root / 'pending.json').exists():
        raise ValueError('Interrupted save-bank switch; preserve all banks for agent recovery')
    if not state.exists():
        if root.exists() and any(root.iterdir()):
            raise ValueError('Unmanaged save-bank contents; preserving them')
        return {'initialized': False, 'active': 'stock'}
    value = json.loads(state.read_text())
    if value not in tuple({'version': 1, 'active': bank} for bank in BANKS):
        raise ValueError('Unrecognized save-bank state')
    active = value['active']
    if not live.is_dir() or (root / active).exists():
        raise ValueError('Save bank topology disagrees with its receipt')
    if any(p.name not in {'active.json', *BANKS} for p in root.iterdir()):
        raise ValueError('Unexpected save-bank entry')
    return {'initialized': True, 'active': active}


def select_locked(bottle, target):
    """Caller holds the private session lock across this call and game lifetime."""
    if target not in BANKS:
        raise ValueError('Unknown private save bank')
    if bottle_processes(bottle):
        raise ValueError('Private session is active; preserving its saves')
    info = inspect(bottle)
    live, root = paths(bottle)
    root.mkdir(exist_ok=True)
    state = root / 'active.json'
    if not info['initialized']:
        live.mkdir(parents=True, exist_ok=True)
        atomic_write(state, b'{"version": 1, "active": "stock"}\n')
    source = info['active']
    if source == target:
        return inspect(bottle)
    archived, incoming = root / source, root / target
    if archived.exists():
        raise ValueError('Active save archive already exists')
    incoming.mkdir(exist_ok=True)
    if not incoming.is_dir():
        raise ValueError('Incoming save bank is not a folder')
    journal = root / 'pending.json'
    atomic_write(journal, (json.dumps({'from': source, 'to': target})+'\n').encode())
    moved_out = moved_in = False
    try:
        os.rename(live, archived)
        moved_out = True
        os.rename(incoming, live)
        moved_in = True
        atomic_write(state, (json.dumps({'version': 1, 'active': target})+'\n').encode())
    except Exception:
        # A failure during rollback intentionally leaves the journal in place.
        # Never overwrite a bank or guess through an interrupted operation.
        if moved_in:
            os.rename(live, incoming)
        if moved_out:
            os.rename(archived, live)
        atomic_write(state, (json.dumps({'version': 1, 'active': source})+'\n').encode())
        journal.unlink()
        raise
    journal.unlink()
    return inspect(bottle)


def select(bottle, target):
    lock = bottle / '.dsr-mw2-session.lock'
    if lock.is_symlink() or not is_within(lock, bottle):
        raise ValueError('Private session lock escapes profile')
    with lock.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return select_locked(bottle, target)
