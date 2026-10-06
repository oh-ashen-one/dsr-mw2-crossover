// Original checked angular adapter. No memory access or native calls here.
#pragma once
#include <array>
#include <algorithm>
#include <cmath>

namespace dsr_mw2 {
inline bool m9_camera_angles(const std::array<float,2>& before,
                             float low_degrees,float high_degrees,
                             float pitch_delta,float yaw_delta,
                             std::array<float,2>& after){
    constexpr float radians=.01745329251994329577f;
    const float low=low_degrees*radians,high=high_degrees*radians;
    if(!std::isfinite(before[0])||!std::isfinite(before[1])||
       !std::isfinite(low)||!std::isfinite(high)||low>=high||low< -3.2f||high>3.2f||
       std::fabs(before[0])>3.2f||std::fabs(before[1])>6.4f||
       !std::isfinite(pitch_delta)||!std::isfinite(yaw_delta)||
       std::fabs(pitch_delta)>.1f||std::fabs(yaw_delta)>.1f)return false;
    after={std::clamp(before[0]+pitch_delta,low,high),
           std::remainder(before[1]+yaw_delta,6.2831853071795864769f)};
    return true;
}
}
