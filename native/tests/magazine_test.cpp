#include "m9_magazine.hpp"
#include <cassert>
using namespace dsr_mw2;
int main(){
    std::array<std::int32_t,31> slots{};slots.fill(-1);
    assert(m9_action_slot(slots)==7);
    for(auto action:{463000,465500,465501,465502}){
        slots[5]=action;assert(m9_action_slot(slots)==5);
        slots[7]=690;assert(m9_action_slot(slots)==7);slots[7]=-1;
    }
    slots[5]=200081;assert(m9_action_slot(slots)==7);
    M9Magazine m;MagazineFrame f;f.player=1;f.hp=100;f.total=85;f.focused=true;m.step(f);m.step(f);
    // Empty trigger starts native reload, with no credit from the request.
    f.now=.1;f.fire=true;assert(m.step(f)==39);assert(m.loaded==0&&m.reloading);
    f.fire=false;f.animation=465501;f.elapsed=1.3;m.step(f);assert(m.loaded==0);
    f.elapsed=.02;f.now=.12;m.step(f);
    for(int i=1;i<8;++i){f.elapsed=.02+i*.2;f.now=.12+i*.2;m.step(f);}
    assert(m.loaded==15);f.animation=-1;f.now=2.1;m.step(f);assert(!m.reloading);
    f.fire=true;assert(m.step(f)==37);m.consume(1,85,84,84,2.1);assert(m.loaded==14);assert(m.step(f)==0);
    f.fire=false;f.total=84;m.step(f);f.reload=true;f.now=2.5;assert(m.step(f)==38);
    f.reload=false;f.animation=465502;f.elapsed=1.5;m.step(f);f.elapsed=.02;f.now=2.52;m.step(f);
    f.hp=90;f.now=2.6;f.elapsed=.1;m.step(f);assert(!m.reloading&&m.loaded==14);
    m.consume(1,84,83,99,3);assert(m.fault&&m.loaded==14);
    f.player=2;f.fire=false;m.step(f);assert(!m.fault&&m.loaded==0);
    // A sustained ready pose must remain eligible for reload and firing.
    f.reload=false;f.animation=465500;f.now=4;m.step(f);
    f.reload=true;assert(m.step(f)==39);m.cancel();
    f.reload=false;m.step(f);m.loaded=15;f.fire=true;
    assert(m.step(f)==37);m.consume(2,84,83,83,4);assert(m.loaded==14);
    // Changing equipment cannot transfer a magazine credit into another gun.
    // The authoritative native total remains unchanged; holding the trigger
    // through the switch cannot fire before a fresh release/reload sequence.
    f.total=83;f.loadout=9100000;m.step(f);
    assert(m.loaded==0&&!m.fault&&!m.reloading&&f.total==83);
    assert(m.step(f)==0);f.fire=false;m.step(f);
    f.reload=true;assert(m.step(f)==39);
    f.loadout=1250000;m.step(f);assert(m.loaded==0&&!m.reloading);
    // Same-address respawn must not revive a previous magazine/reload credit.
    f.reload=false;f.fire=false;m.step(f);m.loaded=10;
    f.hp=0;m.step(f);assert(m.loaded==0&&!m.reloading&&!m.fault&&f.total==83);
    f.hp=100;f.fire=true;assert(m.step(f)==0&&m.loaded==0);
    f.fire=false;m.step(f);f.reload=true;assert(m.step(f)==39);
    m.step({});assert(m.loaded==0&&!m.reloading);
    // Intervention needs native progress AND its original insert/end times.
    f={};f.player=1;f.hp=100;f.total=20;f.focused=true;
    f.loadout=static_cast<std::uint64_t>(9200000)<<1;m.step(f);m.step(f);
    f.fire=true;f.now=10;assert(m.step(f)==39&&m.empty_reload);
    f.fire=false;f.animation=465501;f.elapsed=0;m.step(f);
    for(int i=1;i<=7;++i){f.now=10+i*.2;f.elapsed=i==1?.02:(i-1)*.2;m.step(f);}
    assert(m.loaded==0&&m.reloading);
    f.animation=-1;f.now=11.8;m.step(f);assert(m.loaded==5&&m.reloading);
    f.fire=true;f.now=12;assert(m.step(f)==0);
    f.fire=false;f.now=13.867;m.step(f);assert(!m.reloading&&m.loaded==5);
    f.fire=true;assert(m.step(f)==37);m.consume(1,20,19,19,f.now);
    f.total=19;f.fire=false;m.step(f);f.fire=true;f.now=14.5;assert(m.step(f)==0);
    f.fire=false;m.step(f);f.fire=true;f.now=14.9;assert(m.step(f)==37);
    // Focus loss cancels pending credit; a clock alone never completes reload.
    m.step({});f.fire=false;f.now=20;m.step(f);f.fire=true;assert(m.step(f)==39);
    f.fire=false;f.now=25;m.step(f);assert(m.loaded==0&&!m.reloading);
}
