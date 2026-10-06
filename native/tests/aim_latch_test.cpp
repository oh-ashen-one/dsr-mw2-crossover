#include "m9_aim_latch.hpp"
#include <cassert>
using namespace dsr_mw2;
int main(){
    M9AimLatch a;
    // Entering the context with the button already held must not take aim.
    assert(!a.desired(true,true,true,true,false,true,false));
    assert(!a.desired(true,true,false,false,false,true,false));
    assert(a.desired(true,true,true,true,false,true,false));
    // Reload suspends native ownership, then resumes without another edge.
    assert(!a.desired(true,false,true,false,true,true,true));
    assert(!a.desired(true,false,true,false,false,true,false));
    assert(a.desired(true,true,true,false,false,true,false));
    // Focus loss/evade cancels intent and requires a new neutral observation.
    assert(!a.desired(true,false,true,false,true,false,true));
    assert(!a.desired(true,true,true,true,false,true,false));
    a.desired(true,true,false,false,false,true,false);
    assert(a.desired(true,true,true,true,false,true,false));
    assert(!a.desired(true,true,false,false,true,true,true));
    // Never acquire an aim bit already set by another native context.
    assert(!a.desired(true,true,true,true,false,true,true));
    a.desired(true,true,false,false,false,true,false);
    assert(!a.desired(false,true,true,true,false,true,false));
    assert(!a.desired(true,true,true,true,false,true,false));
    a.reset();assert(!a.desired(true,true,true,true,false,true,false));
}
