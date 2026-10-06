"""Private DSR window configuration and original external window helper.

Does not open a game, control gameplay, edit saves, or change global settings.
The existing launcher starts the helper only after its own game appears.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from .audit import is_within
from .install_private import atomic_write
from .process_ownership import bottle_processes
from .profile import guard, command, environment

CONFIG = 'drive_c/users/crossover/AppData/Local/FromSoftware/NBGI/DarkSouls/DarkSouls.ini'
RECEIPT = '.dsr-mw2-window-controls.json'
SOURCE = 'native/tools/window_controls.cpp'
EXE = 'dsr_window_controls.exe'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def windowed_config(text: str) -> str:
    """Surgical edit of existing display settings; keep keys/audio untouched."""
    settings = {'DisplaySetting': {'WindowMode': 1},
                'DisplaySettingWindow': {'Left': 80, 'Top': 80, 'Width': 1600, 'Height': 900}}
    for section, values in settings.items():
        pattern = r'(?m)^\[' + re.escape(section) + r'\][^\S\r\n]*\r?\n(?:(?!\[)[^\n]*\n?)*'
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous window display section: ' + section)
        match = matches[0]
        body = match[0]
        for key, value in values.items():
            field = r'(?m)^(' + key + r'[ \t]*=[ \t]*)\d+([ \t]*\r?)$'
            body, count = re.subn(field, lambda m: m[1] + str(value) + m[2], body)
            if count != 1:
                raise ValueError('Missing or ambiguous window display value: ' + key)
        text = text[:match.start()] + body + text[match.end():]
    return text


def safe(path: Path, root: Path) -> Path:
    if path.is_symlink() or not is_within(path, root) or path.resolve() != path:
        raise ValueError('Window controls path is redirected')
    return path


def specification(workspace: Path) -> dict:
    out = workspace / 'tooling-local/window-controls'
    record = json.loads(safe(out / 'build.json', workspace).read_text())
    if (record.get('source') != SOURCE or record.get('file') != EXE or
            not re.fullmatch('[0-9a-f]{64}', record.get('sha256', '')) or
            record.get('source_sha256') != digest(safe(workspace / SOURCE, workspace).read_bytes())):
        raise ValueError('Window helper source/build receipt changed; rebuild original source')
    binary = safe(out / EXE, workspace).read_bytes()
    if len(binary) != record.get('bytes') or digest(binary) != record['sha256']:
        raise ValueError('Window helper build bytes changed')
    return record


def staged_path(bottle: Path, record: dict) -> Path:
    return safe(bottle / 'drive_c/Tools/DSR-MW2/window-controls' / record['sha256'] / EXE, bottle)


def stage(workspace: Path, bottle: Path) -> dict:
    if guard(bottle):
        raise ValueError('Private window profile guard failed')
    record = specification(workspace)
    lock_path = safe(bottle / '.dsr-mw2-session.lock', bottle)
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError('Private session is active; preserving its window settings')
        target = staged_path(bottle, record)
        if target.exists() and digest(target.read_bytes()) != record['sha256']:
            raise ValueError('Staged window helper changed')
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, (workspace / 'tooling-local/window-controls' / EXE).read_bytes())
        receipt = safe(bottle / RECEIPT, bottle)
        changed = False
        if not receipt.exists():
            config = safe(bottle / CONFIG, bottle)
            before = config.read_bytes()
            after = windowed_config(before.decode('utf-8')).encode('utf-8')
            backup = safe(config.with_name('DarkSouls.before-window-controls-' + digest(before) + '.ini'), bottle)
            if backup.exists() and backup.read_bytes() != before:
                raise ValueError('Window configuration backup changed')
            if not backup.exists():
                atomic_write(backup, before)
            atomic_write(config, after)
            atomic_write(receipt, (json.dumps({'version': 1, 'enabled': True,
                'before_sha256': digest(before), 'after_sha256': digest(after),
                'backup': str(backup.relative_to(bottle)), 'game_launched': False}) + '\n').encode())
            changed = before != after
        else:
            saved = json.loads(receipt.read_text())
            if saved.get('version') != 1 or saved.get('enabled') is not True:
                raise ValueError('Window controls receipt needs review')
            # Preserve resolution changes the owner makes on later sessions.
    return {'staged': True, 'configuration_changed': changed, 'sha256': record['sha256'],
            'game_launched': False, 'runtime_verified': False}


def start(mode: str, pids: list[int], workspace: Path, bottle: Path,
          network_prefix: list[str], children: list[subprocess.Popen]) -> dict:
    if mode not in {'m9', 'm9-test'} or len(pids) != 1 or not (bottle / RECEIPT).exists():
        return {'status': 'window_controls_skipped'}
    try:
        if guard(bottle) or pids[0] not in bottle_processes(bottle):
            raise ValueError('Expected one game in this private bottle')
        if not network_prefix or network_prefix[0] != '/usr/bin/sandbox-exec':
            raise ValueError('Private offline wrapper missing')
        if json.loads(safe(bottle / RECEIPT, bottle).read_text()).get('enabled') is not True:
            raise ValueError('Private window controls are not enabled')
        # Steam's app path is an alias: it must resolve to this candidate.
        game = safe(bottle / 'drive_c/Games/DSR-MW2', bottle)
        alias = bottle / 'drive_c/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED'
        if not alias.is_symlink() or alias.resolve() != game:
            raise ValueError('Private Steam game alias changed')
        record = specification(workspace)
        target = staged_path(bottle, record)
        if digest(target.read_bytes()) != record['sha256']:
            raise ValueError('Staged window helper hash changed')
        output = safe(workspace / f'tooling-local/launch/window-controls-{time.time_ns()}.jsonl', workspace)
        output.parent.mkdir(parents=True, exist_ok=True)
        windows_exe = 'C:\\Tools\\DSR-MW2\\window-controls\\' + record['sha256'] + '\\' + EXE
        with output.open('x') as log:
            child = subprocess.Popen([*network_prefix, *command(windows_exe, '--watch')],
                cwd=target.parent, env=environment(), stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT)
        children.append(child)
        return {'status': 'window_controls_started', 'pid': child.pid,
                'log': str(output.relative_to(workspace)), 'runtime_verified': False}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'status': 'window_controls_unavailable', 'reason': str(exc)}
