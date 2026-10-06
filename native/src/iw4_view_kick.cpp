// C++ adaptation of weapon_fire_recoil (view part), kick_angles_step_axis and
// kick_angles from IW4L / 2010-rust-rewrite-mashup, commit f608f85e407ff1b7689d54a9aafdd16e95711ac4.
// Copyright 2026 vladtrc. Licensed under Apache-2.0; see native/third_party.
// Changes: bounded input checks, M9's no-perk impulse interface, C++ state API.
#include "iw4_view_kick.hpp"
#include <cmath>

namespace dsr_mw2 {
bool Iw4ViewKick::impulse(float pitch, float yaw) {
    if (!std::isfinite(pitch) || !std::isfinite(yaw) || std::abs(pitch) > 1000 || std::abs(yaw) > 1000)
        return false;
    velocity_[0] = -pitch;
    velocity_[1] = yaw;
    velocity_[2] = yaw * -0.5f;
    return true;
}

static void axis(float& angle, float& velocity, float dt, float center_speed) {
    if (velocity == 0 && angle == 0) return;
    if (angle != 0) velocity += (angle <= 0 ? 1.0f : -1.0f) * center_speed * dt;
    float change = velocity * dt;
    if (angle * change < 0) change *= 0.06f;
    const float next = angle + change;
    if (next * angle < 0) {
        angle = velocity = 0;
    } else {
        angle = next;
        if (angle == 0) velocity = 0;
        else if (std::abs(angle) > 10.0f) {
            angle = angle <= 0 ? -10.0f : 10.0f;
            velocity = 0;
        }
    }
}

bool Iw4ViewKick::step(int frame_ms, float center_speed) {
    if (frame_ms < 0 || frame_ms > 250 || !std::isfinite(center_speed) || center_speed <= 0 || center_speed > 10000)
        return false;
    for (int time = frame_ms; time > 0; time -= 5) {
        const float dt = static_cast<float>(time < 5 ? time : 5) * 0.001f;
        for (std::size_t i = 0; i < angles_.size(); ++i) axis(angles_[i], velocity_[i], dt, center_speed);
    }
    return true;
}
}
