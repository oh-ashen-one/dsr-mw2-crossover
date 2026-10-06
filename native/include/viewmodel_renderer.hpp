#pragma once
#include <cstdint>

namespace dsr_mw2 {
struct VmState {
    std::uint64_t player=0,stamp=0;
    int weapon=0,animation=-1,loaded=0;
    float elapsed=0;
    bool visible=false;
};
// Original renderer only. Receives immutable combat observations. It cannot
// create a shot, change health/ammo, move the camera or control game input.
void vm_publish(const VmState& state);
void vm_native_shot(bool last_round);
bool vm_load(const wchar_t* file);
void vm_render(void* swap_chain);
bool vm_visible(std::uint64_t player);
void vm_stop();
}
