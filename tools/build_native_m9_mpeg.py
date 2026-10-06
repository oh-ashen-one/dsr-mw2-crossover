"""Offline codec-matched audio study. Never install, play, or launch anything.

Uses the pre-existing trusted local FFmpeg only to encode/decode files, with no
audio device. The working installed FSB/FEV pair remains stock.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from dsr_mw2.install_audio import STOCK, check
from dsr_mw2.native_audio_bank import inspect_bank, patch_waveform_playtimes
from dsr_mw2.native_mpeg import frames, replace_mpeg
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import WORKSPACE, configure

FFMPEG = '/opt/homebrew/bin/ffmpeg'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = WORKSPACE/'converted/mw2-2009/m9/audio/weap_beretta_slst_3c.wav'
    wav = source.read_bytes()
    if digest(wav) != '09e57b78ec5a3b6a94b118ec378fa204b7a0b80213590f4c570dbd6c66829f3c':
        raise ValueError('Authentic M9 source revision changed')
    base = bottle_path()/'drive_c/Games/Dark Souls Remastered'
    fsb, fev = ((base/rel).read_bytes() for rel in STOCK)
    if any(digest(data) != expected for data, expected in zip((fsb,fev),STOCK.values(),strict=True)):
        raise ValueError('Native audio baseline changed')
    installed = check()
    if not installed['valid'] or installed['enabled']:
        raise ValueError('Expected the working stock audio installation')
    prefix = [FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error']
    version = subprocess.run([FFMPEG,'-version'],check=True,capture_output=True,text=True).stdout.splitlines()[0]
    command = prefix + ['-i',str(source),'-map_metadata','-1','-ac','1','-ar','44100',
                        '-codec:a','libmp3lame','-b:a','160k','-write_xing','0',
                        '-id3v2_version','0','-f','mp3','pipe:1']
    mp3 = subprocess.run(command,check=True,capture_output=True).stdout
    candidate, report = replace_mpeg(fsb,mp3)
    sample = inspect_bank(candidate)[56]
    recovered = b''.join(frames(candidate[sample.data_at:sample.data_at+sample.size],fsb_aligned=True))
    if recovered != mp3:
        raise ValueError('Embedded audio differs from the encode')
    decode = prefix + ['-f','mp3','-i','pipe:0','-f','s16le','-acodec','pcm_s16le','pipe:1']
    pcm = subprocess.run(decode,input=recovered,check=True,capture_output=True).stdout
    if len(pcm) != report['decoded_frames']*2 or not any(pcm):
        raise ValueError('Independent FFmpeg decode has wrong length or is silent')
    duration = report['decoded_frames']*1000//44100
    events, offsets = patch_waveform_playtimes(fev,name='bank/frpg_main/bowgun-shot.wav',
        bank_name='frpg_main',sample_index=56,old_ms=1027,new_ms=duration,expected_count=3)
    configure()
    from soulstruct.darksouls1r.sound.fsb import FSB
    parsed = FSB.from_bytes(candidate)
    if len(parsed.samples) != 279 or parsed.samples[56].header.mode_flags != 0x10100220:
        raise ValueError('Independent Soulstruct bank parse disagrees')
    destination = WORKSPACE/'converted/dsr/m9-mpeg-audio-study'
    if destination.is_symlink() or not destination.resolve().is_relative_to(WORKSPACE/'converted'):
        raise ValueError('Audio study output escapes the task')
    destination.mkdir(exist_ok=True)
    for name, data in (('frpg_main.fsb',candidate),('frpg_main.fev',events),('m9-mono.mp3',mp3)):
        target = destination/name
        if target.is_symlink():
            raise ValueError('Audio study file is redirected')
        target.write_bytes(data)
    if check() != installed:
        raise ValueError('Installed audio changed during offline study')
    report.update(at=datetime.now(timezone.utc).isoformat(),
        source_wav_sha256=digest(wav),fsb_sha256=digest(candidate),fev_sha256=digest(events),
        mp3_sha256=digest(mp3),decoded_pcm_sha256=digest(pcm),ffmpeg=version,
        source_frames=49283,source_channels=2,source_downmixed_to_native_mono=True,
        source_trimmed=False,fev_duration_ms=duration,fev_duration_offsets=offsets,
        independent_ffmpeg_decode_passed=True,independent_soulstruct_parse_passed=True,
        installed=False,audio_played=False,game_launched=False,runtime_verified=False,
        installer_has_no_route_to_this_candidate=True,
        limitations=['FFmpeg decode is not native FMOD validation',
                    'MPEG encoder delay and tail padding have not been compensated in game',
                    'The shared crossbow sound route affects other native users too',
                    'No reload audio or M9-specific TAE routing integrated'])
    (WORKSPACE/'evidence/native-m9-mpeg-study.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
