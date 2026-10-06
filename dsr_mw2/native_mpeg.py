"""Bounded MP3 framing for a separate, uninstalled native M9 sound candidate.

Matches the owned crossbow sample: MPEG-1 Layer III, 160 kbps, 44100 Hz, mono,
four-byte frame alignment inside FSB4. Does not decode or play sound.
"""
import struct
from .native_audio_bank import inspect_bank


def frames(data: bytes, *, fsb_aligned=False) -> tuple[bytes, ...]:
    if not 4 <= len(data) <= 1024*1024:
        raise ValueError('MPEG sample outside bounded size')
    result, cursor = [], 0
    while cursor < len(data):
        remaining = len(data)-cursor
        if fsb_aligned and remaining < 32 and not any(data[cursor:]):
            break
        if remaining < 4:
            raise ValueError('Truncated MPEG frame header')
        h = int.from_bytes(data[cursor:cursor+4], 'big')
        if (h >> 21 != 0x7FF or (h >> 19) & 3 != 3 or (h >> 17) & 3 != 1
                or (h >> 12) & 15 != 10 or (h >> 10) & 3 != 0 or (h >> 6) & 3 != 3):
            raise ValueError('Expected native 160 kbps MPEG-1 Layer III mono at 44100 Hz')
        size = 144000*160//44100 + ((h >> 9) & 1)
        end = cursor + size
        if end > len(data):
            raise ValueError('Truncated MPEG frame payload')
        result.append(data[cursor:end])
        # Native FSB alignment bytes can contain nonzero garbage, not audio.
        cursor = end + ((-size) % 4 if fsb_aligned else 0)
        if cursor > len(data):
            raise ValueError('Truncated FSB frame alignment')
    if not result:
        raise ValueError('No MPEG frames')
    return tuple(result)


def replace_mpeg(bank: bytes, mp3: bytes) -> tuple[bytes, dict]:
    samples = inspect_bank(bank)
    if len(samples) != 279:
        raise ValueError('Expected native 279-sample main bank')
    original = samples[56]
    if (original.name, original.mode, original.channels, original.rate) != (
            'bowgun-shot.wav', 0x10100220, 1, 44100):
        raise ValueError('Unexpected native crossbow sample format')
    old_frames = frames(bank[original.data_at:original.data_at+original.size], fsb_aligned=True)
    if len(old_frames)*1152 != original.frames:
        raise ValueError('Native sample count and MPEG frames disagree')
    encoded = frames(mp3)
    payload = b''.join(frame + bytes((-len(frame)) % 4) for frame in encoded)
    payload += bytes((-len(payload)) % 32)
    pcm_frames = 1152*len(encoded)
    result = bytearray(bank[:original.data_at]+payload+bank[original.data_at+original.size:])
    struct.pack_into('<I', result, 12, struct.unpack_from('<I', bank, 12)[0]-original.size+len(payload))
    struct.pack_into('<4I', result, original.header_at+32, pcm_frames, len(payload), 0, pcm_frames-1)
    result = bytes(result)
    new_samples = inspect_bank(result)
    new = new_samples[56]
    if frames(result[new.data_at:new.data_at+new.size], fsb_aligned=True) != encoded:
        raise ValueError('FSB framing changed encoded MP3 bytes')
    for index, (before, after) in enumerate(zip(samples, new_samples, strict=True)):
        if index != 56 and (bank[before.header_at:before.header_at+80] != result[after.header_at:after.header_at+80]
                or bank[before.data_at:before.data_at+before.size] != result[after.data_at:after.data_at+after.size]):
            raise ValueError('Unrelated native sound changed')
    if result[:12] != bank[:12] or result[16:48] != bank[16:48]:
        raise ValueError('Bank identity or codec flags changed')
    return result, {'sample_index': 56, 'mpeg_frame_count': len(encoded),
                    'decoded_frames': pcm_frames, 'sample_rate': 44100, 'channels': 1,
                    'bitrate_kbps': 160, 'native_mode_preserved': True,
                    'frame_alignment': 4, 'sample_alignment': 32,
                    'unrelated_samples_preserved': 278}
