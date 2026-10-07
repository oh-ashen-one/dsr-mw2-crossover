#pragma once
#include <cstdint>

namespace dsr_mw2 {
struct VmState {
    std::uint64_t player=0,stamp=0;
    int weapon=0,animation=-1,loaded=0;
    float elapsed=0;
    bool visible=false;
    bool reloading=false,empty_reload=false;
    float reload_elapsed=0,ads=1;
    bool launcher=false;           // SCAR-H M203 mode
    std::uint64_t mode_changed=0;  // tick of the last rifle/M203 toggle
};
// Original renderer only. Receives immutable combat observations. It cannot
// create a shot, change health/ammo, move the camera or control game input.
void vm_publish(const VmState& state);
void vm_native_shot(bool last_round);
// Slots: 0 M9 (76 bones, 7 clips), 1 Intervention (90, 9), 2 SCAR-H (76, 14).
bool vm_load(const wchar_t* file,unsigned slot=0);
void vm_render(void* swap_chain);
bool vm_visible(std::uint64_t player);
void vm_stop();
}
