"""Route gun requests out of the native crossbow states in the existing local owner package."""
import copy
import json
from datetime import datetime, timezone
from dsr_mw2.action_priority import NATIVE_CROSSBOW_STATES, route_native_crossbow
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
    if not route_native_crossbow(esd.state_machines[1]):
        print('Native crossbow request routing already present');return
    encoded=bytes(esd)
    checked=ChrESD.from_bytes(encoded)
    # Undo exactly the prepended dispatch in the decoded result; every machine,
    # state, command, predicate and destination must then match the original.
    for number in NATIVE_CROSSBOW_STATES:
        conditions=checked.state_machines[1][number].conditions
        if [c.next_state_id for c in conditions[:3]]!=[9000,9001,9002]:
            raise ValueError('Crossbow routing round-trip failed')
        del conditions[:3]
    if checked.state_machines!=original:
        raise ValueError('Unrelated native action data changed')
    backup=WORKSPACE/'tooling-local/crossbow-routing-before'
    backup.mkdir(exist_ok=True)
    atomic_write(backup/(report['files']['chr/c0000.esd.dcx']+'.dcx'),before)
    atomic_write(backup/(sha(OUT/'manifest.json')+'.json'),(OUT/'manifest.json').read_bytes())
    atomic_write(path,encoded)
    report['files']['chr/c0000.esd.dcx']=sha(path)
    report['native_crossbow_request_states']=list(NATIVE_CROSSBOW_STATES)
    atomic_write(OUT/'manifest.json',(json.dumps(report,indent=2)+'\n').encode())
    manifest()
    proof={'at':datetime.now(timezone.utc).isoformat(),'states':list(NATIVE_CROSSBOW_STATES),
           'prepended':[9000,9001,9002],'only_prepended_dispatch_changed':True,
           'esd_sha256':sha(path),'game_launched':False,'runtime_verified':False}
    atomic_write(WORKSPACE/'evidence/crossbow-request-routing.json',(json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
