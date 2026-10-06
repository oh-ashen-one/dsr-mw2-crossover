"""Source-preserving gun articulation math; no renderer or native callback."""
from .animation_pose import Transform, unit
from .skin_geometry import world_transforms


def relative_part_pose(rig, components, moving_names):
    """Author the measured M9's identity-bind moving parts from source offsets.

    MW2's viewmodel moving-part translations are offsets from model pivots.
    Require identity local bind rotations for this bounded adapter; unweighted
    effect/knife bones remain at bind rather than guessing other track modes.
    This is a conversion hypothesis requiring native/source visual review.
    """
    names = {b.name for b in rig}
    if not set(moving_names) <= names:raise ValueError('Unknown moving gun bone')
    local = []
    for bone in rig:
        t = bone.local_bind
        if bone.name in moving_names:
            if abs(t.rotation[3]) < .999999:raise ValueError('Nonidentity moving-part bind rotation needs another adapter')
            sample = components.get(bone.name)
            if sample is not None:
                q = t.rotation if sample['rotation'] is None else unit(sample['rotation'])
                offset = (0.,0.,0.) if sample['translation'] is None else sample['translation']
                t = Transform(q,tuple(a+b for a,b in zip(t.translation,offset,strict=True)))
        local.append(t)
    return tuple(local), world_transforms([b.parent for b in rig],local)
