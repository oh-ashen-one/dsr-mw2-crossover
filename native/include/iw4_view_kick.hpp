// Adapted from IW4L kick.rs; Apache-2.0. See native/third_party/IW4L-NOTICE.txt.
// This component computes angles only; it neither hooks nor writes a camera.
#pragma once
#include <array>

namespace dsr_mw2 {
class Iw4ViewKick {
public:
    // MW2 view-kick inputs are angular-velocity impulses, not angle offsets.
    bool impulse(float pitch, float yaw);
    bool step(int frame_ms, float center_speed);
    void reset() { *this = Iw4ViewKick{}; }
    const std::array<float, 3>& degrees() const { return angles_; }
    const std::array<float, 3>& velocity() const { return velocity_; }
private:
    std::array<float, 3> angles_{}, velocity_{};
};
}
