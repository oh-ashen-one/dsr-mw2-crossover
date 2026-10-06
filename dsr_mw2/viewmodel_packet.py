"""Original local-only MW2 viewmodel packet and CPU pose authoring.

The packet contains owned retail geometry/textures: never commit its output.
No DSR animation, damage, inventory or save is changed by this converter.
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import struct
from zipfile import ZipFile

from PIL import Image

from .animation_pose import compose, rotate, sample_components
from .animation_retarget import iw4_viewhand_pose
from .skin_geometry import undo
from .weapon_articulation import relative_part_pose
from .weapon_textures import iwi_blocks, dds_header
from .xmodel_geometry import read as read_model
from .xanim import read as read_animation

MAGIC = b'DSRVM001'
CLIPS = ('idle', 'fire', 'lastfire', 'reload', 'reload_empty2', 'pullout', 'putaway')
MOVING = {'j_gun', 'j_bolt', 'j_press_rear', 'tag_clip', 'tag_silencer'}
TEXTURES = (
    ('iw_02.iwd', 'us_army_glove_col'),
    ('iw_02.iwd', 'us_army_sleeve_gps_col'),
    ('iw_02.iwd', 'us_army_alpha_col'),
    ('iw_03.iwd', 'weapon_beretta_c'),
    ('iw_03.iwd', 'weapon_trinium_site_c'),
    ('iw_03.iwd', 'weapon_suppressor_01_col'),
)


def matrix(t):
    columns = [rotate(t.rotation, v) for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    return tuple(v for r in range(3) for v in (*[c[r] for c in columns], t.translation[r]))


def assemble(source: Path, main: Path):
    provenance = []

    def owned(path):
        data = path.read_bytes()
        provenance.append({'file': str(path.relative_to(source)), 'sha256': hashlib.sha256(data).hexdigest()})
        return data

    models = source / 'm9-handling-models/model_export'
    hands = read_model(owned(models / 'viewmodel_base_viewhands_lod0.xmodel_export').decode())
    gun = read_model(owned(models / 'viewmodel_beretta_lod0.xmodel_export').decode())
    if len(hands.bones) != 66 or len(gun.bones) != 10:
        raise ValueError('Pinned M9/viewhands skeleton changed')
    animation = source / 'm9-handling-animation/xanim'
    animations = {name: read_animation(owned(animation / ('viewmodel_beretta_' + name)))
                  for name in (*CLIPS, 'ads_up', 'fire_ads')}
    ads = sample_components(animations['ads_up'], animations['ads_up'].frames)
    idle = sample_components(animations['idle'], 0)
    attach = next(i for i, b in enumerate(hands.bones) if b.name == 'tag_weapon')
    binds = tuple(b.global_bind for b in (*hands.bones, *gun.bones))
    inverse_binds = tuple(undo(b) for b in binds)
    vertices, draws = [], []
    # Original material references are checked; they never become disk paths.
    mappings = ((hands, 0, (0, 1, 2, 1)), (gun, len(hands.bones), (3, 4, 3, 5)))
    for model, offset, materials in mappings:
        for material, texture in enumerate(materials):
            first = len(vertices)
            for face in model.faces:
                if face.material != material:
                    continue
                for corner in face.corners:
                    weights = model.influences[corner.vertex]
                    indices = [i + offset for i, _ in weights]
                    values = [w for _, w in weights]
                    vertices.append((*model.positions[corner.vertex], *corner.normal, *corner.uv,
                                     *(indices + [0] * (4-len(indices))), *(values + [0.] * (4-len(values)))))
            if len(vertices) != first:
                draws.append((first, len(vertices)-first, texture, int(model is gun and material == 3)))

    textures = []
    for archive, name in TEXTURES:
        with ZipFile(main / archive) as z:
            data = z.read('images/' + name + '.iwi')
        fmt, mips = iwi_blocks(data)
        w, h, blocks = mips[0]
        with Image.open(io.BytesIO(dds_header(w, h, b'DXT1' if fmt == 11 else b'DXT5', len(blocks), 1)+blocks)) as im:
            rgba = im.convert('RGBA').tobytes()
        textures.append((w, h, rgba))
        provenance.append({'archive': archive, 'entry': 'images/'+name+'.iwi',
                           'sha256': hashlib.sha256(data).hexdigest()})

    clips = []
    for name in CLIPS:
        clip = animations[name]
        duration = max(clip.frames / clip.fps, animations['fire_ads'].frames / animations['fire_ads'].fps) if name == 'fire' else clip.frames / clip.fps
        count = max(1, math.ceil(duration * 60) + 1)
        frames = []
        for index in range(count):
            seconds = min(index / 60., duration)
            pairs = []
            for aiming in (False, True):
                current = animations['fire_ads'] if aiming and name == 'fire' else clip
                components = dict(idle)
                components.update(sample_components(current, min(seconds * current.fps, current.frames)))
                if aiming:
                    # ADS is an authored parent transform, not a second skeleton.
                    components.update(ads)
                hand_pose = iw4_viewhand_pose(hands.bones, components)
                _, gun_pose = relative_part_pose(gun.bones, components, MOVING)
                pose = (*hand_pose, *[compose(hand_pose[attach], p) for p in gun_pose])
                pairs.append(tuple(matrix(compose(p, b)) for p, b in zip(pose, inverse_binds, strict=True)))
            frames.append(tuple(pairs))
        clips.append((duration, tuple(frames)))
    return {'bones': len(binds), 'vertices': vertices, 'draws': draws, 'textures': textures,
            'clips': clips, 'provenance': provenance, 'source_models': (hands, gun)}


def encode(packet):
    p = packet
    data = bytearray(MAGIC)
    data += struct.pack('<6I', 1, p['bones'], len(p['vertices']), len(p['draws']), len(p['textures']), len(p['clips']))
    for v in p['vertices']:
        data += struct.pack('<8f4H4f', *v)
    for d in p['draws']:
        data += struct.pack('<4I', *d)
    for w, h, rgba in p['textures']:
        if len(rgba) != w*h*4:
            raise ValueError('Invalid texture size')
        data += struct.pack('<2I', w, h) + rgba
    for duration, frames in p['clips']:
        data += struct.pack('<If', len(frames), duration)
        for frame in frames:
            for pose in frame:
                for bone in pose:
                    data += struct.pack('<12f', *bone)
    return bytes(data)
