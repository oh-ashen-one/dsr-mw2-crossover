"""Compile and run the synthetic-memory ESD state probe tests on macOS. No game, Wine or retail data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tooling-local/esd-probe'
SOURCES = ['native/include/esd_state_probe.hpp', 'native/include/esd_state_table.hpp', 'native/tests/esd_state_probe_test.cpp']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    test = OUT / 'esd-state-probe-test'
    subprocess.run(['/usr/bin/clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-g',
                    '-fsanitize=address,undefined', '-I', str(ROOT / 'native/include'),
                    str(ROOT / 'native/tests/esd_state_probe_test.cpp'), '-o', str(test)], check=True)
    result = subprocess.run([str(test)], check=True, capture_output=True, text=True).stdout.strip()
    table = (ROOT / 'native/include/esd_state_table.hpp').read_text().splitlines()[1]
    report = {'at': datetime.now(timezone.utc).isoformat(), 'result': result,
              'sanitizers': ['address', 'undefined'], 'table_source': table.removeprefix('// Source: '),
              'sources': {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in SOURCES},
              'memory_writes': False, 'game_launched': False, 'runtime_verified': False}
    (ROOT / 'evidence/esd-state-probe.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
