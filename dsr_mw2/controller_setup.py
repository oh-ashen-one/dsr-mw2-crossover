"""Configure only this task's WineBus controller translation, with Wine closed.

CodeWeavers documents Disable hidraw as the Sony-to-XInput compatibility option.
This is not a macOS, Steam-account, security, pairing or game-save setting.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re

from .audit import is_within
from .install_private import atomic_write
from .profile import guard
from .process_ownership import bottle_processes

SECTION = r'System\\CurrentControlSet\\Services\\winebus'
VALUE = '"DisableHidraw"=dword:00000001'


def set_hidraw_disabled(text: str) -> tuple[str, str | None]:
    """Strict surgical edit: preserve all unrelated registry bytes and values."""
    blocks = list(re.finditer(r'^\[([^\]]+)\][^\n]*\n', text, re.MULTILINE))
    matches = [i for i, m in enumerate(blocks) if m[1].lower() == SECTION.lower()]
    if len(matches) != 1:
        raise ValueError('Expected exactly one existing private WineBus section')
    index = matches[0]
    start = blocks[index].end()
    end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
    body = text[start:end]
    values = list(re.finditer(r'^"DisableHidraw"=.*$', body, re.MULTILINE | re.IGNORECASE))
    if len(values) > 1:
        raise ValueError('Ambiguous WineBus controller setting')
    previous = values[0][0] if values else None
    if previous is not None and not re.fullmatch(r'"DisableHidraw"=dword:0000000[01]', previous, re.IGNORECASE):
        raise ValueError('Unexpected WineBus controller value; preserve it')
    if values:
        m = values[0]
        body = body[:m.start()] + VALUE + body[m.end():]
    else:
        # Insert after the optional timestamp comment, keeping Wine formatting.
        offset = body.index('\n') + 1 if body.startswith('#time=') else 0
        body = body[:offset] + VALUE + '\n' + body[offset:]
    return text[:start] + body + text[end:], previous


def configure(bottle: Path) -> dict:
    reasons = guard(bottle)
    if reasons:
        raise ValueError('; '.join(reasons))
    registry = bottle / 'system.reg'
    lock_path = bottle / '.dsr-mw2-session.lock'
    receipt = bottle / '.dsr-mw2-controller.json'
    for path in (registry, lock_path, receipt):
        if path.is_symlink() or not is_within(path, bottle):
            raise ValueError('Controller configuration escapes the private bottle')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError('Private Wine session is active; preserve controller settings')
        before = registry.read_bytes()
        after_text, previous = set_hidraw_disabled(before.decode('utf-8'))
        after = after_text.encode('utf-8')
        if before == after:
            return {'changed': False, 'hidraw_disabled': True, 'runtime_verified': False}
        if receipt.exists():
            raise ValueError('Existing controller-change receipt requires review')
        report = {'version': 1, 'setting': 'WineBus/DisableHidraw', 'value': 1,
                  'previous_line': previous, 'changed': True,
                  'before_sha256': hashlib.sha256(before).hexdigest(),
                  'after_sha256': hashlib.sha256(after).hexdigest(),
                  'game_launched': False, 'runtime_verified': False,
                  'source': 'https://support.codeweavers.com/en_US/troubleshooting/using-controllers-in-crossover'}
        atomic_write(receipt, (json.dumps(report, indent=2) + '\n').encode())
        try:
            atomic_write(registry, after)
        except Exception:
            receipt.unlink()
            raise
        return report
