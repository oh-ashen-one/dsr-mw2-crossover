"""Keep the observed DualSense on Wine's XInput route in this private profile.

Steam's installed client implements controller_blacklist as VID/PID pairs.
The owner-session log identifies Sony 054c:0ce6. No other device is excluded.
"""
import fcntl
import json
import re
from pathlib import Path

from .install_private import atomic_write
from .profile import guard
from .process_ownership import bottle_processes
from .steam_controller_focus import tokens

PARENT = ('installconfigstore',)
DEVICE = '54c/ce6'


def exclude_dualsense(text):
    ts=tokens(text); stack=[]; seen=set(); target=None; close=None; i=0
    while i<len(ts):
        value,start,end=ts[i]
        if value=='}':
            if not stack:raise ValueError('Unbalanced Steam configuration')
            if tuple(stack)==PARENT:close=start
            stack.pop();i+=1;continue
        if not value.startswith('"') or i+1>=len(ts):raise ValueError('Invalid Steam pair')
        key=value[1:-1].lower();loc=(*stack,key)
        if loc in seen:raise ValueError('Duplicate Steam configuration key')
        seen.add(loc); entry=ts[i+1]
        if entry[0]=='{':stack.append(key)
        elif not entry[0].startswith('"'):raise ValueError('Invalid Steam value')
        if loc==(*PARENT,'controller_blacklist'):target=entry
        i+=2
    if stack or close is None:raise ValueError('Expected private Steam configuration block')
    previous=None
    if target:
        if not target[0].startswith('"'):raise ValueError('Controller exclusion must be a scalar')
        previous=target[0][1:-1]
        if not re.fullmatch(r'(?:[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4})(?:,[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4})*|',previous):
            raise ValueError('Unexpected controller exclusion syntax')
        pairs=previous.split(',') if previous else []
        if any(tuple(int(v,16) for v in pair.split('/'))==(0x54c,0xce6) for pair in pairs):return text,previous
        value=','.join([*pairs,DEVICE]);_,start,end=target
        return text[:start]+'"'+value+'"'+text[end:],previous
    return text[:close]+'\t"controller_blacklist"\t\t"'+DEVICE+'"\n\t\t\t'+text[close:],previous


def configure(bottle: Path):
    if guard(bottle):raise ValueError('Private profile guard failed')
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if bottle_processes(bottle):raise ValueError('Private Steam must be closed')
        path=bottle/'drive_c/Program Files (x86)/Steam/config/config.vdf'
        if path.is_symlink() or not path.resolve().is_relative_to(bottle.resolve()):raise ValueError('Configuration redirect')
        raw=path.read_bytes();text,previous=exclude_dualsense(raw.decode('utf-8'));changed=text.encode('utf-8')
        report={'changed':changed!=raw,'excluded_steam_device':DEVICE,'input_route':'CrossOver XInput',
                'scope':'task private Steam only','configuration_path':'InstallConfigStore/controller_blacklist','runtime_verified':False}
        if changed!=raw:
            receipt=bottle/'.dsr-mw2-controller-ownership.json'
            if receipt.exists():raise ValueError('Existing ownership receipt requires review')
            if path.read_bytes()!=raw:raise ValueError('Steam configuration changed concurrently')
            atomic_write(receipt,(json.dumps({'previous':previous,**report},indent=2)+'\n').encode())
            atomic_write(path,changed)
        return report
