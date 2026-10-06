// Original input mapping for the M9 controller. No global keyboard polling,
// synthetic input or game-memory writes. Call only from the owned input phase.
#pragma once
#include "m9_handling.hpp"

namespace dsr_mw2 {
struct WeaponControls {
    bool mouse_primary=false, mouse_secondary=false, keyboard_reload=false;
    bool pad_connected=false;
    std::uint8_t left_trigger=0, right_trigger=0;
    std::uint16_t pad_buttons=0; // Standard XInput bits; X = DualSense Square.
};
struct InputContext {
    bool focused=false, gameplay=false, alive=false, right_m9=false;
    Address player=0;
    std::uint64_t load_epoch=0;
};
struct MappedControls {
    bool owned=false, trigger=false, reload=false, aim=false;
};
class M9Input {
public:
    MappedControls map(const InputContext&,const WeaponControls&);
    void apply(Frame&,const InputContext&,const WeaponControls&);
    void reset();
private:
    Address player_=0;
    std::uint64_t epoch_=0;
    bool active_=false, armed_=false, pad_=false, left_=false, right_=false;
};
}
