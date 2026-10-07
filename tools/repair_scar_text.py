"""Correct the SCAR-H description's keyboard toggle (G is DSR's gesture menu; B is used)."""
import json
from dsr_mw2.action_trial import OUT, ARMORY_PATHS, manifest, receipt, sha
from dsr_mw2.install_private import atomic_write
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import configure

OLD, NEW = 'D-pad Up (or G) toggles', 'D-pad Up (or B) toggles'


def main():
    if bottle_processes(bottle_path()) or receipt(bottle_path()).exists():
        raise ValueError('Close the private session and restore its package first')
    report = manifest(); configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.text.fmg import FMG
    path = OUT / ARMORY_PATHS[3]; before = path.read_bytes(); messages = Binder.from_bytes(before); changed = 0
    for e in messages.entries:
        f = FMG.from_bytes(e.get_uncompressed_data()); text = f.entries.get(9300000)
        if text and OLD in text:
            entries = dict(f.entries); f.entries[9300000] = text.replace(OLD, NEW)
            if FMG.from_bytes(bytes(f)).entries != {**entries, 9300000: text.replace(OLD, NEW)}:
                raise ValueError('Localized text roundtrip changed')
            e.set_uncompressed_data(bytes(f)); changed += 1
    if not changed:
        print('SCAR-H text already corrected'); return
    atomic_write(path, bytes(messages)); report['files'][ARMORY_PATHS[3]] = sha(path)
    atomic_write(OUT / 'manifest.json', (json.dumps(report, indent=2) + '\n').encode()); manifest()
    print(json.dumps({'changed_entries': changed, 'item_msg_sha256': sha(path)}))


if __name__ == '__main__':
    main()
