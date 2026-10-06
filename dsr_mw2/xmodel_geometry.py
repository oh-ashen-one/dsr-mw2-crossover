"""Bounded original reader for the pinned OAT XMODEL_EXPORT v6 geometry.

Positions/influences belong to merged source vertices. Face corners retain
independent normals, UVs and colors; seams must not be merged by position.
Material image paths are metadata only and are never opened by this reader.
"""
from dataclasses import dataclass
import math
import re
import shlex

from .animation_pose import RigBone, read_rig


@dataclass(frozen=True)
class Corner:
    vertex: int
    normal: tuple
    color: tuple
    uv: tuple


@dataclass(frozen=True)
class Face:
    object: int
    material: int
    corners: tuple[Corner, Corner, Corner]


@dataclass(frozen=True)
class Material:
    name: str
    kind: str
    diffuse_reference: str


@dataclass(frozen=True)
class Model:
    bones: tuple[RigBone, ...]
    positions: tuple
    influences: tuple
    faces: tuple[Face, ...]
    objects: tuple[str, ...]
    materials: tuple[Material, ...]


def read(text: str) -> Model:
    bones = read_rig(text)
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('//')]
    cursor = 3 + len(bones) * 7

    def take():
        nonlocal cursor
        if cursor >= len(lines):raise ValueError('Truncated XMODEL geometry')
        line = lines[cursor]; cursor += 1
        return line

    def count(label, maximum, *, zero=False):
        m = re.fullmatch(re.escape(label)+r' (\d+)', take())
        if not m or not (0 if zero else 1) <= int(m[1]) <= maximum:
            raise ValueError('Invalid '+label)
        return int(m[1])

    def values(label, size, *, commas=False):
        line = take()
        if not line.startswith(label+' '):raise ValueError('Missing '+label)
        fields = line[len(label)+1:].split(',') if commas else line[len(label)+1:].split()
        try: result = tuple(float(v) for v in fields)
        except ValueError:raise ValueError('Invalid '+label) from None
        if len(result) != size or not all(math.isfinite(v) for v in result):
            raise ValueError('Invalid '+label)
        return result

    positions = []; influences = []
    for i in range(count('NUMVERTS', 200_000)):
        if take() != f'VERT {i}':raise ValueError('Nonsequential source vertex')
        positions.append(values('OFFSET', 3, commas=True))
        weights = []
        for _ in range(count('BONES', 4)):
            fields = take().split()
            if len(fields) != 3 or fields[0] != 'BONE' or not fields[1].isdigit():
                raise ValueError('Invalid vertex influence')
            index, weight = int(fields[1]), float(fields[2])
            if not 0 <= index < len(bones) or not math.isfinite(weight) or not 0 < weight <= 1:
                raise ValueError('Invalid vertex influence')
            weights.append((index, weight))
        if len({i for i, _ in weights}) != len(weights) or abs(sum(w for _, w in weights)-1) > 1e-4:
            raise ValueError('Ambiguous or unnormalized source influences')
        influences.append(tuple(weights))
    faces = []
    for _ in range(count('NUMFACES', 400_000)):
        fields = take().split()
        if len(fields) != 5 or fields[0] != 'TRI' or fields[-2:] != ['0', '0'] or not all(v.isdigit() for v in fields[1:3]):
            raise ValueError('Unsupported triangle record')
        corners = []
        for _ in range(3):
            vertex = count('VERT', len(positions)-1, zero=True)
            normal, color, uv = values('NORMAL', 3), values('COLOR', 4), values('UV 1', 2)
            if not .9 <= math.sqrt(sum(v*v for v in normal)) <= 1.1 or any(not 0 <= v <= 1 for v in color):
                raise ValueError('Invalid corner normal/color')
            corners.append(Corner(vertex, normal, color, uv))
        # OAT can merge equal position/influence records even when a source
        # face has zero area. Preserve those corners; report them at conversion.
        faces.append(Face(int(fields[1]), int(fields[2]), tuple(corners)))
    objects = []
    for i in range(count('NUMOBJECTS', 4096)):
        fields = shlex.split(take())
        if len(fields) != 3 or fields[:2] != ['OBJECT', str(i)] or not fields[2]:
            raise ValueError('Invalid object definition')
        objects.append(fields[2])
    materials = []
    attributes = (('COLOR',4), ('TRANSPARENCY',4), ('AMBIENTCOLOR',4), ('INCANDESCENCE',4),
                  ('COEFFS',2), ('GLOW',2), ('REFRACTIVE',2), ('SPECULARCOLOR',4),
                  ('REFLECTIVECOLOR',4), ('REFLECTIVE',2), ('BLINN',2), ('PHONG',1))
    for i in range(count('NUMMATERIALS', 4096)):
        fields = shlex.split(take())
        if len(fields) != 5 or fields[:2] != ['MATERIAL',str(i)] or not all(fields[2:]):
            raise ValueError('Invalid material definition')
        materials.append(Material(*fields[2:]))
        for label, size in attributes:values(label, size)
    if cursor != len(lines):raise ValueError('Unparsed trailing XMODEL records')
    if any(f.object >= len(objects) or f.material >= len(materials) for f in faces):
        raise ValueError('Triangle references undefined object/material')
    return Model(bones, tuple(positions), tuple(influences), tuple(faces), tuple(objects), tuple(materials))
