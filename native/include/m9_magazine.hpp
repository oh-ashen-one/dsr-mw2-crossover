// Original integration pilot: native inventory remains the authoritative total.
// Magazine rounds are a subset of that total, consumed only by native receipts.
// No inventory/save mutation. Reload credits follow native animation progress.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
namespace dsr_mw2 {
inline unsigned m9_action_slot(const std::array<std::int32_t,31>& animations){
    // General damage/evade/reload takes precedence. The verified upper-body
    // channel can own only these scoped M9 actions when general is inactive.
    if(animations[7]>=0)return 7;
    const auto upper=animations[5];
    return upper==463000||upper==465500||upper==465501||upper==465502?5U:7U;
}
struct MagazineFrame {
    std::uint64_t player=0;
    int total=0,hp=0,animation=-1;
    double elapsed=0,now=0;
    bool focused=false,fire=false,reload=false,interrupted=false;
    std::uint64_t loadout=0;
};
class M9Magazine {
public:
    int loaded=0;bool fault=false,reloading=false,credited=false;
    int step(const MagazineFrame& f){
        // A death/unload cannot retain rounds or an in-flight reload credit.
        // Focus loss only disarms input; native total still bounds the magazine.
        if(!f.player||!f.hp){*this=M9Magazine{};fire=f.fire;reload=f.reload;return 0;}
        if(!f.focused){armed=false;fire=f.fire;reload=f.reload;cancel();return 0;}
        if(player!=f.player||loadout!=f.loadout){*this=M9Magazine{};player=f.player;loadout=f.loadout;hp=f.hp;}
        loaded=std::min(loaded,std::max(0,f.total));
        if(!armed){fire=f.fire;reload=f.reload;if(!fire&&!reload)armed=true;hp=f.hp;return 0;}
        const bool fire_edge=f.fire&&!fire,reload_edge=f.reload&&!reload;
        fire=f.fire;reload=f.reload;
        if(f.hp<hp||f.interrupted){cancel();hp=f.hp;return 0;}hp=f.hp;
        if(fault)return 0;
        if(reloading){
            if(f.animation==reload_animation){
                if(!seen){seen=true;last_progress=-1;}
                else if(last_progress<0){
                    // The first changed-ID sample can retain the old clip time.
                    if(std::isfinite(f.elapsed)&&f.elapsed>=0&&f.elapsed<.15)last_progress=f.elapsed;
                    else if(f.now-request_time>.3)cancel();
                }else if(!std::isfinite(f.elapsed)||f.elapsed+.001<last_progress||f.elapsed-last_progress>.25)cancel();
                else{
                    last_progress=f.elapsed;
                    if(!credited&&f.elapsed>=1.2){loaded=std::min(15,f.total);credited=true;}
                }
            }else if(seen){
                // Ending or interruption never fabricates progress/ammo credit.
                cancel();
            }else if(f.now-request_time>.3)cancel();
            return 0;
        }
        const bool ready=f.animation<0||f.animation==465500||(f.animation==463000&&f.elapsed>=.08);
        if(reload_edge&&loaded<std::min(15,f.total)&&ready){
            reloading=true;seen=false;credited=false;last_progress=-1;request_time=f.now;
            reload_animation=loaded?465502:465501;return loaded?38:39;
        }
        if(fire_edge&&loaded>0&&ready&&f.now-last_shot>=.08)return 37;
        return 0;
    }
    void consume(std::uint64_t actor,int before,int after,int result,double now){
        if(actor!=player)return;
        if(before<=0||after!=before-1||result!=after){fault=true;cancel();return;}
        // A real native shot can finish after a loadout/focus transition, when
        // our virtual magazine is empty. Keep the authoritative decrement,
        // require release/reload, and retain ADS; never invent a round or turn
        // a valid receipt into a permanent aiming fault.
        if(loaded<=0){loaded=0;armed=false;cancel();last_shot=now;return;}
        --loaded;last_shot=now;
    }
    void cancel(){reloading=false;seen=false;credited=false;last_progress=-1;}
private:
    std::uint64_t player=0,loadout=0;int hp=0,reload_animation=-1;
    bool armed=false,fire=false,reload=false,seen=false;
    double last_shot=-10,request_time=0,last_progress=-1;
};
}
