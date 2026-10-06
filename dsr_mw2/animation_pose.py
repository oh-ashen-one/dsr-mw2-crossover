"""Original CPU pose math for MW2-to-DSR preparation, without Havok dependencies.

XMODEL_EXPORT v6 stores global bind offsets and rotation matrix COLUMNS (verified
in pinned OAT XModelExportWriter). Animation samples retain source components;
asset_type semantics are not silently reinterpreted as DSR local transforms.
"""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass
import math
import re
from .xanim import Animation, Track


def unit(q):
    if len(q) != 4 or not all(math.isfinite(v) for v in q):
        raise ValueError("Invalid quaternion")
    length = math.sqrt(sum(v * v for v in q))
    if length < 1e-12:
        raise ValueError("Zero quaternion")
    return tuple(v / length for v in q)


def inverse(q):
    x, y, z, w = unit(q)
    return -x, -y, -z, w


def multiply(a, b):
    x, y, z, w = unit(a)
    i, j, k, r = unit(b)
    return unit((w*i+x*r+y*k-z*j, w*j-x*k+y*r+z*i,
                 w*k+x*j-y*i+z*r, w*r-x*i-y*j-z*k))


def rotate(q, vector):
    if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
        raise ValueError("Invalid vector")
    x, y, z, w = unit(q)
    a, b, c = vector
    tx, ty, tz = 2*(y*c-z*b), 2*(z*a-x*c), 2*(x*b-y*a)
    return a+w*tx+y*tz-z*ty, b+w*ty+z*tx-x*tz, c+w*tz+x*ty-y*tx


def slerp(a, b, weight):
    if not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError("Invalid interpolation weight")
    a, b = unit(a), unit(b)
    dot = sum(x*y for x, y in zip(a, b, strict=True))
    if dot < 0:
        b, dot = tuple(-v for v in b), -dot
    if dot > 0.9995:
        return unit(tuple(x+(y-x)*weight for x, y in zip(a, b, strict=True)))
    angle = math.acos(max(-1, min(1, dot)))
    left, right = math.sin((1-weight)*angle), math.sin(weight*angle)
    return unit(tuple((x*left+y*right)/math.sin(angle) for x, y in zip(a, b, strict=True)))


def quaternion_from_columns(columns, *, tolerance=1e-4):
    if not 0 < tolerance <= 2e-4:
        raise ValueError("Excessive matrix repair tolerance")
    if len(columns) != 3 or any(len(c) != 3 or not all(math.isfinite(x) for x in c) for c in columns):
        raise ValueError("Invalid rotation matrix")
    # Reject reflections/scales instead of normalizing them into a plausible pose.
    for i in range(3):
        for j in range(3):
            dot = sum(a*b for a, b in zip(columns[i], columns[j], strict=True))
            if abs(dot - (1 if i == j else 0)) > tolerance:
                raise ValueError("Nonorthonormal bind rotation")
    m = [[columns[c][r] for c in range(3)] for r in range(3)]
    det = (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1]) -
           m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0]) +
           m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    if abs(det-1) > tolerance:
        raise ValueError("Bind rotation is a reflection")
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace+1) * 2
        q = ((m[2][1]-m[1][2])/s, (m[0][2]-m[2][0])/s, (m[1][0]-m[0][1])/s, s/4)
    else:
        i = max(range(3), key=lambda k: m[k][k])
        j, k = (i+1) % 3, (i+2) % 3
        s = math.sqrt(1 + m[i][i] - m[j][j] - m[k][k]) * 2
        v = [0.0, 0.0, 0.0, (m[k][j]-m[j][k])/s]
        v[i], v[j], v[k] = s/4, (m[j][i]+m[i][j])/s, (m[k][i]+m[i][k])/s
        q = tuple(v)
    return unit(q)


@dataclass(frozen=True)
class Transform:
    rotation: tuple[float, float, float, float]
    translation: tuple[float, float, float]


def compose(parent: Transform, child: Transform) -> Transform:
    t = rotate(parent.rotation, child.translation)
    return Transform(multiply(parent.rotation, child.rotation), tuple(a+b for a, b in zip(parent.translation, t, strict=True)))


def relative(parent: Transform, child: Transform) -> Transform:
    inv = inverse(parent.rotation)
    return Transform(multiply(inv, child.rotation), rotate(inv, tuple(a-b for a, b in zip(child.translation, parent.translation, strict=True))))


@dataclass(frozen=True)
class RigBone:
    name: str
    parent: int
    global_bind: Transform
    local_bind: Transform


def read_rig(text: str) -> tuple[RigBone, ...]:
    if len(text) > 16*1024*1024:
        raise ValueError("Oversized model export")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("//")]
    if lines[:2] != ["MODEL", "VERSION 6"] or len(lines) < 3:
        raise ValueError("Expected XMODEL_EXPORT v6")
    count_match = re.fullmatch(r"NUMBONES (\d+)", lines[2])
    if not count_match or not 1 <= int(count_match[1]) <= 512:
        raise ValueError("Invalid model bone count")
    count = int(count_match[1])
    if len(lines) < 3 + count*7:
        raise ValueError("Truncated model rig")
    definitions = []
    for i, line in enumerate(lines[3:3+count]):
        m = re.fullmatch(r'BONE (\d+) (-?\d+) "([A-Za-z0-9_]+)"', line)
        if not m or int(m[1]) != i or not -1 <= int(m[2]) < i:
            raise ValueError("Invalid or non-topological model hierarchy")
        definitions.append((m[3], int(m[2])))
    if len({name for name, _ in definitions}) != count:
        raise ValueError("Duplicate rig name")
    bones = []
    for i, (name, parent) in enumerate(definitions):
        start = 3 + count + i*6
        if lines[start] != f"BONE {i}":
            raise ValueError("Missing bone transform")
        vectors = []
        for offset, label in enumerate(("OFFSET", "SCALE", "X", "Y", "Z"), 1):
            prefix = label + " "
            if not lines[start+offset].startswith(prefix):
                raise ValueError("Missing transform component")
            values = tuple(float(v.strip()) for v in lines[start+offset][len(prefix):].split(","))
            if len(values) != 3 or not all(math.isfinite(x) for x in values):
                raise ValueError("Invalid bind transform")
            vectors.append(values)
        if any(abs(v-1) > 1e-6 for v in vectors[1]):
            raise ValueError("Scaled rigs require explicit scale retargeting")
        # Owned viewhands export has measured max orthogonality error .000187
        # and determinant error .000191. OAT emits unnormalized baseMat quats as
        # six-decimal matrices. Permit only this narrow drift, then unitize q.
        global_bind = Transform(quaternion_from_columns(vectors[2:], tolerance=2e-4), vectors[0])
        local = relative(bones[parent].global_bind, global_bind) if parent >= 0 else global_bind
        bones.append(RigBone(name, parent, global_bind, local))
    return tuple(bones)


def sample_track(track: Track, frame: float, *, rotation: bool):
    """Return None for absent tracks. Never invent a bind/identity component."""
    if not math.isfinite(frame) or frame < 0:
        raise ValueError("Invalid animation sample frame")
    if len(track.indices) != len(track.values) or any(a >= b for a, b in zip(track.indices, track.indices[1:])):
        raise ValueError("Invalid animation track")
    if not track.indices:
        return None
    size = 4 if rotation else 3
    if track.indices[0] < 0 or any(len(v) != size or not all(math.isfinite(x) for x in v) for v in track.values):
        raise ValueError("Invalid animation values")
    if len(track.indices) == 1 or frame <= track.indices[0]:
        return unit(track.values[0]) if rotation else track.values[0]
    if frame >= track.indices[-1]:
        return unit(track.values[-1]) if rotation else track.values[-1]
    index = bisect_right(track.indices, frame) - 1
    a, b = track.values[index:index+2]
    weight = (frame-track.indices[index])/(track.indices[index+1]-track.indices[index])
    if rotation:
        return slerp(a, b, weight)
    return tuple(x+(y-x)*weight for x, y in zip(a, b, strict=True))


def sample_components(animation: Animation, frame: float) -> dict:
    if not math.isfinite(frame) or not 0 <= frame <= animation.frames:
        raise ValueError("Frame outside source clip")
    return {bone.name: {"rotation": sample_track(bone.rotation, frame, rotation=True),
                        "translation": sample_track(bone.translation, frame, rotation=False)}
            for bone in animation.bones}


def retarget_rotation(source_bind, source_animated, target_bind, basis):
    """Map a LOCAL bind-relative rotation using an explicit source->target basis.

    Does not guess basis, bone correspondence, translation scale, additive-track
    semantics or upper-body masks. Those require real target skeleton evidence.
    """
    delta = multiply(inverse(source_bind), source_animated)
    converted = multiply(multiply(basis, delta), inverse(basis))
    return multiply(target_bind, converted)
