"""Original narrow FSB4/FEV waveform patcher, preserving native event routing.

No FMOD, decoder/helper executable, process attachment or playback is involved.
Layout/flag facts were checked in approved Soulstruct and vgmstream's FSB parser.
Only full 80-byte sample headers and the measured MPEG_PADDED4 bank are accepted.
"""
from dataclasses import dataclass
import struct
from .wav_container import repair_oat_pcm


@dataclass(frozen=True)
class Sample:
    name: str
    header_at: int
    data_at: int
    frames: int
    size: int
    rate: int
    channels: int
    mode: int


def inspect_bank(data: bytes) -> tuple[Sample, ...]:
    if not 48 <= len(data) <= 32*1024*1024:
        raise ValueError("FSB bank size outside bounded layout")
    signature, count, header_bytes, payload_bytes, version, flags = struct.unpack_from("<4s5I", data)
    if signature != b"FSB4" or version != 0x40000 or flags != 0x40:
        raise ValueError("Only native FSB4 full-header MPEG_PADDED4 banks supported")
    if not 1 <= count <= 4096 or header_bytes != count*80 or 48+header_bytes+payload_bytes != len(data):
        raise ValueError("FSB header/data sizes disagree")
    cursor = 48+header_bytes
    samples = []
    for i in range(count):
        at = 48+i*80
        if struct.unpack_from("<H", data, at)[0] != 80:
            raise ValueError("Unexpected sample header or codec metadata")
        name_bytes = data[at+2:at+32]
        if b"\0" not in name_bytes:
            raise ValueError("Unterminated sample name")
        name = name_bytes.split(b"\0", 1)[0].decode("ascii")
        frames, size, start, end, mode, rate = struct.unpack_from("<6I", data, at+32)
        channels = struct.unpack_from("<H", data, at+62)[0]
        if not name or not frames or not size or size % 32 or cursor+size > len(data):
            raise ValueError("Invalid aligned sample payload")
        if not 8000 <= rate <= 192000 or channels not in (1,2) or start > end or end >= frames:
            raise ValueError("Invalid sample playback format")
        samples.append(Sample(name, at, cursor, frames, size, rate, channels, mode))
        cursor += size
    if cursor != len(data) or len({s.name for s in samples}) != count:
        raise ValueError("Duplicate sample names or trailing bank payload")
    return tuple(samples)


def replace_pcm(bank: bytes, sample_index: int, expected_name: str, wav: bytes) -> tuple[bytes, dict]:
    samples = inspect_bank(bank)
    if type(sample_index) is not int or not 0 <= sample_index < len(samples):
        raise ValueError("Invalid native sample index")
    original = samples[sample_index]
    if original.name != expected_name or original.mode != 0x10100220:
        raise ValueError("Unexpected native MPEG/mono/3D sample identity")
    fixed, pcm = repair_oat_pcm(wav)
    if fixed != wav:
        raise ValueError("Use the verified repaired source WAV")
    payload = wav[44:]
    padding = (-len(payload)) % 32
    payload += b"\0" * padding
    result = bytearray(bank[:original.data_at] + payload + bank[original.data_at+original.size:])
    old_payload_size = struct.unpack_from("<I", bank, 12)[0]
    struct.pack_into("<I", result, 12, old_payload_size-original.size+len(payload))
    # Native 3D spatialization flag retained; source PCM channels/rate preserved.
    # MP3 codec bits removed. Explicit LOOP_OFF avoids a looping gunshot.
    mode = 0x00100000 | 0x10 | 0x100 | (0x20 if pcm["channels"] == 1 else 0x40) | 0x1
    struct.pack_into("<6I", result, original.header_at+32, pcm["samples"], len(payload), 0,
                     pcm["samples"]-1, mode, pcm["sample_rate"])
    struct.pack_into("<H", result, original.header_at+62, pcm["channels"])
    encoded = bytes(result)
    decoded = inspect_bank(encoded)
    new = decoded[sample_index]
    if encoded[new.data_at:new.data_at+len(wav)-44] != wav[44:]:
        raise ValueError("Gun PCM sample bytes changed")
    for i, (before, after) in enumerate(zip(samples, decoded, strict=True)):
        if i == sample_index:
            continue
        if (bank[before.header_at:before.header_at+80] != encoded[after.header_at:after.header_at+80] or
                bank[before.data_at:before.data_at+before.size] != encoded[after.data_at:after.data_at+after.size]):
            raise ValueError("An unrelated sound changed")
    # Bank identity/hash/GUID stay aligned with unchanged native FEV references.
    if encoded[:12] != bank[:12] or encoded[16:48] != bank[16:48]:
        raise ValueError("Native sound bank identity changed")
    return encoded, {"sample_index": sample_index, "native_sample_name": expected_name,
                     "source_frames": pcm["samples"], "source_channels": pcm["channels"],
                     "source_rate": pcm["sample_rate"], "source_pcm_bytes": len(wav)-44,
                     "native_padding_bytes": padding, "source_pcm_preserved": True,
                     "unrelated_samples_preserved": len(samples)-1, "sample_mode": hex(mode)}


def patch_waveform_playtimes(fev: bytes, *, name: str, bank_name: str, sample_index: int,
                             old_ms: int, new_ms: int, expected_count: int) -> tuple[bytes, list[int]]:
    """Replace duration fields of exact FEV Waveform records without rebuilding.

    This is deliberately not a general FEV parser. Callers must hash-pin the
    complete native FEV and establish the exact expected records first.
    """
    if fev[:4] != b"FEV1" or len(fev) > 4*1024*1024 or not 0 < new_ms < 60000:
        raise ValueError("Unexpected FEV or playback duration")
    def string(value):
        encoded = value.encode("ascii") + b"\0"
        return struct.pack("<I", len(encoded)) + encoded
    needle = b"\0"*4 + struct.pack("<I",100) + string(name) + string(bank_name) + struct.pack("<II",sample_index,old_ms)
    positions = []
    start = 0
    while (at := fev.find(needle, start)) != -1:
        positions.append(at+len(needle)-4)
        start = at+len(needle)
    if len(positions) != expected_count or expected_count < 1:
        raise ValueError("Native waveform record count/identity changed")
    result = bytearray(fev)
    for at in positions:
        struct.pack_into("<I", result, at, new_ms)
    changed = {at+i for at in positions for i in range(4)}
    if any(a != b and i not in changed for i,(a,b) in enumerate(zip(fev,result,strict=True))):
        raise ValueError("FEV event/definition routing changed")
    return bytes(result), positions
