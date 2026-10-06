"""CPU geometry checks using explicit bind and pose transforms.

This is linear blend skinning, not a game or Havok evaluator. Pose inputs must
be labeled by their source; diagnostic poses do not prove native animation.
Only unit-scale rigid bone transforms are represented here.
"""
from __future__ import annotations

import math

from .animation_pose import Transform, compose, inverse, rotate


IDENTITY = Transform((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))


def point(transform: Transform, value) -> tuple[float, float, float]:
    rotated = rotate(transform.rotation, value)
    if len(transform.translation) != 3 or not all(math.isfinite(v) for v in transform.translation):
        raise ValueError("Invalid transform translation")
    return tuple(a + b for a, b in zip(rotated, transform.translation, strict=True))


def undo(transform: Transform) -> Transform:
    q = inverse(transform.rotation)
    return Transform(q, rotate(q, tuple(-v for v in transform.translation)))


def world_transforms(parents, local) -> tuple[Transform, ...]:
    """Resolve any bounded acyclic hierarchy, including multiple native roots."""
    if not 0 < len(local) <= 512 or len(parents) != len(local):
        raise ValueError("Invalid skeleton length")
    result, visiting = {}, set()

    def resolve(index):
        if index in result:
            return result[index]
        if index in visiting:
            raise ValueError("Cyclic skeleton")
        parent = parents[index]
        if type(parent) is not int or not -1 <= parent < len(local) or parent == index:
            raise ValueError("Invalid parent index")
        visiting.add(index)
        # compose validates quaternion and translation values even for roots.
        result[index] = compose(resolve(parent) if parent >= 0 else IDENTITY, local[index])
        point(result[index], (0.0, 0.0, 0.0))
        visiting.remove(index)
        return result[index]

    return tuple(resolve(i) for i in range(len(local)))


def skin(positions, influences, bind_world, pose_world) -> tuple[tuple[float, float, float], ...]:
    """Deform actual bind-space vertices through P * inverse(B), then blend.

    Influences are global bone-index/weight pairs. Callers must resolve each
    mesh's palette first. Invalid weights fail; they are never silently fixed.
    """
    if (not 0 < len(positions) <= 200_000 or len(influences) != len(positions)
            or not 0 < len(bind_world) <= 512 or len(bind_world) != len(pose_world)):
        raise ValueError("Invalid skinning input dimensions")
    deltas = tuple(compose(pose, undo(bind)) for bind, pose in zip(bind_world, pose_world, strict=True))
    result = []
    for position, weights in zip(positions, influences, strict=True):
        if not 1 <= len(weights) <= 4 or len({i for i, _ in weights}) != len(weights):
            raise ValueError("Invalid vertex influence count")
        if any(type(i) is not int or not 0 <= i < len(deltas) or not math.isfinite(w) or w <= 0 for i, w in weights):
            raise ValueError("Invalid vertex bone or weight")
        if abs(sum(w for _, w in weights) - 1.0) > 1e-4:
            raise ValueError("Vertex weights do not sum to one")
        transformed = [(point(deltas[i], position), weight) for i, weight in weights]
        result.append(tuple(sum(p[axis] * weight for p, weight in transformed) for axis in range(3)))
    return tuple(result)


def dummy_position(local_point, parent_index, attach_index, follows, bind_world, pose_world):
    """Parent bone defines bind space; attach bone supplies the motion delta.

    This documented FLVER authoring convention is an offline hypothesis until
    native playback verifies it. It must not be confused with a live projectile
    spawn position or with applying both current parent and attachment motion.
    """
    if len(bind_world) != len(pose_world) or not bind_world:
        raise ValueError("Invalid dummy skeleton")
    for index in (parent_index, attach_index):
        if type(index) is not int or not -1 <= index < len(bind_world):
            raise ValueError("Invalid dummy bone index")
    reference = point(bind_world[parent_index], local_point) if parent_index >= 0 else point(IDENTITY, local_point)
    if follows and attach_index >= 0:
        return point(compose(pose_world[attach_index], undo(bind_world[attach_index])), reference)
    return reference


def mesh_displacement(before, after) -> float:
    if len(before) != len(after) or not before:
        raise ValueError("Mismatched geometry")
    return max(math.dist(a, b) for a, b in zip(before, after, strict=True))
