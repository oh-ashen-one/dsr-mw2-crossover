"""Read-only public checkout prerequisites. Never creates or opens a profile."""
import hashlib
import json
from pathlib import Path
import platform
import shutil

from .local_config import ROOT, path, read
from .runtime_paths import bottle_path

EXE_SHA = 'a45aaa36dd2f6cc151670a639ea5547043cf38ea79ff4178b963c6ed71f98d7b'


def check():
    config = read()
    bottle = bottle_path()
    missing = []
    if not config:
        missing.append('local-config.json; run tools/configure_public.py --help')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        missing.append('Current runtime launcher requires Apple Silicon macOS; source tests remain available')
    for program in ('clang++', 'x86_64-w64-mingw32-g++', 'x86_64-w64-mingw32-objdump'):
        if not shutil.which(program):
            missing.append('Build tool: ' + program)
    if not (path('crossover_app', '/Applications/CrossOver.app') / 'Contents/SharedSupport/CrossOver/bin/wine').is_file():
        missing.append('Configured CrossOver application')
    for name in ('drive_c/Games/Dark Souls Remastered', 'drive_c/Games/DSR-MW2'):
        exe = bottle / name / 'DarkSoulsRemastered.exe'
        if not exe.is_file() or exe.is_symlink():
            missing.append('Private game executable: ' + name)
        elif hashlib.sha256(exe.read_bytes()).hexdigest() != EXE_SHA:
            missing.append('Unsupported executable revision: ' + name)
    required = ('converted/packages/winding-v2/m9-sidearm/manifest.json',
                'converted/mw2-2009/viewmodel-v1/manifest.json',
                'evidence/native-input-build.json', 'evidence/owner-probe-build.json')
    missing.extend('Local build output: ' + name for name in required if not (ROOT / name).is_file())
    return {'source_release': '0.1.0', 'missing': missing,
            'prerequisites_present': not missing, 'runtime_verified': False,
            'game_launched': False,
            'next': 'docs/SETUP.md; prerequisites alone do not qualify gameplay'}


def main():
    report = check()
    print(json.dumps(report, indent=2))
    return 2 if report['missing'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
