"""Trace unchanged native crossbow TAE -> FEV event/definition -> M9 FSB slot."""
import hashlib
import json
from pathlib import Path
import struct
from dsr_mw2.soulstruct_tools import configure
from dsr_mw2.tae32 import read_events

ROOT=Path(__file__).resolve().parents[1]


def main():
    configure()
    from soulstruct.containers import Binder
    from soulstruct.utilities.binary import BinaryReader
    from soulstruct.darksouls1r.sound.fev.core import Event,SoundDef
    from soulstruct.darksouls1r.sound.fsb import FSB
    native=ROOT/'profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered'
    binder=Binder.from_path(native/'chr/c0000.anibnd.dcx')
    raw=next(e for e in binder.entries if e.path.endswith('\\a46.tae')).get_uncompressed_data()
    tae_hash=hashlib.sha256(raw).hexdigest()
    if tae_hash!='f57bb059cd3656109a0df549b77d44d2893673df9949752d872185e12bbb9280':
        raise ValueError('Native crossbow TAE revision changed')
    identity,events=read_events(raw)
    fires=[e for e in events if e.sound==(1,10400)]
    if not {3000,4000,5000}.issubset({e.animation for e in fires}):
        raise ValueError('Expected native crossbow shot cues missing')
    fsb_data=(ROOT/'converted/dsr/m9-native-audio-candidate/mod/sound/frpg_main.fsb').read_bytes()
    fev=(ROOT/'converted/dsr/m9-native-audio-candidate/mod/sound/frpg_main.fev').read_bytes()
    fsb_hash=hashlib.sha256(fsb_data).hexdigest()
    fev_hash=hashlib.sha256(fev).hexdigest()
    if (fsb_hash!='89f6d616dfdd1f36ad3fbc32fc270138659c7194ae5a0addc4e4b1253bcd7423' or
            fev_hash!='0c418b099e4a14c154d842e8b66fd3220a0ff642de75f12671e6e909c5b2eb02'):
        raise ValueError('Verified authentic M9 audio candidate revision changed')
    fsb=FSB.from_bytes(fsb_data)
    # Full EventGroup traversal fails in this pinned reader on an unrelated
    # complex layer. Parse the intact sound-definition array separately, proving
    # its count and every record boundary rather than guessing an index by name.
    positions=[];at=0
    while (at:=fev.find(b'/frpg_main/',at))>=0:
        if at>=4 and 0<(n:=struct.unpack_from('<I',fev,at-4)[0])<256 and fev[at+n-1:at+n]==b'\0':positions.append(at-4)
        at+=1
    if not positions or struct.unpack_from('<I',fev,positions[0]-4)[0]!=len(positions):
        raise ValueError('Native SoundDef array count not established')
    definitions=[];end=None
    for start in positions:
        if end is not None and end!=start:raise ValueError('SoundDef array is not contiguous')
        reader=BinaryReader(fev);reader.seek(start);definitions.append(SoundDef.from_fev_reader(reader));end=reader.position
    routes=[]
    for name in ('c000010400','g000010400'):
        encoded=name.encode()+b'\0'
        if fev.count(encoded)!=1:raise ValueError('Expected unique shot event')
        at=fev.index(encoded)
        if struct.unpack_from('<I',fev,at-4)[0]!=len(encoded):raise ValueError('Invalid event name record')
        reader=BinaryReader(fev);reader.seek(at-8);event=Event.from_fev_reader(reader)
        targets=[s.sounddef_index for layer in event.layers for s in layer.sound_instances]
        mapped=[]
        for target in targets:
            definition=definitions[target]
            for w in definition.waveforms:
                if w.bank_name!='frpg_main' or w.index_in_bank!=56 or w.playtime!=1117:
                    raise ValueError('Shot event does not reach the candidate native sample')
                sample=fsb.samples[w.index_in_bank]
                if sample.header.name!='bowgun-shot.wav' or sample.header.channel_count!=2 or sample.header.length!=49283:
                    raise ValueError('Event resolves to unexpected sample')
                mapped.append({'sounddef_index':target,'sounddef_name':definition.name,'fsb_sample':w.index_in_bank})
        if not mapped:raise ValueError('Native shot event has no waveforms')
        routes.append({'native_event':name,'mappings':mapped})
    report={'tae_id':identity,'tae_version':'0x1000B','tae_offsets':32,'native_animation_count':len({e.animation for e in events}),
            'native_tae_sha256':tae_hash,'candidate_fsb_sha256':fsb_hash,'candidate_fev_sha256':fev_hash,
            'shot_animation_ids':sorted({e.animation for e in fires}),'shot_sound_type':1,'shot_sound_id':10400,
            'sounddefs_contiguously_parsed':len(definitions),'native_routes':routes,
            'sound_bank_candidate_verified':True,'native_tae_changed':False,'game_launched':False,'runtime_verified':False,
            'limits':['Sound-type prefix c from approved native SoundType table; ghost route g also checked',
                      'Shared shot sample still affects other native crossbow users',
                      'Format route is verified; runtime playback, attenuation and phase not verified'],
            'tae_format_sources':['https://github.com/soulsmods/SoulsFormats/blob/master/SoulsFormats/Formats/TAE/TAE.cs',
                                  'https://github.com/soulsmods/SoulsFormats/blob/master/SoulsFormats/Formats/TAE/Animation.cs',
                                  'https://github.com/soulsmods/SoulsFormats/blob/master/SoulsFormats/Formats/TAE/Event.cs']}
    (ROOT/'evidence/native-m9-audio-routes.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
