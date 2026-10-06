"""Original bounded authoring adapter for the separately approved Havok source.

No helper executable or automatic dependency installation. Single-block studies
require constant scale; translation splines need explicit opt-in. Not an installer.
"""
import math
import struct

from .animation_pose import unit


def single_block_layout(frame_count, track_count, frame_rate):
    if type(frame_count) is not int or not 2 <= frame_count <= 256:
        raise ValueError("Study needs 2..256 frames in one block")
    if type(track_count) is not int or not 1 <= track_count <= 61:
        raise ValueError("Unexpected DSR player track count")
    if not math.isfinite(frame_rate) or not 0 < frame_rate <= 120:
        raise ValueError("Invalid study frame rate")
    return {"numFrames": frame_count, "numBlocks": 1, "maxFramesPerBlock": 256,
            "maskAndQuantizationSize": track_count*4,
            "blockDuration": 255/frame_rate, "blockInverseDuration": frame_rate/255,
            "frameDuration": 1/frame_rate, "blockOffsets": [0]}


def make_spline_study(frames, bone_indices, names, frame_rate, *, translating=False, skeleton_name='Master'):
    """Piecewise-linear rotation splines using the approved 40-bit codec.

    Keep every sampled control point. Compression here is storage format and
    quaternion quantization, not an animation curve simplification heuristic.
    """
    layout = single_block_layout(len(frames), len(bone_indices), frame_rate)
    if len(set(bone_indices)) != len(bone_indices) or any(type(b) is not int or not 0 <= b < 61 for b in bone_indices):
        raise ValueError("Invalid/duplicate native bone binding")
    if len(names) != len(bone_indices) or any(len(f) != len(names) for f in frames):
        raise ValueError("Animation track counts differ")
    if not isinstance(skeleton_name,str) or not 1 <= len(skeleton_name) <= 64 or not skeleton_name.replace('_','').isalnum():
        raise ValueError('Invalid target skeleton identity')
    from soulstruct.havok.spline_compression import (SplineHeader, SplineQuaternion, TrackQuaternion,
        TrackVector3, SplineTransformTrack, SplineCompressedAnimationData, SplineFloat)
    from soulstruct.utilities.binary import BinaryReader
    from soulstruct.havok.utilities.maths import Quaternion
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.dcx import DCXType

    n = len(frames)
    # Degree-one clamped knot vector: duplicate the first and last knots.
    knots = [0, *range(n), n-1]
    header = SplineHeader(BinaryReader(struct.pack("<HB"+"B"*len(knots), n-1, 1, *knots)))
    tracks = []
    for b in range(len(names)):
        initial = frames[0][b]
        for frame in frames:
            if (not translating and tuple(frame[b].translation) != tuple(initial.translation)) or tuple(frame[b].scale) != tuple(initial.scale):
                raise ValueError("This bounded writer does not support translating/scaling tracks")
        channels = []
        for axis in range(3):
            values = [float(frame[b].translation[axis]) for frame in frames]
            if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite translation')
            channels.append(values[0] if all(v == values[0] for v in values) else SplineFloat(values))
        translation = TrackVector3(*channels, header if any(isinstance(v,SplineFloat) for v in channels) else None)
        rotations = []
        for frame in frames:
            q = unit(tuple(frame[b].rotation))
            if rotations and sum(a*c for a,c in zip(rotations[-1], q)) < 0:
                q = tuple(-v for v in q)
            rotations.append(q)
        # An all-identity spline has no rotation flags, but the pinned writer
        # would still emit its spline payload. Represent it as the format's
        # true default track so subsequent track offsets remain valid.
        rotation = (TrackQuaternion(Quaternion((0,0,0,1)))
                    if all(q[:3] == (0,0,0) for q in rotations)
                    else TrackQuaternion(SplineQuaternion(Quaternion(q) for q in rotations), header))
        tracks.append(SplineTransformTrack(
            translation,
            rotation,
            TrackVector3(*tuple(initial.scale))))
    data = SplineCompressedAnimationData([], 0, 0)
    data.blocks = [tracks]
    hkx = AnimationHKX.from_minimal_data_spline(data, n, bone_indices,
        original_skeleton_name=skeleton_name, frame_rate=frame_rate, track_names=names)
    # The pinned constructor contains a fixed 84-track/30-Hz metadata example.
    # Set fields from this actual one-block payload instead of inheriting it.
    animation = hkx.animation_container.hkx_animation
    for name, value in layout.items():
        setattr(animation, name, value)
    animation.floatBlockOffsets = [len(animation.data)]
    hkx.dcx_type = DCXType.Null
    return hkx
