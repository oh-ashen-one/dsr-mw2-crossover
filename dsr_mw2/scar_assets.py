"""Owned IW4 SCAR-H + M203 viewmodel conversion. Outputs contain retail data: keep local.

Hands (66 bones) plus the SCAR-H (35) exceed the packet's 90-bone limit, so only
bones that carry vertex weight are packed, remapped into the 76-bone format.
Rifle clips aim with the rifle ADS pose; M203 clips aim with the launcher pose.
"""
import hashlib
import math
from pathlib import Path

from .animation_pose import compose, sample_components
from .animation_retarget import iw4_viewhand_pose
from .intervention_assets import image
from .skin_geometry import undo
from .viewmodel_packet import matrix
from .weapon_articulation import relative_part_pose
from .xanim import read as read_animation
from .xmodel_geometry import read as read_model

PACKET_BONES = 76
# Clip slots used by the native renderer for the SCAR-H (see viewmodel_renderer.cpp).
CLIPS = ('m203_idle', 'm203_fire', 'm203_ads_fire', 'm203_reload', 'm203_reload_empty', 'm203_pullout',
         'm203_putaway', 'ads_up', 'm203_grenade_idle', 'm203_grenade_fire', 'm203_grenade_reload',
         'm203_bullet_2_grenade', 'm203_grenade_2_bullet', 'm203_grenade_ads_up')
LAUNCHER_CLIPS = {'m203_grenade_idle', 'm203_grenade_fire', 'm203_grenade_reload', 'm203_bullet_2_grenade',
                  'm203_grenade_2_bullet', 'm203_grenade_ads_up'}
# scar_gl_mp hideTags: every optional attachment except the M203.
HIDDEN = {'tag_foregrip', 'tag_silencer', 'tag_red_dot', 'tag_thermal_scope', 'tag_sight_off', 'tag_acog_2',
          'tag_shotgun', 'tag_eotech', 'tag_heartbeat'}
MOVING = {'j_gun', 'j_reload', 'tag_clip', 'j_front_ring', 'tag_sight_on', 'j_grenade_m203', 'j_slider_m203', 'tag_m203'}
IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0.)


def visible_faces(model):
    hidden = set()
    for i, b in enumerate(model.bones):
        if b.name in HIDDEN or b.parent in hidden:
            hidden.add(i)
    return tuple(f for f in model.faces if not any(i in hidden and w > .001
                 for c in f.corners for i, w in model.influences[c.vertex]))


def assemble(source, main):
    provenance = []

    def owned(path):
        data = path.read_bytes()
        provenance.append({'file': str(path.relative_to(source)), 'sha256': hashlib.sha256(data).hexdigest()})
        return data
    root = source / 'scar'
    hands = read_model(owned(root / 'model_export/viewmodel_base_viewhands_lod0.xmodel_export').decode())
    gun = read_model(owned(root / 'model_export/viewmodel_scar_h_lod0.xmodel_export').decode())
    if len(hands.bones) != 66 or len(gun.bones) != 35:
        raise ValueError('SCAR-H skeleton revision changed')
    animations = {n: read_animation(owned(root / 'xanim' / ('viewmodel_scar_h_' + n))) for n in CLIPS}
    rifle_idle = sample_components(animations['m203_idle'], 0)
    launcher_idle = sample_components(animations['m203_grenade_idle'], 0)
    rifle_ads = sample_components(animations['ads_up'], animations['ads_up'].frames)
    launcher_ads = sample_components(animations['m203_grenade_ads_up'], animations['m203_grenade_ads_up'].frames)
    attach = next(i for i, b in enumerate(hands.bones) if b.name == 'tag_weapon')
    inverse = tuple(undo(b.global_bind) for b in (*hands.bones, *gun.bones))
    textures, names, raw, draws = [], [], [], []

    def texture(name):
        if name not in names:
            tex, _, proof = image(main, name)
            names.append(name); textures.append(tex); provenance.append(proof)
        return names.index(name)
    for model, offset, faces in [(hands, 0, hands.faces), (gun, 66, visible_faces(gun))]:
        for i, mat in enumerate(model.materials):
            fs = [f for f in faces if f.material == i]
            if not fs:
                continue
            tex = texture(Path(mat.diffuse_reference).stem); first = len(raw)
            for f in fs:
                for c in f.corners:
                    weights = model.influences[c.vertex]
                    raw.append((model.positions[c.vertex], c.normal, c.uv,
                                [j + offset for j, _ in weights], [w for _, w in weights]))
            draws.append((first, len(raw) - first, tex, 0))
    used = sorted({j for *_, idx, w in raw for j, x in zip(idx, w) if x > 0})
    if len(used) > PACKET_BONES:
        raise ValueError('SCAR-H uses more bones than the packet allows: %d' % len(used))
    slot = {old: new for new, old in enumerate(used)}
    vertices = []
    for position, normal, uv, idx, w in raw:
        kept = [(slot[j], x) for j, x in zip(idx, w) if x > 0][:4]
        total = sum(x for _, x in kept)
        indices = [j for j, _ in kept] + [0] * (4 - len(kept))
        values = [x / total for _, x in kept] + [0.] * (4 - len(kept))
        vertices.append((*position, *normal, *uv, *indices, *values))
    clips = []
    for name in CLIPS:
        clip = animations[name]; duration = clip.frames / clip.fps; frames = []
        launcher = name in LAUNCHER_CLIPS
        base, aim = (launcher_idle, launcher_ads) if launcher else (rifle_idle, rifle_ads)
        for i in range(math.ceil(duration * 60) + 1):
            sec = min(i / 60., duration); pairs = []
            for aiming in (False, True):
                current = animations['m203_ads_fire'] if aiming and name == 'm203_fire' else clip
                components = dict(base)
                components.update(sample_components(current, min(sec * current.fps, current.frames)))
                if aiming:
                    components.update(aim)
                handpose = iw4_viewhand_pose(hands.bones, components)
                _, gunpose = relative_part_pose(gun.bones, components, MOVING)
                pose = (*handpose, *[compose(handpose[attach], p) for p in gunpose])
                full = [matrix(compose(p, b)) for p, b in zip(pose, inverse, strict=True)]
                packed = [full[old] for old in used] + [IDENTITY] * (PACKET_BONES - len(used))
                pairs.append(tuple(packed))
            frames.append(tuple(pairs))
        clips.append((duration, tuple(frames)))
    return {'bones': PACKET_BONES, 'vertices': vertices, 'draws': draws, 'textures': textures, 'clips': clips,
            'provenance': provenance, 'texture_names': names, 'hidden_tags': sorted(HIDDEN),
            'packed_bones': [(hands.bones + gun.bones)[j].name for j in used]}
