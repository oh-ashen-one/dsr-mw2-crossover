"""Preserve the native DSR Havok type bytes in otherwise identical-type clips.

The current exporter changes only THSH ordering in the native TYPE section.
Require every other TYPE byte and every hash/index pair to match before using
the original section. This changes no spline, binding, bone or event data.
Native engine acceptance remains a test requirement.
"""
import hashlib
import json
import struct
from pathlib import Path
from dsr_mw2.soulstruct_tools import configure,WORKSPACE as ROOT
from dsr_mw2.runtime_paths import bottle_path

def sections(raw,start=0,end=None):
    if end is None:end=len(raw)
    found={}
    while start<end:
        if start+8>end:raise ValueError('Truncated tag')
        size=struct.unpack_from('>I',raw,start)[0]&0x3fffffff
        tag=raw[start+4:start+8].decode('ascii')
        if size<8 or start+size>end or tag in found:raise ValueError('Invalid tag bounds')
        found[tag]=(start,start+size)
        if tag in ('TAG0','TYPE','INDX'):
            nested=sections(raw,start+8,start+size)
            if found.keys()&nested.keys():raise ValueError('Duplicate tag')
            found.update(nested)
        start+=size
    return found

def hash_pairs(raw):
    at=8
    def varint():
        nonlocal at
        first=raw[at];at+=1
        if first<0x80:return first
        if first<0xc0:
            value=((first&0x3f)<<8)|raw[at];at+=1;return value
        raise ValueError('Unexpected native hash index size')
    count=varint();pairs={}
    for _ in range(count):
        i=varint();h=struct.unpack_from('<I',raw,at)[0];at+=4
        if i in pairs:raise ValueError('Duplicate hash index')
        pairs[i]=h
    if any(raw[at:]):raise ValueError('Nonzero hash section padding')
    return pairs

def preserve_types(native,new):
    a,b=sections(native),sections(new)
    for tag in ('SDKV','TPTR','TSTR','TNAM','FSTR','TBOD','TPAD'):
        if native[slice(*a[tag])]!=new[slice(*b[tag])]:
            raise ValueError('Native type definitions differ: '+tag)
    old_hashes=native[slice(*a['THSH'])];new_hashes=new[slice(*b['THSH'])]
    if hash_pairs(old_hashes)!=hash_pairs(new_hashes):raise ValueError('Native type hash mapping differs')
    start,end=b['TYPE'];replacement=native[slice(*a['TYPE'])]
    if len(replacement)!=end-start:raise ValueError('Type section size differs')
    result=new[:start]+replacement+new[end:]
    assert result[:start]==new[:start] and result[end:]==new[end:]
    return result

def main():
    configure()
    from soulstruct.containers import Binder
    native=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx')
    source=ROOT/'converted/mw2-2009/m9/havok/player-reference-v2/report.json'
    records=json.loads(source.read_text())['clips']
    out=source.parent.parent/'player-native-types-v3';out.mkdir(exist_ok=True)
    reports=[]
    for number,clip in ((463000,'fire'),(465502,'reload'),(465501,'reload_empty2')):
        entry=next(e for e in native.entries if e.entry_id==number)
        r=next(r for r in records if r['source_clip']=='viewmodel_beretta_'+clip)
        raw=(ROOT/r['spline']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=r['spline_sha256']:raise ValueError('Input changed')
        data=preserve_types(entry.get_uncompressed_data(),raw)
        path=out/(r['source_clip']+'.hkx');path.write_bytes(data)
        reports.append({**r,'source_sha256':r['spline_sha256'],'spline':str(path.relative_to(ROOT)),
            'spline_sha256':hashlib.sha256(data).hexdigest(),'native_type_section_exact':True,
            'changed_bytes':sum(a!=b for a,b in zip(raw,data)),'runtime_verified':False})
    (out/'report.json').write_text(json.dumps({'clips':reports,'hypothesis_only':True},indent=2)+'\n')
    print(json.dumps([{'clip':r['source_clip'],'changed_bytes':r['changed_bytes']} for r in reports]))

if __name__=='__main__':main()
