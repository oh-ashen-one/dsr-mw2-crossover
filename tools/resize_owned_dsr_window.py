"""Resize this task's one DSR window; no gameplay input or game-memory access."""
import argparse
import json
import subprocess

from dsr_mw2.install_private import atomic_write
from dsr_mw2.launch import game_processes, network_wrapper
from dsr_mw2.profile import command, environment, guard
from dsr_mw2.runtime_paths import WORKSPACE, bottle_path
from dsr_mw2.window_controls import specification, staged_path, digest, EXE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('height',choices=('720','900','1080'))
    args=parser.parse_args();bottle=bottle_path();pids=game_processes()
    if guard(bottle) or len(pids)!=1:raise RuntimeError('Expected one isolated DSR game')
    game=bottle/'drive_c/Games/DSR-MW2'
    alias=bottle/'drive_c/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED'
    if not alias.is_symlink() or alias.resolve()!=game:
        raise RuntimeError('Private game alias changed')
    record=specification(WORKSPACE);target=staged_path(bottle,record)
    if target.exists() and digest(target.read_bytes())!=record['sha256']:
        raise RuntimeError('Window helper changed')
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(target,(WORKSPACE/'tooling-local/window-controls'/EXE).read_bytes())
    if game_processes()!=pids:raise RuntimeError('Game ownership changed')
    windows_exe='C:\\Tools\\DSR-MW2\\window-controls\\'+record['sha256']+'\\'+EXE
    result=subprocess.run([*network_wrapper('m9-test'),*command(windows_exe,'--size-'+args.height)],
        env=environment(),capture_output=True,text=True,timeout=20)
    print(json.dumps({'owner_game_pid':pids[0],'height_requested':int(args.height),
        'exit_code':result.returncode,'result':result.stdout.strip(),'gameplay_input':False}))
    if result.returncode:raise RuntimeError('Window resize request failed')


if __name__=='__main__':main()
