// Original per-weapon handling table for the native MW2 guns. One place decides
// magazine size, fire interval, fire mode and reload model for each weapon ID;
// the SCAR-H carries a second profile for its underbarrel M203 launcher mode.
#pragma once
#include <cstdint>

namespace dsr_mw2 {
enum class GunKind : std::uint8_t { m9, intervention, scar, scar_launcher };

struct GunProfile {
    GunKind kind;
    int capacity;            // rounds per magazine
    double interval;         // minimum seconds between shots
    bool automatic;          // held trigger keeps firing at `interval`
    bool timed_reload;       // authored MW2 reload duration after native acknowledgement
    double reload_credit;    // seconds into a timed reload when rounds are credited
    double reload_end;       // tactical reload duration
    double empty_reload_end; // empty reload duration
};

constexpr std::int32_t scar_weapon = 9300000;

// M9 values are the qualified native-verified reload; Intervention values are the
// authored MW2 timings. SCAR-H values are provisional until its weapon file is read.
inline constexpr GunProfile m9_profile{GunKind::m9, 15, .08, false, false, 0, 0, 0};
inline constexpr GunProfile intervention_profile{GunKind::intervention, 5, .916, false, true, 1.8, 2.268, 3.867};
inline constexpr GunProfile scar_profile{GunKind::scar, 20, .1, true, true, 1.6, 2.4, 3.0};
inline constexpr GunProfile scar_launcher_profile{GunKind::scar_launcher, 1, .5, false, true, 1.8, 2.6, 2.6};

inline bool is_scar(std::int32_t weapon) { return weapon == scar_weapon; }

inline const GunProfile& gun_profile(std::int32_t weapon, bool launcher = false) {
    if (weapon == 9200000) return intervention_profile;
    if (is_scar(weapon)) return launcher ? scar_launcher_profile : scar_profile;
    return m9_profile;
}
} // namespace dsr_mw2
