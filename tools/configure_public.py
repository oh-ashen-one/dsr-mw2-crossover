"""Initialize local source-work directories; no games, installers or profile writes."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mw2-root', type=Path, required=True)
    p.add_argument('--crossover-app', type=Path, default=Path('/Applications/CrossOver.app'))
    p.add_argument('--gpu-dir', type=Path, help='Existing shared coordinator, if your machine has one')
    p.add_argument('--allow-offline-conversion', action='store_true')
    p.add_argument('--allow-owner-test', action='store_true')
    args = p.parse_args()
    config = ROOT / 'local-config.json'
    if config.exists() or config.is_symlink():
        raise ValueError('Preserving existing local-config.json; review it before changing settings')
    mw2 = args.mw2_root.expanduser().resolve()
    cx = args.crossover_app.expanduser().resolve()
    if not (mw2 / 'main').is_dir() or not (mw2 / 'zone/english/common_mp.ff').is_file():
        raise ValueError('MW2 root must contain main/ and zone/english/common_mp.ff')
    if not (cx / 'Contents/SharedSupport/CrossOver/bin/wine').is_file():
        raise ValueError('Installed CrossOver application not found')
    for name in ('converted', 'evidence', 'profiles', 'retail', 'tooling-local', 'mod'):
        directory = ROOT / name
        if directory.is_symlink():
            raise ValueError('Private output directory is redirected: ' + name)
        directory.mkdir(exist_ok=True)
    gpu = args.gpu_dir.expanduser().resolve() if args.gpu_dir else ROOT / 'tooling-local/gpu'
    if args.gpu_dir:
        if not (gpu / 'bin/gpu_slot.py').is_file() or not (gpu / 'locks/perf.lock').is_file():
            raise ValueError('Existing coordinator must provide bin/gpu_slot.py and locks/perf.lock')
    else:
        if gpu.exists():
            raise ValueError('Preserving existing GPU coordinator; use --gpu-dir')
        (gpu / 'bin').mkdir(parents=True)
        (gpu / 'locks').mkdir()
        (gpu / 'locks/perf.lock').touch(exist_ok=False)
        shutil.copy2(ROOT / 'tools/gpu_slot.py', gpu / 'bin/gpu_slot.py')
    data = {'version': 1, 'mw2_root': str(mw2), 'crossover_app': str(cx),
            'gpu_dir': str(gpu), 'allow_offline_conversion': args.allow_offline_conversion,
            'allow_owner_test': args.allow_owner_test, 'allow_agent_gameplay': False}
    with config.open('x') as output:
        json.dump(data, output, indent=2)
        output.write('\n')
    print('Local configuration created. No profile created, assets extracted or game launched.')
    print('Continue with docs/SETUP.md. Do not publish local-config.json.')


if __name__ == '__main__':
    main()
