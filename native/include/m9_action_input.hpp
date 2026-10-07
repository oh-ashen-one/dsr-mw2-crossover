// Pure routing for the qualified, foreground M9 gameplay context.
#pragma once
#include <array>
#include <cstdint>
namespace dsr_mw2 {
inline bool m9_fire_intent(const std::array<std::uint8_t,53>& actions,bool trigger,bool aim_held=false){
    // While L2/RMB aims, DSR holds native action 1 (with 19/21/52) for the aim
    // itself. Counting it as a held trigger hid every R2/R1 press edge.
    return actions[0]||(actions[1]&&!aim_held)||actions[7]||trigger;
}
inline void m9_route_actions(std::array<std::uint8_t,53>& actions,int request,bool reload,bool aim){
    // R2 is native heavy fire (1), including the two-handed crossbow path.
    // Letting it through fires outside the magazine and poisons the aim state.
    for(auto i:{0,1,5,7,37,38,39,40})actions[static_cast<unsigned>(i)]=0;
    if(reload)actions[14]=0;
    if(aim)for(auto i:{19,51,52})actions[static_cast<unsigned>(i)]=0;
    if(request==37||request==38||request==39)actions[static_cast<unsigned>(request)]=1;
}
}
