"""Offline anatomical palm frames; no game state or animation I/O."""
import math
from .animation_pose import quaternion_from_columns, multiply, inverse
from .pose_ik import normalized, sub, mul, dot, cross


def palm_frame(index_from_wrist, thumb_from_wrist):
    """Right-handed frame: wrist-to-index, perpendicular thumb, palm normal.

    Bone quaternion axes are not assumed to be anatomical. Two non-collinear
    landmarks are needed to disambiguate palm roll as well as pointing.
    """
    if not all(math.isfinite(v) for p in (index_from_wrist,thumb_from_wrist) for v in p):
        raise ValueError('Nonfinite palm landmark')
    forward=normalized(index_from_wrist)
    lateral=normalized(sub(thumb_from_wrist,mul(forward,dot(thumb_from_wrist,forward))))
    return quaternion_from_columns((forward,lateral,cross(forward,lateral)))


def palm_rotation(native_index_local,native_thumb_local,desired_index_world,desired_thumb_world):
    """Orient the native hand by actual palm landmarks, retaining bone lengths."""
    return multiply(palm_frame(desired_index_world,desired_thumb_world),
                    inverse(palm_frame(native_index_local,native_thumb_local)))
