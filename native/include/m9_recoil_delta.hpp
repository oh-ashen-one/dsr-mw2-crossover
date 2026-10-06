// Original lifetime/unit adapter around the attributed IW4 view-kick solver.
// Pure computation only. Native application must qualify camera identity/phase.
#pragma once
#include "iw4_view_kick.hpp"
#include <cmath>
#include <cstdint>

namespace dsr_mw2 {
class M9RecoilDelta {
public:
    struct Delta { float pitch=0,yaw=0; bool valid=false; };
    void reset(){kick.reset();previous={};fraction_ms=0;actor=0;}
    bool shot(std::uint64_t player,int before,int after,int returned,bool identity,float pitch_sample,float yaw_sample,bool sniper=false){
        if(!identity||!player||before<=0||after!=before-1||returned!=after||
           !std::isfinite(pitch_sample)||!std::isfinite(yaw_sample)||
           pitch_sample<0||pitch_sample>1||yaw_sample<0||yaw_sample>1)return false;
        if(actor!=player){reset();actor=player;}
        center=sniper?500.f:750.f;
        return kick.impulse(sniper?30.f+55.f*pitch_sample:25.f+20.f*pitch_sample,sniper?70.f-145.f*yaw_sample:55.f-110.f*yaw_sample);
    }
    Delta step(std::uint64_t player,float dt,bool owned){
        if(!owned||player!=actor||!std::isfinite(dt)||dt<=0||dt>.1f){reset();return {};}
        fraction_ms+=static_cast<double>(dt)*1000.;
        const auto whole=static_cast<int>(fraction_ms);fraction_ms-=whole;
        if(!kick.step(whole,center)){reset();return {};}
        constexpr float radians=.01745329251994329577f;
        const auto now=kick.degrees();
        Delta delta{(now[0]-previous[0])*radians,(now[1]-previous[1])*radians,true};
        previous=now;return delta;
    }
    const std::array<float,3>& degrees()const{return kick.degrees();}
private:
    Iw4ViewKick kick;
    std::array<float,3> previous{};
    double fraction_ms=0;float center=750;
    std::uint64_t actor=0;
};
}
