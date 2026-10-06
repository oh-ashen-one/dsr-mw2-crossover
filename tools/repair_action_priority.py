"""Repair only idle request priority in the existing local owner package."""
import copy
import json
from datetime import datetime, timezone
from dsr_mw2.action_priority import prioritize_requests
from dsr_mw2.action_trial import OUT, manifest, receipt, sha
from dsr_mw2.install_private import atomic_write
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import configure, WORKSPACE


def main():
    bottle=bottle_path()
    if bottle_processes(bottle) or receipt(bottle).exists():
        raise ValueError('Close the private session and restore its package first')
    report=manifest()
    configure()
    from soulstruct.darksouls1r.ezstate.esd import ChrESD
    path=OUT/'chr/c0000.esd.dcx'
    before=path.read_bytes()
    esd=ChrESD.from_bytes(before)
    original=copy.deepcopy(esd.state_machines)
    changed=prioritize_requests(esd.state_machines[1][0].conditions)
    if not changed:
        print('Action priority already repaired');return
    encoded=bytes(esd)
    checked=ChrESD.from_bytes(encoded)
    # Undo the sole permutation in the decoded result. Every machine, state,
    # command, predicate and destination must then match the original.
    conditions=checked.state_machines[1][0].conditions
    if [c.next_state_id for c in conditions[:4]]!=[9000,9001,9002,9003]:
        raise ValueError('Action priority round-trip failed')
    conditions[:4]=conditions[3:4]+conditions[:3]
    if checked.state_machines!=original:
        raise ValueError('Unrelated native action data changed')
    backup=WORKSPACE/'tooling-local/action-priority-before'
    backup.mkdir(exist_ok=True)
    atomic_write(backup/(report['files']['chr/c0000.esd.dcx']+'.dcx'),before)
    atomic_write(backup/(sha(OUT/'manifest.json')+'.json'),(OUT/'manifest.json').read_bytes())
    atomic_write(path,encoded)
    report['files']['chr/c0000.esd.dcx']=sha(path)
    report['idle_request_priority']=[9000,9001,9002,9003]
    atomic_write(OUT/'manifest.json',(json.dumps(report,indent=2)+'\n').encode())
    manifest()
    proof={'at':datetime.now(timezone.utc).isoformat(),'only_idle_condition_order_changed':True,
           'before':[9003,9000,9001,9002],'after':[9000,9001,9002,9003],
           'esd_sha256':sha(path),'game_launched':False,'runtime_verified':False}
    atomic_write(WORKSPACE/'evidence/action-priority-repair.json',(json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
