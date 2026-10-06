"""Bounded, read-only observations during an owner-started M9 session.

This module cannot launch the game. The launcher's existing process watcher
may call start() once after the private game has started. No input, injection,
save access, camera write or inventory write is provided.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .audit import is_within
from .install_private import atomic_write
from .process_ownership import bottle_processes
from .profile import guard, command, environment
from .save_banks import inspect as inspect_banks

PROBE = 'dsr_readonly_probe_v3.exe'
def windows_probe(record):
    return 'C:\\Tools\\DSR-MW2\\observer-v3\\' + record['sha256'] + '\\' + PROBE


def specification(workspace: Path) -> dict:
    report_path = workspace / 'evidence/owner-probe-build.json'
    if report_path.is_symlink() or not is_within(report_path, workspace):
        raise ValueError('Observer build receipt escapes this checkout')
    report = json.loads(report_path.read_text())
    if not isinstance(report, dict) or not isinstance(report.get('source_sha256'), dict):
        raise ValueError('Observer build receipt is not a supported object')
    record = report.get('external_probe', {})
    if (not isinstance(record, dict) or record.get('file') != PROBE or record.get('schema') != 3 or
            not isinstance(record.get('sha256'), str) or
            not re.fullmatch('[0-9a-f]{64}', record['sha256']) or
            type(record.get('bytes')) is not int or not 0 < record['bytes'] < 4_000_000 or
            record.get('capture_seconds') != 120 or record.get('max_wait_for_character_seconds') != 300 or
            record.get('process_access') != ['PROCESS_VM_READ', 'PROCESS_QUERY_INFORMATION', 'SYNCHRONIZE']):
        raise ValueError('Observer build receipt is incomplete or unsupported')
    # A changed reader must be rebuilt/reviewed, not silently run with a stale
    # executable and stale claims about what it observes.
    for name in ('native/src/read_only_probe.cpp', 'native/src/dsr_snapshot.cpp', 'native/include/dsr_snapshot.hpp'):
        path = workspace / name
        if (path.is_symlink() or not is_within(path, workspace) or
                hashlib.sha256(path.read_bytes()).hexdigest() != report.get('source_sha256', {}).get(name)):
            raise ValueError('Observer source no longer matches its build receipt')
    return record


def checked_bytes(path: Path, root: Path, record: dict) -> bytes:
    if path.is_symlink() or not is_within(path, root):
        raise ValueError('Observer executable escapes its private folder')
    if path.stat().st_size != record['bytes']:
        raise ValueError('Observer executable size changed')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Observer executable hash changed')
    return data


def staged_path(bottle: Path, record: dict) -> Path:
    digest = record.get('sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Invalid observer version digest')
    path = bottle / 'drive_c/Tools/DSR-MW2/observer-v3' / digest / PROBE
    if path.is_symlink() or not is_within(path, bottle) or path.resolve() != path:
        raise ValueError('Observer destination escapes the private profile')
    return path


def stage(workspace: Path, bottle: Path) -> dict:
    """Copy our compiled observer only; never execute it or access save bytes."""
    blockers = guard(bottle)
    if blockers:
        raise ValueError('; '.join(blockers))
    lock_path = bottle / '.dsr-mw2-session.lock'
    if lock_path.is_symlink() or not is_within(lock_path, bottle):
        raise ValueError('Private session lock escapes profile')
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if bottle_processes(bottle):
            raise ValueError('Private session is active; observer installation deferred')
        record = specification(workspace)
        data = checked_bytes(workspace / 'tooling-local/native-observer' / PROBE, workspace, record)
        target = staged_path(bottle, record)
        if target.exists():
            checked_bytes(target, bottle, record)  # Preserve any different file.
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, data)
            checked_bytes(target, bottle, record)
    return {'staged': True, 'file': PROBE, 'sha256': record['sha256'],
            'probe_executed': False, 'game_launched': False, 'runtime_verified': False}


def start(mode: str, game_pids: list[int], workspace: Path, bottle: Path, network_prefix: list[str],
          children: list[subprocess.Popen]) -> dict:
    """Called by the existing owner launch only after exactly one game appears."""
    if mode not in {'m9', 'm9-test'} or len(game_pids) != 1:
        return {'status': 'read_only_diagnostics_skipped'}
    try:
        if not network_prefix or network_prefix[0] != '/usr/bin/sandbox-exec':
            raise ValueError('Offline observer network wrapper is missing')
        if guard(bottle) or inspect_banks(bottle).get('active') != ('validation' if mode == 'm9-test' else 'm9'):
            raise ValueError('Private offline M9 profile is not ready for diagnostics')
        if mode == 'm9-test':
            from .validation_session import verify
            verify(bottle, active=True)
        if game_pids[0] not in bottle_processes(bottle):
            raise ValueError('Observed game no longer belongs to the private profile')
        record = specification(workspace)
        checked_bytes(staged_path(bottle, record), bottle, record)
        folder = workspace / 'tooling-local/launch/observations'
        if folder.is_symlink() or not is_within(folder, workspace):
            raise ValueError('Observation output folder escapes this checkout')
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f'm9-{time.time_ns()}.jsonl'
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as log:
            child = subprocess.Popen([*network_prefix, *command(windows_probe(record), '120')],
                cwd=staged_path(bottle, record).parent, env=environment(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        children.append(child)
        return {'status': 'read_only_diagnostics_started', 'observer_pid': child.pid,
                'log': str(output.relative_to(workspace)), 'sha256': record['sha256'],
                'max_wait_seconds': 300, 'capture_seconds': 120, 'runtime_verified': False}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Optional diagnostics must never prevent the owner from playing or
        # retry themselves, start another game, or change the active session.
        return {'status': 'read_only_diagnostics_unavailable', 'reason': str(exc)}
