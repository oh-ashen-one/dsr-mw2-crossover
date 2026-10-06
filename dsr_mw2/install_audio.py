"""Reversible, hash-pinned native M9 shot audio in the private candidate only."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from .audit import is_within
from .install_private import WORKSPACE, atomic_write, layout, sha
from .process_ownership import bottle_processes

STOCK = {
    'sound/frpg_main.fsb': '7e9ef82652f361cda5e5e8c18178d747f29a4685914d8f02c0ffd7957c428074',
    'sound/frpg_main.fev': '28ebfd34bb9e893fe4cfa93a85ae43d2832f75175170bf60ca5b84f8fffa488b',
}
CANDIDATE = {
    'sound/frpg_main.fsb': '89f6d616dfdd1f36ad3fbc32fc270138659c7194ae5a0addc4e4b1253bcd7423',
    'sound/frpg_main.fev': '0c418b099e4a14c154d842e8b66fd3220a0ff642de75f12671e6e909c5b2eb02',
}
RECEIPT = '.dsr-mw2-audio-install.json'
REJECTED_FSB = '89f6d616dfdd1f36ad3fbc32fc270138659c7194ae5a0addc4e4b1253bcd7423'


def read_receipt(bottle):
    path = bottle / RECEIPT
    if path.is_symlink() or not is_within(path, bottle):
        raise ValueError('Audio receipt escapes private bottle')
    if not path.exists():
        return False
    report = json.loads(path.read_text())
    if not isinstance(report, dict) or type(report.get('enabled')) is not bool:
        raise ValueError('Invalid audio receipt')
    expected = CANDIDATE if report['enabled'] else STOCK
    if report.get('installed_hashes') != expected:
        raise ValueError('Audio receipt does not match the pinned native banks')
    return report['enabled']


def check(workspace=WORKSPACE):
    try:
        bottle, stock, game = layout(workspace)
        enabled = read_receipt(bottle)
        for relative, digest in STOCK.items():
            p = stock / relative
            if not is_within(p, stock) or sha(p) != digest:
                raise ValueError('Private stock audio changed: '+relative)
        for relative, digest in (CANDIDATE if enabled else STOCK).items():
            p = game / relative
            if not is_within(p, game) or sha(p) != digest:
                raise ValueError('Unmanaged private audio change: '+relative)
        return {'valid':True, 'enabled':enabled, 'runtime_verified':False,
                'runtime_rejected': enabled and CANDIDATE.get('sound/frpg_main.fsb') == REJECTED_FSB}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'valid':False, 'runtime_verified':False, 'error':str(exc)}


def install(workspace=WORKSPACE, *, enable):
    if enable and CANDIDATE.get('sound/frpg_main.fsb') == REJECTED_FSB:
        raise ValueError('This audio candidate crashed native FMOD during startup; preserve stock audio')
    bottle, stock, game = layout(workspace)
    lock_path = bottle / '.dsr-mw2-session.lock'
    if lock_path.is_symlink() or not is_within(lock_path, bottle):
        raise ValueError('Private session lock escapes bottle')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError('Private session is active; preserving its audio')
        state = check(workspace)
        if not state['valid']:
            raise ValueError(state['error'])
        expected = CANDIDATE if enable else STOCK
        source = workspace / 'converted/dsr/m9-native-audio-candidate/mod' if enable else stock
        payload = {}
        for relative, digest in expected.items():
            p = source / relative
            if not is_within(p, source):
                raise ValueError('Audio source escapes its reviewed directory')
            payload[relative] = p.read_bytes()
            if hashlib.sha256(payload[relative]).hexdigest() != digest:
                raise ValueError('Audio differs from the reviewed native candidate')
        before = {relative:(game / relative).read_bytes() for relative in STOCK}
        changed = []
        try:
            for relative, data in payload.items():
                atomic_write(game / relative, data)
                changed.append(relative)
            if {relative:sha(game / relative) for relative in STOCK} != expected:
                raise ValueError('Installed audio verification failed')
            report = {'enabled':enable, 'installed_hashes':dict(expected),
                      'stock_baseline_preserved':True, 'runtime_verified':False,
                      'scope':'Native shared crossbow shot sample; all users of this sound change. No reload foley.'}
            atomic_write(bottle / RECEIPT, (json.dumps(report, indent=2)+'\n').encode())
        except Exception:
            for relative in reversed(changed):
                atomic_write(game / relative, before[relative])
            raise
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--enable', action='store_true')
    group.add_argument('--restore', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = check() if args.check else install(enable=args.enable)
    print(json.dumps(result, indent=2))
    return 1 if result.get('valid') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
