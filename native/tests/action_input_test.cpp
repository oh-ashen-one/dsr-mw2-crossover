#include "m9_action_input.hpp"
#include "m9_magazine.hpp"
#include "m9_aim_latch.hpp"
#include <cassert>
using namespace dsr_mw2;
int main(){
    // Replay the owner's R2 path: no native heavy shot can escape with an
    // empty magazine, while movement/menu/stance requests remain untouched.
    std::array<std::uint8_t,53> a{};a[1]=1;a[21]=1;a[10]=1;
    assert(m9_fire_intent(a,false));
    // Owner trace: L2 aim holds native 1/19/21/52 continuously; R2 then adds
    // 0/7 plus the trigger. Only the press may count as fire while aiming.
    {std::array<std::uint8_t,53> aim{};aim[1]=aim[19]=aim[21]=aim[52]=1;
     assert(!m9_fire_intent(aim,false,true));
     assert(m9_fire_intent(aim,true,true));
     aim[0]=aim[7]=1;assert(m9_fire_intent(aim,false,true));}
    m9_route_actions(a,0,false,true);
    assert(!a[1]&&!a[0]&&!a[37]&&a[21]&&a[10]);
    a[1]=1;m9_route_actions(a,37,false,true);
    assert(a[37]&&!a[1]);
    a.fill(1);m9_route_actions(a,999,true,true);
    assert(!a[0]&&!a[1]&&!a[5]&&!a[7]&&!a[14]&&!a[19]&&!a[51]&&!a[52]);
    assert(a[10]&&a[21]&&a[50]&&!a[37]&&!a[38]&&!a[39]);
    // A native 99->98 receipt after a switch leaves zero rounds, but allows
    // another explicit reload instead of permanently disabling gun/aim.
    M9Magazine m;MagazineFrame f;f.player=1;f.hp=100;f.total=99;f.focused=true;
    m.step(f);m.step(f);m.consume(1,99,98,98,1);
    assert(!m.fault&&m.loaded==0&&!m.reloading);
    f.total=98;f.fire=true;assert(m.step(f)==0);
    f.fire=false;m.step(f);f.reload=true;assert(m.step(f)==39);
    m.consume(1,98,97,96,2);assert(m.fault);
    // Explicit L2 can request aim with no native precision action in the
    // two-handed stance. Focus/menu loss still needs release and re-press.
    M9AimLatch aim;
    assert(!aim.desired(true,true,true,true,false,true,false));
    aim.desired(true,true,false,false,false,true,false);
    assert(aim.desired(true,true,true,true,false,true,false));
    assert(!aim.desired(false,false,true,true,true,false,true));
    assert(!aim.desired(true,true,true,true,false,true,false));
}
