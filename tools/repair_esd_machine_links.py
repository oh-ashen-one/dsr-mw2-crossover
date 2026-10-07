"""Relink the packaged player ESD so each machine's transitions stay in that machine.

The earlier Soulstruct writes linked machine 0 (damage, falls, death) into machine
1's same-numbered states; see dsr_mw2/esd_links.py. Reading the file still yields
the intended state IDs, so a re-write with per-machine links restores the native
master machine without changing any state, condition or command.
"""
import json
from datetime import datetime, timezone
from dsr_mw2.action_trial import OUT, manifest, receipt, sha
from dsr_mw2.install_private import atomic_write
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import configure, WORKSPACE

PATH = 'chr/c0000.esd.dcx'


def signature(esd):
    def commands(items):
        return [(c.bank, c.index, [bytes(a) for a in c.args]) for c in items]

    def condition(c):
        return (c.next_state_id, bytes(c.test_ezl), commands(c.pass_commands), [condition(s) for s in c.subconditions])
    return {m: [(sid, commands(s.enter_commands), commands(s.exit_commands), commands(s.ongoing_commands),
                 [condition(c) for c in s.conditions]) for sid, s in states.items()]
            for m, states in esd.state_machines.items()}


def main():
    bottle = bottle_path()
    if bottle_processes(bottle) or receipt(bottle).exists():
        raise ValueError('Close the private session and restore its package first')
    report = manifest()
    configure()
    from soulstruct.darksouls1r.ezstate.esd import ChrESD
    from soulstruct.dcx.core import decompress
    from dsr_mw2 import esd_links
    path = OUT / PATH
    before = path.read_bytes()
    bad_before = esd_links.cross_machine_links(decompress(before)[0], ChrESD)
    if not bad_before:
        print('Player ESD links already per machine'); return
    esd = ChrESD.from_bytes(before)
    esd_links.install()
    encoded = bytes(esd)
    checked = ChrESD.from_bytes(encoded)
    if signature(checked) != signature(esd):
        raise ValueError('Relinked ESD changed a state, condition or command')
    if esd_links.cross_machine_links(decompress(encoded)[0], ChrESD):
        raise ValueError('Relinked ESD still crosses machines')
    backup = WORKSPACE / 'tooling-local/esd-links-before'; backup.mkdir(exist_ok=True)
    atomic_write(backup / (sha(path) + '.dcx'), before)
    atomic_write(backup / (sha(OUT / 'manifest.json') + '.json'), (OUT / 'manifest.json').read_bytes())
    atomic_write(path, encoded)
    report['files'][PATH] = sha(path)
    report['esd_machine_links'] = 'per-machine (dsr_mw2/esd_links.py)'
    atomic_write(OUT / 'manifest.json', (json.dumps(report, indent=2) + '\n').encode())
    manifest()
    proof = {'at': datetime.now(timezone.utc).isoformat(), 'cross_machine_links_before': len(bad_before),
             'cross_machine_links_after': 0, 'states_conditions_commands_unchanged': True,
             'esd_sha256': sha(path), 'game_launched': False, 'runtime_verified': False}
    atomic_write(WORKSPACE / 'evidence/esd-machine-links.json', (json.dumps(proof, indent=2) + '\n').encode())
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
