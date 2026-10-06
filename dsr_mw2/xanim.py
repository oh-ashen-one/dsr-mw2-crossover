"""Bounded reader for OAT's compiled IW4 skeletal animation exports.

Format reference: the pinned OAT CompiledXAnimWriter and BinaryXAnimCommon.
Original implementation; game transforms remain local and are never embedded in
source. Delta-root tracks and versions other than 17/18 are rejected explicitly.
"""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class Track:
    indices: tuple[int, ...]
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class Bone:
    name: str
    rotation: Track
    translation: Track


@dataclass(frozen=True)
class Animation:
    version: int
    frames: int
    fps: int
    looped: bool
    asset_type: int
    bones: tuple[Bone, ...]
    events: tuple[tuple[str, int], ...]

    @property
    def seconds(self):
        return self.frames / self.fps


class Cursor:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, count):
        if count < 0 or self.offset + count > len(self.data):
            raise ValueError("Truncated XAnim export")
        result = self.data[self.offset:self.offset + count]
        self.offset += count
        return result

    def unpack(self, fmt):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))

    def name(self):
        end = self.data.find(b"\0", self.offset, self.offset + 256)
        if end < 0:
            raise ValueError("Unterminated/oversized XAnim name")
        name = self.take(end - self.offset).decode("ascii")
        self.take(1)
        if not name or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid XAnim name")
        return name


def read(data: bytes) -> Animation:
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("Oversized XAnim export")
    c = Cursor(data)
    version, raw_frames, count, flags, asset_type, fps = c.unpack("HHHBBH")
    if version not in {17, 18} or flags & ~1:
        raise ValueError("Unsupported XAnim version or delta-root flags")
    looped = bool(flags & 1)
    frames = raw_frames if looped else raw_frames - 1
    if not 0 <= frames <= 10000 or not 1 <= fps <= 1000 or not 1 <= count <= 512:
        raise ValueError("Invalid XAnim frame/bone/rate limits")
    masks = (count + 7) // 8
    signs, halves = c.take(masks), c.take(masks)
    names = [c.name() for _ in range(count)]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate XAnim bone name")

    def indices(size):
        if size > frames + 1:
            raise ValueError("XAnim track exceeds frame count")
        if size == 0:
            return ()
        if size == 1:
            return (0,)
        if size == frames + 1:
            return tuple(range(size))
        values = c.unpack(("B" if frames < 256 else "H") * size)
        if any(a >= b for a, b in zip(values, values[1:])) or values[-1] > frames:
            raise ValueError("Invalid XAnim key indices")
        return values

    bones = []
    for i, name in enumerate(names):
        half = bool(halves[i // 8] & (1 << (i % 8)))
        sign = -1 if signs[i // 8] & (1 << (i % 8)) else 1
        num_quats, = c.unpack("H")
        quat_indices = indices(num_quats)
        rotations = []
        for _ in range(num_quats):
            values = c.unpack("h" if half else "hhh")
            xyz = (0.0, 0.0, values[0] / 32767.0) if half else tuple(v / 32767.0 for v in values)
            square = sum(v * v for v in xyz)
            if square > 1.0002:
                raise ValueError("Invalid quantized XAnim rotation")
            quat = tuple(sign * v for v in (*xyz, math.sqrt(max(0.0, 1.0 - square))))
            length = math.sqrt(sum(v*v for v in quat))
            quat = tuple(v / length for v in quat)
            if rotations and sum(a*b for a, b in zip(rotations[-1], quat)) < 0:
                quat = tuple(-v for v in quat)
            rotations.append(quat)
        num_trans, = c.unpack("H")
        trans_indices = indices(num_trans)
        if num_trans == 0:
            translations = ()
        elif num_trans == 1:
            translations = (c.unpack("fff"),)
        else:
            small, = c.unpack("B")
            if small not in {0, 1}:
                raise ValueError("Invalid XAnim translation encoding")
            minimum, scale = c.unpack("fff"), c.unpack("fff")
            unit = 0.003921568859368563 if small else 0.00001525902189314365
            translations = tuple(tuple(minimum[j] + v * scale[j] * unit for j, v in enumerate(c.unpack("BBB" if small else "HHH")))
                                 for _ in range(num_trans))
        if any(not math.isfinite(x) for v in translations for x in v):
            raise ValueError("Non-finite XAnim translation")
        bones.append(Bone(name, Track(quat_indices, tuple(rotations)), Track(trans_indices, tuple(translations))))
    notify_count, = c.unpack("B")
    events = tuple((c.name(), c.unpack("H")[0]) for _ in range(notify_count))
    if any(frame > frames for _, frame in events):
        raise ValueError("XAnim event outside animation")
    if c.offset != len(data):
        raise ValueError("Unconsumed XAnim export bytes")
    return Animation(version, frames, fps, looped, asset_type, tuple(bones), events)
