"""Original bind-relative rotational retarget study, independent of Havok.

This is deliberately not a hand-contact/IK solver. Correspondence, source pose
semantics and the world basis are explicit caller decisions. Target local
translations remain unchanged; unmatched bones retain their local bind pose.
"""
from dataclasses import dataclass
import math
from .animation_pose import Transform, inverse, multiply, unit, slerp
from .skin_geometry import world_transforms


@dataclass(frozen=True)
class OrthogonalBasis:
    """Explicit axis conversion, including a change of handedness.

    A reflection cannot itself be a quaternion. Conjugating a rotation by an
    orthogonal basis maps its imaginary vector by det(C)*C and retains w.
    """
    columns: tuple

    def __post_init__(self):
        c = self.columns
        if len(c) != 3 or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in c):
            raise ValueError("Invalid axis basis")
        for i in range(3):
            for j in range(3):
                if abs(sum(a*b for a,b in zip(c[i],c[j]))-(1 if i==j else 0)) > 1e-8:
                    raise ValueError("Axis basis must be orthonormal")

    @property
    def determinant(self):
        a,b,c=self.columns
        return a[0]*(b[1]*c[2]-b[2]*c[1])-b[0]*(a[1]*c[2]-a[2]*c[1])+c[0]*(a[1]*b[2]-a[2]*b[1])

    def vector(self, v):
        return tuple(sum(self.columns[c][r]*v[c] for c in range(3)) for r in range(3))

    def rotation(self, q):
        q=unit(q)
        v=self.vector(q[:3])
        return unit((*[self.determinant*x for x in v],q[3]))


def retarget_local_rotation(source_idle, source_current, target_idle, source_bone_bind, target_bone_bind, world_basis):
    """Transfer a joint-local change through its authored anatomical axes.

    Useful for finger chains: carrying each finger's world-space delta into a
    differently oriented target grip can tear shared hand webbing. This maps
    the local joint change through each rig's bone frame before applying it to
    the native grip. Parent motion remains owned by the parent joint.
    """
    delta = multiply(inverse(source_idle), source_current)
    world = multiply(multiply(source_bone_bind, delta), inverse(source_bone_bind))
    converted = world_basis.rotation(world)
    local = multiply(multiply(inverse(target_bone_bind), converted), target_bone_bind)
    return multiply(target_idle, local)


def forearm_twist_rotation(forearm, hand_local, anchor_forearm, anchor_hand_local, anchor_twist):
    """Drive DSR's sibling foretwist along the forearm, with half wrist roll.

    DSR's forearm and foretwist share an elbow origin. Copying a source wrist
    swing into this sibling makes forearm-weighted skin point away from the
    wrist. Retain the native relative twist at the anchor; only add axial roll.
    This is an explicit target-rig authoring rule, not a recovered engine rule.
    """
    delta = multiply(hand_local, inverse(anchor_hand_local))
    norm = math.hypot(delta[0], delta[3])
    twist = (delta[0]/norm, 0, 0, delta[3]/norm) if norm > 1e-8 else (0,0,0,1)
    base = multiply(inverse(anchor_forearm), anchor_twist)
    return multiply(forearm, multiply(slerp((0,0,0,1), twist, .5), base))


def retarget_global_rotations(source_bind, source_pose, target_bind, parents, mapping, basis):
    """Map source GLOBAL bind deltas, then resolve target LOCAL rotations.

    Unlike copying local Euler/quaternion values, this works across different
    bone parent layouts. A source bone must be unique in the mapping. The
    caller must mask unmatched target bones when authoring an animation.
    """
    if not source_bind or len(source_bind) != len(source_pose):
        raise ValueError("Mismatched source transforms")
    if not mapping or len(set(mapping.values())) != len(mapping):
        raise ValueError("Empty or ambiguous bone correspondence")
    if any(type(t) is not int or type(s) is not int or not 0 <= t < len(target_bind)
           or not 0 <= s < len(source_bind) for t, s in mapping.items()):
        raise ValueError("Bone correspondence outside skeleton")
    if not isinstance(basis, OrthogonalBasis):
        basis = unit(basis)
    target_world = world_transforms(parents, target_bind)
    desired = {}
    for target, source in mapping.items():
        delta = multiply(source_pose[source].rotation, inverse(source_bind[source].rotation))
        delta = basis.rotation(delta) if isinstance(basis, OrthogonalBasis) else multiply(multiply(basis, delta), inverse(basis))
        desired[target] = multiply(delta, target_world[target].rotation)
    resolved_world, local = {}, {}

    def resolve(i):
        if i in local:
            return
        parent = parents[i]
        if parent >= 0:
            resolve(parent)
        parent_q = resolved_world[parent] if parent >= 0 else (0, 0, 0, 1)
        q = multiply(inverse(parent_q), desired[i]) if i in desired else target_bind[i].rotation
        local[i] = Transform(q, target_bind[i].translation)
        resolved_world[i] = multiply(parent_q, q)

    for i in range(len(target_bind)):
        resolve(i)
    return tuple(local[i] for i in range(len(target_bind)))


def iw4_viewhand_pose(rig, components):
    """Explicit IW4 viewhand interpretation, excluding relative gun bones.

    Existing, unkeyed rig bones retain bind transforms. A named NO_QUAT track
    means identity rotation; NO_TRANS retains the model's local translation.
    Nonzero tracks are absolute parent-local transforms for these viewhands.
    This must not be applied blindly to j_gun children or additive clips.
    """
    if any(b.name.startswith("j_gun") for b in rig):
        raise ValueError("Relative viewmodel gun subtrees need separate interpretation")
    local = []
    for bone in rig:
        if bone.name not in components:
            local.append(bone.local_bind)
            continue
        track = components[bone.name]
        rotation = (0, 0, 0, 1) if track["rotation"] is None else track["rotation"]
        translation = bone.local_bind.translation if track["translation"] is None else track["translation"]
        local.append(Transform(unit(rotation), translation))
    return world_transforms([b.parent for b in rig], local)
