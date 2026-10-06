"""Build a separate native crossbow-gunfire sound bank candidate; never install/play."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dsr_mw2.native_audio_bank import inspect_bank, patch_waveform_playtimes, replace_pcm
from dsr_mw2.soulstruct_tools import configure

ROOT = Path(__file__).resolve().parents[1]


def digest(data):return hashlib.sha256(data).hexdigest()


def main():
    base=ROOT/'profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/sound'
    fsb=(base/'frpg_main.fsb').read_bytes()
    fev=(base/'frpg_main.fev').read_bytes()
    wav=(ROOT/'converted/mw2-2009/m9/audio/weap_beretta_slst_3c.wav').read_bytes()
    pins={'fsb':'7e9ef82652f361cda5e5e8c18178d747f29a4685914d8f02c0ffd7957c428074',
          'fev':'28ebfd34bb9e893fe4cfa93a85ae43d2832f75175170bf60ca5b84f8fffa488b',
          'wav':'09e57b78ec5a3b6a94b118ec378fa204b7a0b80213590f4c570dbd6c66829f3c'}
    if any(digest(data)!=pins[key] for key,data in (('fsb',fsb),('fev',fev),('wav',wav))):
        raise ValueError('Native bank or authentic source audio revision changed')
    candidate,report=replace_pcm(fsb,56,'bowgun-shot.wav',wav)
    duration=report['source_frames']*1000//report['source_rate']
    events,offsets=patch_waveform_playtimes(fev,name='bank/frpg_main/bowgun-shot.wav',bank_name='frpg_main',
                                        sample_index=56,old_ms=1027,new_ms=duration,expected_count=3)
    # Independent approved parser verifies sample format/count/payload slices.
    # Do not call fsbext(), FEV.write(), FMOD Designer or any audio playback API.
    configure()
    from soulstruct.darksouls1r.sound.fsb import FSB
    decoded=FSB.from_bytes(candidate)
    item=decoded.samples[56]
    if (len(decoded.samples)!=279 or item.header.name!='bowgun-shot.wav' or item.header.channel_count!=2 or
            item.header.length!=49283 or item.data[:len(wav)-44]!=wav[44:]):
        raise ValueError('Independent native bank parse does not recover full authentic PCM')
    old_decoded=FSB.from_bytes(fsb)
    if any(before.header!=after.header or before.data!=after.data for i,(before,after) in enumerate(zip(old_decoded.samples,decoded.samples,strict=True)) if i!=56):
        raise ValueError('Independent native parser found an unrelated sound change')
    output=ROOT/'converted/dsr/m9-native-audio-candidate/mod/sound'
    if not output.resolve().is_relative_to(ROOT/'converted'):
        raise ValueError('Audio output escaped task')
    output.mkdir(parents=True,exist_ok=True)
    for name,data in (('frpg_main.fsb',candidate),('frpg_main.fev',events)):
        destination=output/name
        if destination.is_symlink():raise ValueError('Audio output cannot be a symlink')
        destination.write_bytes(data)
    if (base/'frpg_main.fsb').read_bytes()!=fsb or (base/'frpg_main.fev').read_bytes()!=fev:
        raise ValueError('Native source changed during build')
    report.update(at=datetime.now(timezone.utc).isoformat(),source_hashes=pins,
        output_fsb_sha256=digest(candidate),output_fev_sha256=digest(events),
        patched_fev_duration_offsets=offsets,old_fev_duration_ms=1027,new_fev_duration_ms=duration,
        event_routing_preserved=True,independent_soulstruct_fsb_parse_passed=True,
        fsb_samples=279,full_fev_parser_passed=False,
        fev_parser_blocker='Pinned Soulstruct Layer.COMPLEX_STRUCT signature assertion fails on unmodified native FEV; targeted hash-pinned Waveform records were patched instead',
        installed=False,audio_played=False,game_launched=False,runtime_verified=False,
        scope='Existing shared native crossbow gunshot sample, including three FEV waveform references; not M9-only event isolation',
        remaining=['DSR FMOD mixed PCM/MPEG playback and 3D stereo spatialization unverified',
                   'M9-only event routing requires native event/TAE identity; other users of this shared sample would also change',
                   'Reload foley needs actual reload animation/audio cues; remains unstaged'],
        format_reference='https://github.com/vgmstream/vgmstream/blob/master/src/meta/fsb.c')
    (ROOT/'evidence/native-m9-audio-candidate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
