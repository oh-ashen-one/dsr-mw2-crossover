"""Stop the isolated Steam client's overlay/guide button from taking input.

Setting paths come from the installed Steam UI's settings descriptors:
enable_overlay -> system\\EnableGameOverlay, and
controller_guide_button_focus_steam -> Controller_CheckGuideButton.
No account tokens are copied, parsed as settings, printed or written elsewhere.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re

from .install_private import atomic_write
from .profile import guard
from .process_ownership import bottle_processes

TOKEN = re.compile(r'\s+|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]')
SETTINGS = (("UserLocalConfigStore", "system", "EnableGameOverlay"),
            ("UserLocalConfigStore", "Controller_CheckGuideButton"))


def tokens(text):
    result=[];at=0
    for m in TOKEN.finditer(text):
        if m.start()!=at:raise ValueError('Unsupported private Steam VDF syntax')
        at=m.end();value=m[0]
        if value.isspace() or value.startswith('//'):continue
        result.append((value,m.start(),m.end()))
    if at!=len(text):raise ValueError('Truncated private Steam VDF')
    return result


def set_disabled(text, path):
    """Change exactly one boolean; preserve unrelated bytes including secrets."""
    ts=tokens(text);entries={};closes={};stack=[];i=0
    while i<len(ts):
        value,start,end=ts[i]
        if value=='}':
            if not stack:raise ValueError('Unbalanced private Steam VDF')
            closes[tuple(stack)]=start;stack.pop();i+=1;continue
        if not value.startswith('"') or i+1>=len(ts):raise ValueError('Invalid private Steam VDF pair')
        key=value[1:-1].lower();loc=(*stack,key)
        if loc in entries:raise ValueError('Duplicate private Steam VDF key')
        target=ts[i+1];entries[loc]=target
        if target[0]=='{':stack.append(key)
        elif not target[0].startswith('"'):raise ValueError('Invalid private Steam VDF value')
        i+=2
    if stack:raise ValueError('Unclosed private Steam VDF block')
    loc=tuple(x.lower() for x in path)
    if loc in entries:
        value,start,end=entries[loc]
        if value not in ('"0"','"1"'):raise ValueError('Unexpected private controller setting')
        return text[:start]+'"0"'+text[end:],value[1:-1]
    if loc[:-1] not in closes:raise ValueError('Expected private controller settings block is absent')
    at=closes[loc[:-1]]
    return text[:at]+'\t"'+path[-1]+'"\t\t"0"\n'+('\t'*(len(path)-2))+text[at:],None


def configure(bottle: Path):
    if guard(bottle):raise ValueError('Private controller profile guard failed')
    with (bottle/'.dsr-mw2-session.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if bottle_processes(bottle):raise ValueError('Private Steam is active; preserve settings')
        matches=list((bottle/'drive_c/Program Files (x86)/Steam/userdata').glob('*/config/localconfig.vdf'))
        if len(matches)!=1:raise ValueError('Expected one private Steam local configuration')
        path=matches[0]
        if path.is_symlink() or not path.resolve().is_relative_to(bottle.resolve()):
            raise ValueError('Controller setting escapes private profile')
        raw=path.read_bytes();text=raw.decode('utf-8');previous={}
        for setting in SETTINGS:
            text,old=set_disabled(text,setting);previous['/'.join(setting[1:])]=old
        changed=text.encode('utf-8')
        report={'changed':changed!=raw,'overlay_enabled':False,'guide_button_focuses_steam':False,
                'scope':'isolated task Steam client only','runtime_verified':False}
        if changed!=raw:
            if path.read_bytes()!=raw:raise ValueError('Private Steam configuration changed concurrently')
            # Receipt contains just the two previous UI booleans, never the
            # account-bearing configuration or identifiers.
            receipt=bottle/('.dsr-controller-focus-'+hashlib.sha256(raw).hexdigest()+'.json')
            if not receipt.exists():atomic_write(receipt,(json.dumps({'previous':previous,**report},indent=2)+'\n').encode())
            atomic_write(path,changed)
        return report
