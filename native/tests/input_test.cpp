#include "m9_input.hpp"
#include <cassert>
#include <iostream>
using namespace dsr_mw2;
int main(){
    unsigned checks=0;auto check=[&](bool ok){assert(ok);++checks;};
    InputContext c{true,true,true,true,0x123400,1};WeaponControls raw;M9Input input;
    check(input.map(c,raw).owned);
    raw.mouse_primary=true;check(input.map(c,raw).trigger);
    raw.keyboard_reload=true;raw.mouse_secondary=true;
    auto out=input.map(c,raw);check(out.trigger&&out.reload&&out.aim);
    c.focused=false;out=input.map(c,raw);check(!out.owned&&!out.trigger&&!out.reload&&!out.aim);
    c.focused=true;out=input.map(c,raw);check(out.owned&&!out.trigger&&!out.reload&&!out.aim);
    raw={};input.map(c,raw);raw.mouse_primary=true;check(input.map(c,raw).trigger);
    c.load_epoch++;check(!input.map(c,raw).trigger);
    raw={};input.map(c,raw);raw.pad_connected=true;raw.right_trigger=255;
    check(!input.map(c,raw).trigger);raw.right_trigger=0;input.map(c,raw);
    raw.right_trigger=29;check(!input.map(c,raw).trigger);
    raw.right_trigger=30;check(input.map(c,raw).trigger);
    raw.right_trigger=25;check(input.map(c,raw).trigger);
    raw.right_trigger=20;check(!input.map(c,raw).trigger);
    raw.left_trigger=255;raw.pad_buttons=0x4000;out=input.map(c,raw);check(out.aim&&out.reload&&!out.trigger);
    raw.pad_connected=false;out=input.map(c,raw);check(!out.trigger&&!out.aim&&!out.reload);
    raw={};input.map(c,raw);raw.keyboard_reload=true;
    c.gameplay=false;check(!input.map(c,raw).owned);
    c.gameplay=true;check(!input.map(c,raw).reload);
    raw={};input.map(c,raw);raw.keyboard_reload=true;check(input.map(c,raw).reload);
    c.alive=false;check(!input.map(c,raw).owned);c.alive=true;
    c.right_m9=false;check(!input.map(c,raw).owned);c.right_m9=true;
    c.player=0;check(!input.map(c,raw).owned);c.player=0x678900;
    check(!input.map(c,raw).reload);raw={};input.map(c,raw);
    Frame frame;raw.mouse_primary=true;input.apply(frame,c,raw);
    check(frame.focused&&frame.gameplay&&frame.trigger&&!frame.aim&&!frame.reload&&frame.load_epoch==c.load_epoch);
    c.focused=false;input.apply(frame,c,raw);check(!frame.focused&&!frame.gameplay&&!frame.trigger);
    std::cout<<checks<<" input lifecycle checks passed; no game or physical controller exercised\n";
}
