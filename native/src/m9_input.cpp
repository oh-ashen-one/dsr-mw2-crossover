#include "m9_input.hpp"

namespace dsr_mw2 {
void M9Input::reset(){*this=M9Input{};}
MappedControls M9Input::map(const InputContext& context,const WeaponControls& raw){
    if(!context.focused||!context.gameplay||!context.alive||!context.right_m9||!context.player){reset();return {};}
    const bool identity_changed=!active_||context.player!=player_||context.load_epoch!=epoch_;
    const bool device_changed=active_&&pad_!=raw.pad_connected;
    if(identity_changed||device_changed){
        reset();active_=true;player_=context.player;epoch_=context.load_epoch;pad_=raw.pad_connected;
    }
    // Trigger hysteresis avoids repeated firing/ADS changes around a threshold.
    // A release below 20 is required after a press at 30 or above.
    auto trigger=[](std::uint8_t value,bool held){return held?value>20:value>=30;};
    left_=raw.pad_connected&&trigger(raw.left_trigger,left_);
    right_=raw.pad_connected&&trigger(raw.right_trigger,right_);
    const bool fire=raw.mouse_primary||right_;
    const bool aim=raw.mouse_secondary||left_;
    const bool reload=raw.keyboard_reload||(raw.pad_connected&&(raw.pad_buttons&0x4000));
    // Reacquiring focus/character/weapon/device cannot turn a held control into
    // a shot or reload. All weapon controls must return to neutral first.
    if(!armed_){armed_=!fire&&!aim&&!reload;return {true,false,false,false};}
    return {true,fire,reload,aim};
}
void M9Input::apply(Frame& frame,const InputContext& context,const WeaponControls& raw){
    const auto controls=map(context,raw);
    frame.focused=context.focused;
    frame.gameplay=context.gameplay&&context.alive&&context.right_m9&&controls.owned;
    frame.load_epoch=context.load_epoch;
    frame.trigger=controls.trigger;frame.reload=controls.reload;frame.aim=controls.aim;
}
}
