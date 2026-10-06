#include "m9_recoil_delta.hpp"
#include "m9_camera_angles.hpp"
#include <cassert>
#include <cmath>
#include <limits>
int main(){
    dsr_mw2::M9RecoilDelta r;
    assert(!r.shot(1,12,11,11,false,.5f,.5f));
    assert(!r.shot(1,12,10,10,true,.5f,.5f));
    assert(!r.shot(1,12,11,10,true,.5f,.5f));
    assert(r.shot(1,12,11,11,true,.5f,.25f));
    double pitch=0,yaw=0;float peak=0;
    for(int i=0;i<600;i++){
        const auto d=r.step(1,1.f/60.f,true);assert(d.valid);
        pitch+=d.pitch;yaw+=d.yaw;peak=std::max(peak,std::abs(r.degrees()[0]));
    }
    assert(peak>.1f&&peak<3.f);assert(std::abs(pitch)<1e-6&&std::abs(yaw)<1e-6);
    assert(r.shot(1,11,10,10,true,1.f,0.f));
    assert(r.step(1,.016f,true).pitch<0);
    assert(!r.step(1,.016f,false).valid);
    assert(!r.step(2,.016f,true).valid);
    assert(!r.step(1,std::numeric_limits<float>::quiet_NaN(),true).valid);
    assert(r.degrees()[0]==0&&r.degrees()[1]==0);
    std::array<float,2> after{88,99};
    assert(dsr_mw2::m9_camera_angles({0,3.13f},-80,80,-.01f,.05f,after));
    assert(after[0]==-.01f&&after[1]< -3.);
    assert(dsr_mw2::m9_camera_angles({-1.395f,0},-80,80,-.01f,0,after));
    assert(std::abs(after[0]+1.3962634f)<1e-6f);
    const auto unchanged=after;
    assert(!dsr_mw2::m9_camera_angles({0,0},80,-80,.01f,0,after));
    assert(!dsr_mw2::m9_camera_angles({0,0},-80,80,.2f,0,after));
    assert(!dsr_mw2::m9_camera_angles({0,0},-80,80,std::numeric_limits<float>::quiet_NaN(),0,after));
    assert(after==unchanged);
}
