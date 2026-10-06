"""Bounded original reader for native DSR's 0x1000B, 32-bit-offset TAE events.

The game's x64 folder does not imply 64-bit TAE offsets. Layout facts were
checked against SoulsFormats' DS1 branch and the owned native a46 file. This
reader is for route verification, not a general TAE serializer or event editor.
"""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class Event:
    animation: int
    index: int
    kind: int
    start: float
    end: float
    parameter_offset: int
    sound: tuple[int, int] | None


def read_events(data: bytes) -> tuple[int, tuple[Event, ...]]:
    if not 160 <= len(data) <= 8*1024*1024:
        raise ValueError("Invalid TAE size")
    def read(fmt, at):
        size=struct.calcsize('<'+fmt)
        if at < 0 or at+size > len(data):
            raise ValueError("TAE pointer outside file")
        return struct.unpack_from('<'+fmt,data,at)
    if data[:8] != b'TAE \0\0\0\0' or read('II',8) != (0x1000B,len(data)):
        raise ValueError("Expected native little-endian 32-bit-offset TAE 0x1000B")
    if read('4I',0x10) != (0x40,1,0x50,0x70) or read('HH',0x20) != (2,1):
        raise ValueError("Unexpected native TAE header layout")
    tae_id,count,table=read('III',0x50)
    if not 0 < count <= 4096 or read('I',0x64)[0] != count or read('II',0x80)!=(tae_id,tae_id):
        raise ValueError("TAE header counts/identity disagree")
    read(str(count*8)+'s',table)
    seen=set();events=[]
    for i in range(count):
        animation,header=read('II',table+i*8)
        if animation in seen:raise ValueError("Duplicate TAE animation")
        seen.add(animation)
        n,headers,groups,group_at,times,time_at,mini=read('7I',header)
        if n>4096 or groups>4096 or times>8192:raise ValueError("TAE count exceeds bound")
        if n:read(str(n*12)+'s',headers)
        if times:read(str(times*4)+'s',time_at)
        if groups:read(str(groups*12)+'s',group_at)
        read('II',mini)
        for j in range(n):
            start_at,end_at,parameters=read('III',headers+j*12)
            if any(at<time_at or at>=time_at+times*4 or (at-time_at)%4 for at in (start_at,end_at)):
                raise ValueError("TAE event time outside its time table")
            start,end=read('f',start_at)[0],read('f',end_at)[0]
            if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<start:
                raise ValueError("Invalid TAE event time")
            kind,explicit=read('II',parameters)
            payload=parameters+8
            if explicit not in (0,payload):raise ValueError("Unexpected TAE parameter pointer")
            sound=read('ii',payload) if kind==128 else None
            events.append(Event(animation,j,kind,start,end,payload,sound))
    return tae_id,tuple(events)


def remove_reload_bolt_effect(data: bytes, animations=(5501,5502)) -> bytes:
    """Remove only native held-bolt FFX6000 records from ungrouped reloads.

    Compact fixed event headers in place; all absolute payload/time offsets,
    animation data and the firing/Bullet event remain unchanged. Grouped event
    tables require a different writer and are deliberately refused.
    """
    identity,events=read_events(data);result=bytearray(data)
    count,table=struct.unpack_from('<II',data,0x54)
    removed=set()
    for i in range(count):
        number,header=struct.unpack_from('<II',data,table+8*i)
        if number not in animations:continue
        n,headers,groups=struct.unpack_from('<III',data,header)
        selected=[e for e in events if e.animation==number and e.kind==119]
        if groups or len(selected)!=1:raise ValueError('Expected one ungrouped reload bolt effect')
        event=selected[0]
        effect,dummy,extra,repeat=struct.unpack_from('<ihhi',data,event.parameter_offset)
        if effect!=6000 or dummy not in (55,56) or extra!=0 or repeat!=1:
            raise ValueError('Unexpected held-bolt effect payload')
        kept=[data[headers+12*j:headers+12*(j+1)] for j in range(n) if j!=event.index]
        result[headers:headers+12*(n-1)]=b''.join(kept)
        struct.pack_into('<I',result,header,n-1);removed.add(number)
    if removed!=set(animations):raise ValueError('Missing requested reload animations')
    checked=read_events(bytes(result))
    key=lambda e:(e.animation,e.kind,e.start,e.end,e.parameter_offset,e.sound)
    wanted=[key(e) for e in events if not(e.animation in removed and e.kind==119)]
    if checked[0]!=identity or [key(e) for e in checked[1]]!=wanted:
        raise ValueError('Unrelated TAE events changed')
    return bytes(result)


def remove_shared_gunshot(data: bytes) -> bytes:
    """Remove only a463000's (1,10400) sound; retain native shot/collision events.

    This action now selects original per-weapon audio from its verified native
    ammo receipt. Other native actions and their sound cues are unchanged.
    """
    identity,events=read_events(data);result=bytearray(data)
    matches=[e for e in events if e.animation==3000 and e.sound==(1,10400)]
    if len(matches)!=1:raise ValueError('Expected one native gunshot cue')
    selected=matches[0];count,table=struct.unpack_from('<II',data,0x54)
    for i in range(count):
        number,header=struct.unpack_from('<II',data,table+8*i)
        if number!=3000:continue
        n,headers,groups=struct.unpack_from('<III',data,header)
        if groups:raise ValueError('Grouped gunshot events are unsupported')
        kept=[data[headers+12*j:headers+12*(j+1)] for j in range(n) if j!=selected.index]
        result[headers:headers+12*(n-1)]=b''.join(kept)
        struct.pack_into('<I',result,header,n-1)
    checked=read_events(bytes(result))
    key=lambda e:(e.animation,e.kind,e.start,e.end,e.parameter_offset,e.sound)
    if checked[0]!=identity or [key(e) for e in checked[1]]!=[key(e) for e in events if e!=selected]:
        raise ValueError('Unrelated TAE event changed')
    return bytes(result)
