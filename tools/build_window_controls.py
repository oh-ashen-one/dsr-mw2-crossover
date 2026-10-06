"""Compile original window-only helper; do not run Wine or launch a game."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'native/tools/window_controls.cpp'


def main():
    out = ROOT / 'tooling-local/window-controls'
    out.mkdir(parents=True, exist_ok=True)
    binary = out / 'dsr_window_controls.exe'
    compiler = shutil.which('x86_64-w64-mingw32-g++')
    inspector = shutil.which('x86_64-w64-mingw32-objdump')
    if not compiler or not inspector:
        raise RuntimeError('Existing MinGW C++ compiler and objdump are required')
    subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion',
                    '-static', '-fno-exceptions', '-fno-rtti', '-Wl,--no-insert-timestamp',
                    str(ROOT / SOURCE), '-luser32', '-o', str(binary)], check=True)
    imports = subprocess.check_output([inspector, '-p', str(binary)], text=True)
    for forbidden in ('ReadProcessMemory', 'WriteProcessMemory', 'CreateRemoteThread', 'VirtualAllocEx',
                      'SendInput', 'keybd_event', 'mouse_event', 'SetCursorPos', 'ClipCursor',
                      'CreateProcess', 'ShellExecute', 'SetWindowsHookEx', 'libwinpthread-1.dll'):
        if forbidden in imports:
            raise ValueError('Unexpected input/injection/launch import: ' + forbidden)
    report = {'source': SOURCE, 'source_sha256': hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest(),
              'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bytes': binary.stat().st_size,
              'file': binary.name, 'compiled': True, 'game_launched': False, 'runtime_verified': False}
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
