"""Preserve authored animation cues without inventing runtime timing or aliases."""
from __future__ import annotations

import re

from .xanim import Animation


def weapon_fields(data: bytes) -> dict[str, str]:
    if len(data) > 1024 * 1024:
        raise ValueError('Oversized weapon info string')
    parts = data.decode('ascii').split('\\')
    if parts[0] != 'WEAPONFILE' or len(parts) % 2 != 1:
        raise ValueError('Invalid weapon info string')
    result = dict(zip(parts[1::2], parts[2::2], strict=True))
    if len(result) * 2 + 1 != len(parts) or any(not key for key in result):
        raise ValueError('Duplicate or empty weapon field')
    return result


def note_maps(fields: dict[str, str]) -> dict[str, tuple[str, str]]:
    result = {}
    for field, kind in (('notetrackSoundMap', 'sound_alias'), ('notetrackRumbleMap', 'rumble_alias')):
        if field not in fields:
            raise ValueError('Missing explicit source notetrack mapping')
        for line in fields[field].splitlines():
            if not line.strip():
                continue
            pair = line.split()
            if len(pair) != 2 or any(not re.fullmatch(r'[A-Za-z0-9_]+', name) for name in pair):
                raise ValueError('Invalid source note mapping')
            note, alias = pair
            if note in result:
                raise ValueError('Duplicate or ambiguous source note')
            result[note] = (kind, alias)
    return result


def classify_events(animation: Animation, maps: dict[str, tuple[str, str]]) -> list[dict]:
    """Keep source-frame and normalized phase, without choosing a DSR clock.

    Unknown notes fail instead of being dropped. Sound aliases are not file
    paths: resolving a WAV from an alias needs separate source evidence.
    """
    result = []
    for note, frame in animation.events:
        if note not in maps or not 0 <= frame <= animation.frames:
            raise ValueError('Unmapped or out-of-range authored note: ' + note)
        kind, alias = maps[note]
        if kind not in ('sound_alias', 'rumble_alias'):
            raise ValueError('Unknown cue kind')
        result.append({'name': note, 'kind': kind, 'alias': alias, 'source_frame': frame,
                       'source_seconds': frame / animation.fps,
                       'normalized_phase': frame / animation.frames if animation.frames else 0.0,
                       'native_event_id': None, 'resolved_audio_file': None})
    return result
