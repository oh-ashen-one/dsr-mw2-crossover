"""One owner-operated, reversible test of the MW2 handling/viewmodel package.

--prepare installs/checks/restores offline. Only the default owner-invoked path
can launch DSR. No game input, save editing, shared Steam changes or GPU bypass.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from . import action_trial, mpeg_audio_trial, owner_diagnostics, controller_setup, window_controls, steam_controller_focus
from . import steam_controller_ownership
from .install_private import WORKSPACE, atomic_write
from .profile import guard
from .runtime_paths import bottle_path
from .process_ownership import bottle_processes
from .validation_session import verify

GATES = {
    'DSR_MW2_NATIVE_INPUT_TRIAL':'validation-v1', 'DSR_MW2_FRAME_TRIAL':'observe-v3',
    'DSR_MW2_GUN_TRIAL':'play-v1', 'DSR_MW2_AIM_TRIAL':'hold-v1',
    'DSR_MW2_CAMERA_TRIAL':'frame-v1', 'DSR_MW2_HUD_TRIAL':'reticle-v1',
    'DSR_MW2_AUDIO_TRIAL':'mono-mpeg-v1', 'DSR_MW2_LOADOUT_TRIAL':'bonfire-v1',
    'DSR_MW2_SESSION_TRIAL':'owner-2h-test-v1', 'DSR_MW2_VIEWMODEL_TRIAL':'source-vm-v1',
}
MARKER = '.dsr-mw2-owner-testing.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def viewmodel_spec():
    root = WORKSPACE/'converted/mw2-2009/viewmodel-v1'
    report = json.loads((root/'manifest.json').read_text())
    source = root/'m9.dsrvm'
    if source.is_symlink() or source.resolve()!=source or source.stat().st_size!=report['bytes'] or sha(source)!=report['sha256']:
        raise ValueError('Local MW2 viewmodel packet changed')
    if report['file']!='converted/mw2-2009/viewmodel-v1/m9.dsrvm' or report['bones']!=76:
        raise ValueError('Unsupported viewmodel packet')
    return source, report


def viewmodel_check():
    source, report = viewmodel_spec()
    target=bottle_path()/'drive_c/Tools/DSR-MW2/viewmodel-v1/m9.dsrvm'
    if target.is_symlink() or target.resolve()!=target or sha(target)!=report['sha256']:
        raise ValueError('Staged viewmodel differs from its checked local build')
    for source,target_name,digest in additional_assets():
        target=bottle_path()/'drive_c/Tools/DSR-MW2/viewmodel-v1'/target_name
        if target.is_symlink() or target.resolve()!=target or sha(target)!=digest:
            raise ValueError('Staged gun asset differs: '+target_name)
    return report['sha256']


def additional_assets():
    root=WORKSPACE/'converted/mw2-2009/intervention-viewmodel-v1'
    report=json.loads((root/'manifest.json').read_text())
    if report['bones']!=90 or report['scope_texture']!=8 or len(report['clips'])!=9:
        raise ValueError('Unsupported Intervention packet')
    assets=[(root/'intervention.dsrvm','intervention.dsrvm',report['sha256'])]
    sound=json.loads((WORKSPACE/'converted/mw2-2009/shot-audio/manifest.json').read_text())
    if set(sound['files'])!={'m9-shot.wav','intervention-shot.wav'}:raise ValueError('Unexpected gun sound set')
    assets += [(WORKSPACE/'converted/mw2-2009/shot-audio'/name,name,h) for name,h in sound['files'].items()]
    for source,name,h in assets:
        if source.is_symlink() or source.resolve()!=source or sha(source)!=h:
            raise ValueError('Local gun asset changed: '+name)
    return assets


@contextmanager
def gates():
    before = {name: os.environ.get(name) for name in GATES}
    os.environ.update(GATES)
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:os.environ.pop(name, None)
            else:os.environ[name]=value


def stage():
    from tools.native_input_trial import expected
    bottle=bottle_path()
    if guard(bottle) or bottle_processes(bottle):raise ValueError('Private profile must be closed before preparing the owner test')
    before=verify(bottle);expected();action_trial.manifest()
    controller=controller_setup.configure(bottle)
    steam_focus=steam_controller_focus.configure(bottle)
    steam_focus['device_ownership']=steam_controller_ownership.configure(bottle)
    diagnostic=owner_diagnostics.stage(WORKSPACE,bottle)
    windows=window_controls.stage(WORKSPACE,bottle)
    source, report=viewmodel_spec()
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if guard(bottle) or bottle_processes(bottle):raise ValueError('Private profile changed during preparation')
        target=bottle/'drive_c/Tools/DSR-MW2/viewmodel-v1/m9.dsrvm'
        if target.is_symlink() or target.resolve()!=target:raise ValueError('Redirected viewmodel destination')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)!=report['sha256']:
            # Preserve the prior local packet before replacing our private copy.
            previous=target.with_name('preserved-'+sha(target)+'.dsrvm')
            if previous.exists() and sha(previous)!=sha(target):raise ValueError('Existing preserved packet differs')
            if not previous.exists():atomic_write(previous,target.read_bytes())
        if not target.exists() or sha(target)!=report['sha256']:atomic_write(target,source.read_bytes())
        for source,name,h in additional_assets():
            target=bottle/'drive_c/Tools/DSR-MW2/viewmodel-v1'/name
            if target.is_symlink() or target.resolve()!=target:raise ValueError('Redirected gun asset destination')
            if target.exists() and sha(target)!=h:
                previous=target.with_name('preserved-'+sha(target)+'-'+name)
                if previous.exists() and sha(previous)!=sha(target):raise ValueError('Preserved gun asset differs')
                if not previous.exists():atomic_write(previous,target.read_bytes())
            if not target.exists() or sha(target)!=h:atomic_write(target,source.read_bytes())
        viewmodel_check()
    return {'owner_saves':before,'controller':controller,'steam_focus':steam_focus,'diagnostic':diagnostic,'windows':windows,'viewmodel_sha256':report['sha256']}


@contextmanager
def package():
    """Roll back this transaction's installs; never repair an unrelated session."""
    from tools.native_input_trial import mutate as native_mutate
    bottle=bottle_path();completed=[]
    try:
        action_trial.mutate('install');completed.append('actions')
        mpeg_audio_trial.mutate('install');completed.append('audio')
        native_mutate('install');completed.append('native')
        yield
    finally:
        if completed and bottle_processes(bottle):
            raise RuntimeError('Private processes are still running; preserving the test files and recovery receipts until they close')
        for item in reversed(completed):
            if item=='native':native_mutate('restore')
            elif item=='audio':mpeg_audio_trial.mutate('restore')
            else:action_trial.mutate('restore')
        verify(bottle)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true',help='Offline staging and reversible install checks only; never launch')
    args=parser.parse_args();bottle=bottle_path()
    with (bottle/'.dsr-mw2-owner-test.lock').open('a+') as owner_lock:
        fcntl.flock(owner_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker=bottle/MARKER
        if marker.exists() or marker.is_symlink():raise ValueError('A prior owner-test receipt is present; preserve it for task-local recovery')
        staged=stage()
        if args.prepare:
            with gates(),package():
                from .launch import preflight
                check=preflight('m9-test')
                resource=[s for s in check['blockers'] if s.startswith(('Another game or renderer is active','The Studio coordinator has paused game launches'))]
                setup=[s for s in check['blockers'] if s not in resource]
                if setup:raise ValueError('; '.join(setup))
            # Record readiness only after the complete rollback and preservation
            # check have succeeded, not while temporary trial files are active.
            from .native_runtime import RUNTIME_HASHES
            baseline_sha=sha(bottle/'drive_c/Games/DSR-MW2/xinput1_3.dll')
            if baseline_sha!=RUNTIME_HASHES['xinput1_3.dll']:raise ValueError('Controller baseline did not restore')
            if any((bottle/name).exists() for name in ('.dsr-mw2-action-trial.json',mpeg_audio_trial.RECEIPT)):
                raise ValueError('Temporary trial receipt remained after preparation')
            report={'at':datetime.now(timezone.utc).isoformat(),**staged,'owner_saves':verify(bottle),
                    'offline_package_check':True,'private_baseline_restored':True,
                    'native_adapter_sha256':json.loads((WORKSPACE/'evidence/native-input-build.json').read_text())['sha256'],
                    'retail_xinput_restored_sha256':baseline_sha,'launch_resource_blockers':resource,
                    'game_launched':False,'runtime_verified':False}
            (WORKSPACE/'evidence/owner-test-preparation.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2));return 0
        with gates(),package():
            from .launch import preflight
            check=preflight('m9-test')
            # Resource availability is rechecked on owner click. Offline setup
            # doesn't take a slot or disturb somebody else's running renderer.
            resource=[s for s in check['blockers'] if s.startswith(('Another game or renderer is active','The Studio coordinator has paused game launches'))]
            setup=[s for s in check['blockers'] if s not in resource]
            if setup:raise ValueError('; '.join(setup))
            if resource:raise ValueError('; '.join(resource))
            atomic_write(marker,(json.dumps({'owner_only':True,'gameplay_input_authorized':False,
                'started_at':datetime.now(timezone.utc).isoformat(),'viewmodel_sha256':staged['viewmodel_sha256']})+'\n').encode())
            print('DSR × MW2 — owner test candidate',flush=True)
            print('Create or load your private test character. Your earlier saves stay separate.',flush=True)
            print('M9: hold L2 / right mouse to aim, R2 or R1 / left mouse to fire, Square while aiming / R to reload.',flush=True)
            print('Empty trigger starts a reload; release, then press again after the reload to fire.',flush=True)
            print('Asylum bonfire → MW2 armory → MW2 Intervention (1 soul). Equip in the right hand; D-pad Right switches equipped guns.',flush=True)
            print('Window: Control+Option+1/2/3 for 720p/900p/1080p; Control+Option+M minimizes to free the mouse. Command+Tab also switches away.',flush=True)
            print('New first-person rendering and physical controller response still need your test. This session has a two-hour handling limit.',flush=True)
            print('Quit normally when done; this window restores the private baseline. You control all play.',flush=True)
            log=WORKSPACE/'tooling-local/launch/owner-test.log';log.parent.mkdir(exist_ok=True)
            try:
                with log.open('a') as stream:
                    from .owner_launch import progress_message
                    with subprocess.Popen([sys.executable,'-B','-m','dsr_mw2.launch','--mode','m9-test'],cwd=WORKSPACE,
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1) as child:
                        for line in child.stdout:
                            stream.write(line);stream.flush()
                            message=progress_message(line)
                            if message:print(message,flush=True)
                        result=child.wait()
            finally:
                if not bottle_processes(bottle):
                    archive=WORKSPACE/'tooling-local/launch'/('owner-session-'+sha(marker)+'.json')
                    atomic_write(archive,marker.read_bytes());marker.unlink()
            return result


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,RuntimeError) as exc:
        print('Owner test stopped: '+str(exc),file=sys.stderr)
        raise SystemExit(75)
