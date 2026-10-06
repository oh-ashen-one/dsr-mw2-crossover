// Original Windows console test for the original hook; no game or renderer.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xmmintrin.h>
#include <cstdio>
#include <cstring>
#include "entry_observer.hpp"
extern "C" double EntryTestTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntryPadTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntryDeltaTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntrySetTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntryAimTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntryHudTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" double EntryPresentTarget(std::uint64_t,double,std::uint64_t,double);
extern "C" void EntryVisibilityTarget(void*);
namespace {
unsigned calls=0;bool captured=true;
alignas(8) unsigned char actor[0x2b0]{};
void observe_visibility(const dsr_mw2::EntryRegisters& r){captured=captured&&r.rcx==reinterpret_cast<std::uint64_t>(actor);++calls;}
void redirect_visibility(void* pointer){
    using Fn=void(*)(void*);Fn f=nullptr;auto* address=dsr_mw2::entry_trampoline(dsr_mw2::EntryPoint::player_visibility);
    std::memcpy(&f,&address,sizeof(f));captured=captured&&pointer==actor;++calls;f(pointer);
}
void observe(const dsr_mw2::EntryRegisters& r){
    double b=0,d=0;std::memcpy(&b,r.xmm[1],8);std::memcpy(&d,r.xmm[3],8);
    captured=captured&&r.rcx==31&&r.r8==71&&b==1.25&&d==3.5&&r.return_address!=0;
    ++calls;
    // Deliberately alter floating-point control state. The shim must restore it.
    _mm_setcsr(_mm_getcsr()|0x6000);
}
}
template<dsr_mw2::EntryPoint point> double redirect(std::uint64_t a,double b,std::uint64_t c,double d){
    using Fn=double(*)(std::uint64_t,double,std::uint64_t,double);
    Fn original=nullptr;auto* address=dsr_mw2::entry_trampoline(point);
    static_assert(sizeof(original)==sizeof(address));std::memcpy(&original,&address,sizeof(original));
    const auto result=original(a,b,c,d);
    captured=captured&&a==31&&b==1.25&&c==71&&d==3.5;++calls;
    return result;
}
int main(int argc,char**){
    const auto initial=_mm_getcsr();
    using Fn=double(*)(std::uint64_t,double,std::uint64_t,double);
    Fn functions[]={EntryTestTarget,EntryPadTarget,EntryDeltaTarget,EntrySetTarget,EntryAimTarget,EntryHudTarget,EntryPresentTarget};
    Fn redirects[]={redirect<dsr_mw2::EntryPoint::frame>,redirect<dsr_mw2::EntryPoint::pad>,redirect<dsr_mw2::EntryPoint::item_delta>,redirect<dsr_mw2::EntryPoint::set_count>,redirect<dsr_mw2::EntryPoint::aim_camera>,redirect<dsr_mw2::EntryPoint::hud_reticle>,redirect<dsr_mw2::EntryPoint::render_present>};
    for(unsigned index=0;index<7;++index){
        if(functions[index](31,1.25,71,3.5)!=106.75)return 1;
        const auto point=index==6?dsr_mw2::EntryPoint::render_present:static_cast<dsr_mw2::EntryPoint>(index);
        const bool installed=argc>1?dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(functions[index]),reinterpret_cast<void*>(redirects[index]),point):
            dsr_mw2::install_entry_observer(reinterpret_cast<void*>(functions[index]),observe,point);
        if(!installed)return 2;
    }
    const bool visibility=argc>1?dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(EntryVisibilityTarget),reinterpret_cast<void*>(redirect_visibility),dsr_mw2::EntryPoint::player_visibility):
        dsr_mw2::install_entry_observer(reinterpret_cast<void*>(EntryVisibilityTarget),observe_visibility,dsr_mw2::EntryPoint::player_visibility);
    if(!visibility)return 4;
    bool outputs=true;
    for(unsigned i=0;i<500;++i)for(auto function:functions)
        outputs=outputs&&function(31,1.25,71,3.5)==106.75&&_mm_getcsr()==initial;
    for(unsigned i=0;i<500;++i)EntryVisibilityTarget(actor);
    unsigned actor_count=0;std::memcpy(&actor_count,actor,4);outputs=outputs&&actor_count==500;
    bool removed=true;
    for(unsigned index=0;index<8;++index)removed=dsr_mw2::remove_entry_observer(static_cast<dsr_mw2::EntryPoint>(index))&&removed;
    bool after=calls==4000;
    for(auto function:functions)after=after&&function(31,1.25,71,3.5)==106.75;
    EntryVisibilityTarget(actor);std::memcpy(&actor_count,actor,4);
    after=after&&calls==4000&&actor_count==501;
    std::printf("{\"calls\":%u,\"profiles\":8,\"typed_redirect\":%s,\"arguments_preserved\":%s,\"outputs_and_mxcsr_preserved\":%s,\"removed\":%s,\"post_remove_passed\":%s,\"native_game_test\":false}\n",
                calls,argc>1?"true":"false",captured?"true":"false",outputs?"true":"false",removed?"true":"false",after?"true":"false");
    return captured&&outputs&&removed&&after?0:3;
}
