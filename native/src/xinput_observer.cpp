// Original input-boundary observer. CrossOver system input, untouched outputs.
// Optional exact-entry frame observation is separately gated and time-bounded.
// No controller emulation, inventory write or worker thread.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xinput.h>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <cmath>
#include <algorithm>
#include "dsr_snapshot.hpp"
#include "entry_observer.hpp"
#include "input_lookup_guard.hpp"
#include "m9_magazine.hpp"
#include "m9_action_input.hpp"
#include "m9_native_aim.hpp"
#include "m9_recoil_delta.hpp"
#include "m9_camera_angles.hpp"
#include "viewmodel_renderer.hpp"
#include "shot_audio.hpp"
#include "esd_state_table.hpp"

namespace {
INIT_ONCE once=INIT_ONCE_STATIC_INIT;
SRWLOCK log_lock=SRWLOCK_INIT;
HMODULE backend=nullptr;
using GetStateFn=DWORD(WINAPI*)(DWORD,XINPUT_STATE*);
GetStateFn get_state=nullptr;
HANDLE log_file=INVALID_HANDLE_VALUE;
unsigned long long calls=0;
ULONGLONG last_sample=0;
// Diagnostic only: record the first native-game access violation, then let
// Windows handle it normally. Never swallow a fault or alter CONTEXT/input.
HANDLE crash_log=INVALID_HANDLE_VALUE;
std::uintptr_t crash_base=0;
volatile LONG crash_recorded=0;
LONG CALLBACK record_native_crash(EXCEPTION_POINTERS* fault){
    if(!fault||!fault->ExceptionRecord||!fault->ContextRecord||crash_log==INVALID_HANDLE_VALUE)
        return EXCEPTION_CONTINUE_SEARCH;
    const auto& e=*fault->ExceptionRecord;const auto& c=*fault->ContextRecord;
    if(e.ExceptionCode!=EXCEPTION_ACCESS_VIOLATION||c.Rip<crash_base||c.Rip-crash_base>=0x1d00000||
       InterlockedCompareExchange(&crash_recorded,1,0)!=0)return EXCEPTION_CONTINUE_SEARCH;
    char line[512]{};
    const int n=std::snprintf(line,sizeof(line),
        "{\"kind\":\"native_access_violation\",\"ms\":%llu,\"rva\":\"%llx\",\"rbx_null\":%s,\"rcx_null\":%s,\"rdx_null\":%s,\"access\":%llu,\"null_target\":%s}\n",
        GetTickCount64(),static_cast<unsigned long long>(c.Rip-crash_base),
        c.Rbx==0?"true":"false",c.Rcx==0?"true":"false",c.Rdx==0?"true":"false",
        static_cast<unsigned long long>(e.NumberParameters?e.ExceptionInformation[0]:0),
        e.NumberParameters>1&&e.ExceptionInformation[1]==0?"true":"false");
    DWORD written=0;
    if(n>0&&n<static_cast<int>(sizeof(line)))WriteFile(crash_log,line,static_cast<DWORD>(n),&written,nullptr);
    // Code-looking stack words are candidates, NOT an unwound backtrace.
    // No raw stack bytes, user text, account data or memory dump is saved.
    for(unsigned i=0;i<64;++i){
        std::uintptr_t value=0;SIZE_T bytes=0;
        if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(c.Rsp+i*sizeof(value)),&value,sizeof(value),&bytes)||bytes!=sizeof(value))break;
        if(value<crash_base||value-crash_base>=0x1200000)continue;
        const int count=std::snprintf(line,sizeof(line),"{\"kind\":\"stack_code_candidate\",\"slot\":%u,\"rva\":\"%llx\"}\n",i,static_cast<unsigned long long>(value-crash_base));
        if(count>0&&count<static_cast<int>(sizeof(line)))WriteFile(crash_log,line,static_cast<DWORD>(count),&written,nullptr);
    }
    FlushFileBuffers(crash_log);
    return EXCEPTION_CONTINUE_SEARCH;
}
bool frame_enabled=false,contracts_enabled=false,post_enabled=false,frame_attempted=false,frame_finished=false;
std::array<std::int32_t,31> previous_animations{};
bool gun_enabled=false;
bool loadout_session=false;
bool owner_session=false;
// Owner request: unlimited gun ammunition. A qualified gun shot keeps its native
// Standard Bolt; magazine/recoil/sound still see an ordinary one-round receipt.
bool unlimited_ammo=false;
unsigned frame_limit_ms(){return gun_enabled?(owner_session?7200000u:loadout_session?600000u:180000u):post_enabled?90000u:contracts_enabled?60000u:30000u;}
bool audio_enabled=false;
bool view_enabled=false,view_installed=false,visibility_installed=false;
SRWLOCK controller_lock=SRWLOCK_INIT;
XINPUT_GAMEPAD controller{};ULONGLONG controller_stamp=0;DWORD controller_slot=4;
XINPUT_GAMEPAD current_controller(){
    XINPUT_GAMEPAD result{};AcquireSRWLockShared(&controller_lock);
    if(controller_slot<4&&GetTickCount64()-controller_stamp<250)result=controller;
    ReleaseSRWLockShared(&controller_lock);return result;
}
bool aim_enabled=false;
bool camera_enabled=false,camera_installed=false,camera_fault=false;
unsigned long long camera_calls=0,camera_scoped_calls=0;
bool hud_enabled=false,hud_installed=false,hud_fault=false,hud_masked=false;
unsigned long long hud_calls=0,hud_scoped_calls=0,hud_restores=0;
dsr_mw2::Address hud_gauge=0,hud_root=0;
std::array<dsr_mw2::Address,10> hud_children{},hud_vtables{};
std::array<bool,10> hud_visible{};
constexpr const wchar_t* hud_names[]={L"bg_parchment_0",L"text",L"F20-01_arrow",
    L"category_l2",L"category_r2",L"text_L",L"text_R",L"category_l",L"category_r",L"targetsite"};
DWORD pad_thread=0;
dsr_mw2::M9Magazine magazine;
dsr_mw2::M9NativeAim aim;
dsr_mw2::M9RecoilDelta recoil;
bool recoil_fault=false;float scope_fraction=0;
std::uint32_t recoil_random=0x9e3779b9U;
std::uint64_t last_loadout=0;
unsigned long long pad_calls=0,delta_calls=0,set_calls=0;
std::array<std::uint8_t,53> previous_pad{};
HANDLE frame_log=INVALID_HANDLE_VALUE;
SRWLOCK frame_lock=SRWLOCK_INIT;
ULONGLONG frame_start=0;
unsigned long long frame_calls=0;
dsr_mw2::Snapshot previous_frame{};
struct LocalReader final:dsr_mw2::Reader {
    bool read(dsr_mw2::Address at,void* dst,std::size_t bytes)const override {
        SIZE_T n=0;return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(at),dst,bytes,&n)&&n==bytes;
    }
};
void contract_sample(const dsr_mw2::EntryRegisters& registers,dsr_mw2::EntryPoint point){
    if(frame_finished||frame_log==INVALID_HANDLE_VALUE||!TryAcquireSRWLockExclusive(&frame_lock))return;
    LocalReader reader;dsr_mw2::Snapshot s;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const auto status=dsr_mw2::observe(reader,base,s);
    auto& count=point==dsr_mw2::EntryPoint::pad?pad_calls:point==dsr_mw2::EntryPoint::item_delta?delta_calls:set_calls;
    ++count;
    if(point!=dsr_mw2::EntryPoint::pad||count<=3||count%60==0||s.actions!=previous_pad){
        dsr_mw2::Address control=0;reader.read(s.player+0x68,&control,sizeof(control));
        float dt=0;std::memcpy(&dt,registers.xmm[1],4);
        std::uint64_t stack5=0;
        reader.read(reinterpret_cast<dsr_mw2::Address>(&registers.return_address)+0x28,&stack5,sizeof(stack5));
        char line[2048]{};
        const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_contract_entry\",\"point\":%u,\"ms\":%llu,\"count\":%llu,\"thread\":%lu,"
            "\"rcx\":\"%llx\",\"rdx\":\"%llx\",\"r8\":\"%llx\",\"r9\":\"%llx\",\"stack5\":\"%llx\",\"xmm1_float\":%.9g,"
            "\"return_rva\":\"%llx\",\"snapshot\":%u,\"player\":\"%llx\",\"control\":\"%llx\",\"manipulator\":\"%llx\",\"equip_data\":\"%llx\","
            "\"bolt_index\":%d,\"bolts\":%d,\"a0\":%u,\"a7\":%u,\"inventory_writes\":false}\n",
            static_cast<unsigned>(point),GetTickCount64(),count,GetCurrentThreadId(),registers.rcx,registers.rdx,registers.r8,registers.r9,
            static_cast<unsigned long long>(stack5),static_cast<double>(dt),
            static_cast<unsigned long long>(registers.return_address>=base?registers.return_address-base:0),static_cast<unsigned>(status),
            static_cast<unsigned long long>(s.player),static_cast<unsigned long long>(control),static_cast<unsigned long long>(s.manipulator),
            static_cast<unsigned long long>(s.equip_data),s.first_bolt.index,s.first_bolt.quantity,unsigned(s.actions[0]),unsigned(s.actions[7]));
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
    }
    if(point==dsr_mw2::EntryPoint::pad)previous_pad=s.actions;
    ReleaseSRWLockExclusive(&frame_lock);
}
void pad_sample(const dsr_mw2::EntryRegisters& r){contract_sample(r,dsr_mw2::EntryPoint::pad);}
void delta_sample(const dsr_mw2::EntryRegisters& r){contract_sample(r,dsr_mw2::EntryPoint::item_delta);}
void set_sample(const dsr_mw2::EntryRegisters& r){contract_sample(r,dsr_mw2::EntryPoint::set_count);}
template<class Fn> Fn original(dsr_mw2::EntryPoint point){
    Fn f=nullptr;auto* address=dsr_mw2::entry_trampoline(point);
    static_assert(sizeof(f)==sizeof(address));std::memcpy(&f,&address,sizeof(f));return f;
}
void view_present(const dsr_mw2::EntryRegisters& r){
    // CD4630 receives the renderer object in RCX and skip-Present in DL.
    // This original observer preserves all native registers/flags. Native query
    // completion and Present continue unchanged after the viewmodel commands.
    if(r.rdx&255)return;
    LocalReader reader;dsr_mw2::Address table=0,chain=0;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    if(reader.get(r.rcx,0,table)&&table==base+0x14a9448&&reader.get(r.rcx,0x30,chain)&&chain)
        dsr_mw2::vm_render(reinterpret_cast<void*>(chain));
}
void view_visibility(dsr_mw2::Address player){
    using Function=void(*)(dsr_mw2::Address);
    original<Function>(dsr_mw2::EntryPoint::player_visibility)(player);
    if(!dsr_mw2::vm_visible(player)||!TryAcquireSRWLockExclusive(&frame_lock))return;
    if(!frame_finished&&aim.owned&&!aim.fault&&aim.player==player&&GetCurrentThreadId()==pad_thread){
        LocalReader reader;
        // Independent static inspection of native3549e0 confirms these exact
        // render-state fields. Native update above owns restoration every tick.
        for(const auto& spec:std::array<std::array<unsigned,3>,2>{{{0x60,0x84,0x92},{0x850,0x9c,0xaa}}}){
            dsr_mw2::Address model=0;unsigned dirty=0;unsigned char visible=0;
            if(reader.get(player,spec[0],model)&&model&&reader.get(model,spec[1],dirty)&&reader.get(model,spec[2],visible)&&(visible&1)){
                dirty|=0x200;visible=static_cast<unsigned char>(visible&0xfe);
                std::memcpy(reinterpret_cast<void*>(model+spec[1]),&dirty,sizeof(dirty));
                std::memcpy(reinterpret_cast<void*>(model+spec[2]),&visible,1);
            }
        }
    }
    ReleaseSRWLockExclusive(&frame_lock);
}
// Native HUD contracts independently checked against the pinned retail image.
// Only F20-01's named children are masked; no global bow asset or root-class
// visibility assumption. Native update always runs with prior bits restored.
using HudChildFn=dsr_mw2::Address(*)(dsr_mw2::Address,const wchar_t*);
using HudVisibleFn=bool(*)(dsr_mw2::Address,bool);
bool hud_contract(dsr_mw2::Address base){
    constexpr unsigned char child[]={0x48,0x89,0x5c,0x24,0x10,0x57,0x48,0x83,0xec,0x20};
    constexpr unsigned char visible[]={0x44,0x0f,0xb6,0x41,0x28,0x02,0xd2,0x41,0x32,0xd0,0x41,0x0f,0xb6,0xc0,
        0x80,0xe2,0x02,0xd0,0xe8,0x41,0x32,0xd0,0x24,0x01,0x88,0x51,0x28,0xc3};
    return !std::memcmp(reinterpret_cast<void*>(base+0xed6020),child,sizeof(child))&&
        !std::memcmp(reinterpret_cast<void*>(base+0xedbdb0),visible,sizeof(visible));
}
bool restore_hud(const LocalReader& reader,dsr_mw2::Address base){
    if(!hud_masked)return true;
    dsr_mw2::Address root=0;
    bool valid=GetCurrentThreadId()==pad_thread&&reader.get(hud_gauge,0x4f8,root)&&root==hud_root;
    const auto child=reinterpret_cast<HudChildFn>(base+0xed6020);
    // Check the whole identity set before any write. Never touch stale widgets.
    for(unsigned i=0;valid&&i<hud_children.size();++i){
        dsr_mw2::Address vt=0;std::uint8_t flags=0;
        valid=child(root,hud_names[i])==hud_children[i]&&reader.get(hud_children[i],0,vt)&&
            vt==hud_vtables[i]&&reader.get(hud_children[i],0x28,flags);
    }
    hud_masked=false;
    if(!valid){hud_fault=true;return false;}
    const auto visible=reinterpret_cast<HudVisibleFn>(base+0xedbdb0);
    bool restored=true;
    for(unsigned i=0;i<hud_children.size();++i){
        visible(hud_children[i],hud_visible[i]);std::uint8_t flags=0;
        restored=reader.get(hud_children[i],0x28,flags)&&bool(flags&2)==hud_visible[i]&&restored;
    }
    if(!restored)hud_fault=true;
    ++hud_restores;return restored;
}
void scoped_hud(dsr_mw2::Address gauge){
    using Function=void(*)(dsr_mw2::Address);
    const auto native=original<Function>(dsr_mw2::EntryPoint::hud_reticle);
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    LocalReader reader;
    if(!TryAcquireSRWLockExclusive(&frame_lock)){native(gauge);return;}
    const bool restored=restore_hud(reader,base);
    ReleaseSRWLockExclusive(&frame_lock);
    native(gauge);
    if(frame_finished||!TryAcquireSRWLockExclusive(&frame_lock))return;
    ++hud_calls;
    dsr_mw2::Snapshot s;dsr_mw2::Address root=0,root_vt=0;
    const auto status=dsr_mw2::observe(reader,base,s);
    DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
    bool scoped=hud_enabled&&!hud_fault&&restored&&hud_calls>60&&GetCurrentThreadId()==pad_thread&&
        status==dsr_mw2::ReadStatus::ok&&s.hp&&dsr_mw2::is_m9(s.right_weapon)&&
        aim.owned&&!aim.fault&&aim.player==s.player&&foreground==GetCurrentProcessId()&&
        reader.get(gauge,0x4f8,root)&&reader.get(root,0,root_vt)&&root_vt>base&&root_vt<base+0x1d00000;
    const auto child=reinterpret_cast<HudChildFn>(base+0xed6020);
    for(unsigned i=0;scoped&&i<hud_children.size();++i){
        hud_children[i]=child(root,hud_names[i]);std::uint8_t flags=0;
        scoped=reader.get(hud_children[i],0,hud_vtables[i])&&hud_vtables[i]>base&&hud_vtables[i]<base+0x1d00000&&
            reader.get(hud_children[i],0x28,flags);
        hud_visible[i]=bool(flags&2);
        for(unsigned j=0;j<i;++j)scoped=scoped&&hud_children[j]!=hud_children[i];
    }
    if(scoped){
        hud_gauge=gauge;hud_root=root;hud_masked=true;++hud_scoped_calls;
        const auto visible=reinterpret_cast<HudVisibleFn>(base+0xedbdb0);
        for(auto widget:hud_children){
            visible(widget,false);std::uint8_t flags=0;
            if(!reader.get(widget,0x28,flags)||(flags&2))hud_fault=true;
        }
        if(hud_fault)restore_hud(reader,base);
    }
    if(hud_calls<=3||hud_calls%30==0||scoped||hud_fault){
        char line[512]{};const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_hud_scope\",\"ms\":%llu,\"count\":%llu,\"thread\":%lu,\"pad_thread\":%lu,\"gauge\":\"%llx\",\"root\":\"%llx\",\"scoped\":%s,\"restored_previous\":%s,\"fault\":%s}\n",
            GetTickCount64(),hud_calls,GetCurrentThreadId(),pad_thread,static_cast<unsigned long long>(gauge),
            static_cast<unsigned long long>(root),scoped?"true":"false",restored?"true":"false",hud_fault?"true":"false");
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
    }
    ReleaseSRWLockExclusive(&frame_lock);
}
void post_pad(dsr_mw2::Address manipulator,float dt,dsr_mw2::Address control){
    using Function=void(*)(dsr_mw2::Address,float,dsr_mw2::Address);
    original<Function>(dsr_mw2::EntryPoint::pad)(manipulator,dt,control);
    if(frame_finished||frame_log==INVALID_HANDLE_VALUE||!TryAcquireSRWLockExclusive(&frame_lock))return;
    LocalReader reader;dsr_mw2::Snapshot s;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const auto status=dsr_mw2::observe(reader,base,s);++pad_calls;pad_thread=GetCurrentThreadId();
    dsr_mw2::Address actual_control=0,mediator=0;
    reader.get(s.player,0x68,actual_control);reader.get(actual_control,0x20,mediator);
    std::array<std::int32_t,31> animations{};std::array<float,31> elapsed{};
    bool animation_read=mediator!=0;
    for(unsigned i=0;i<31;++i){
        animation_read=reader.get(mediator,168*i,animations[i])&&animation_read;
        animation_read=reader.get(mediator,168*i+0xa4,elapsed[i])&&animation_read;
    }
    if(gun_enabled&&status==dsr_mw2::ReadStatus::ok&&s.hp&&dsr_mw2::is_m9(s.right_weapon)&&
       !dsr_mw2::is_m9(s.left_weapon)&&manipulator==s.manipulator&&control==actual_control&&animation_read){
        DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
        dsr_mw2::MagazineFrame f;
        f.loadout=(static_cast<std::uint64_t>(s.right_weapon)<<1)|s.right_slot;
        const bool loadout_changed=last_loadout!=f.loadout;
        const auto previous_loadout=last_loadout;
        if(loadout_changed){aim.stop(reader,base,s);recoil.reset();scope_fraction=0;last_loadout=f.loadout;}
        const auto action_slot=dsr_mw2::m9_action_slot(animations);
        f.player=s.player;f.total=unlimited_ammo&&s.first_bolt.quantity>0?999:s.first_bolt.quantity;f.hp=static_cast<int>(s.hp);f.animation=animations[action_slot];
        f.elapsed=elapsed[action_slot];f.now=static_cast<double>(GetTickCount64())/1000.;f.focused=foreground==GetCurrentProcessId();
        // Read-only position qualification. Reviewed DSR-Gadget's current
        // ChrMapData=player+68 and ChrPosData=control+28; no position writer.
        if(pad_calls%12==0){
            dsr_mw2::Address position=0,again=0;std::array<float,3> xyz{};
            const bool valid=reader.get(actual_control,0x28,position)&&reader.get(position,0x10,xyz)&&
                reader.get(actual_control,0x28,again)&&position==again&&
                std::all_of(xyz.begin(),xyz.end(),[](float v){return std::isfinite(v)&&std::fabs(v)<100000;});
            if(valid){
                char line[384]{};const int n=std::snprintf(line,sizeof(line),
                    "{\"kind\":\"position_observation\",\"ms\":%llu,\"player\":\"%llx\",\"xyz\":[%.9g,%.9g,%.9g],\"forward_key\":%s,\"aim_owned\":%s,\"animation\":%d}\n",
                    GetTickCount64(),static_cast<unsigned long long>(s.player),static_cast<double>(xyz[0]),
                    static_cast<double>(xyz[1]),static_cast<double>(xyz[2]),
                    f.focused&&(GetAsyncKeyState('W')&0x8000)?"true":"false",aim.owned?"true":"false",f.animation);
                if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
            }
        }
        const auto pad=current_controller();
        // DSR raises native action 1 at a lighter L2 pull than the aim latch's
        // 64; excluding it from the first trigger travel stops L2 firing a shot.
        const bool aim_held=f.focused&&((GetAsyncKeyState(VK_RBUTTON)&0x8000)||pad.bLeftTrigger>=8);
        f.fire=dsr_mw2::m9_fire_intent(s.actions,f.focused&&pad.bRightTrigger>=64,aim_held);
        // Native precision mode suppresses item-use/action14. Read only the
        // owned game's explicit reload key in its already-qualified M9 context.
        f.reload=f.focused&&((GetAsyncKeyState('R')&0x8000)||(aim_enabled&&aim.owned&&(pad.wButtons&XINPUT_GAMEPAD_X)));
        f.interrupted=s.actions[10]||s.actions[15]||s.actions[16]||s.actions[17]||s.actions[18]||s.actions[42];
        int request=magazine.step(f);
        if(loadout_changed){
            char line[384]{};const int n=std::snprintf(line,sizeof(line),
                "{\"kind\":\"loadout_change\",\"ms\":%llu,\"previous\":%llu,\"current\":%llu,\"weapon\":%d,\"right_slot\":%u,\"loaded\":%d,\"native_total\":%d,\"request\":%d,\"inventory_writes\":false}\n",
                GetTickCount64(),static_cast<unsigned long long>(previous_loadout),static_cast<unsigned long long>(f.loadout),
                s.right_weapon,unsigned(s.right_slot),magazine.loaded,f.total,request);
            if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        }
        if(aim_enabled){
            const bool allowed=f.focused&&!f.interrupted&&!magazine.fault&&
                (f.animation<0||f.animation==463000||f.animation==465500||f.animation==465501||f.animation==465502);
            const bool held=f.focused&&((GetAsyncKeyState(VK_RBUTTON)&0x8000)||pad.bLeftTrigger>=64);
            const bool resumable=f.focused&&!f.interrupted&&!magazine.fault;
            // L2/RMB is the explicit aim request in either hand stance. Native
            // crossbow precision requests are not emitted in every stance.
            // The latch still requires neutral/re-press and verified native
            // menu/context bits; it never takes an already-owned native bit.
            const bool changed=aim.step(reader,base,s,allowed,held,held||s.actions[19]||s.actions[51],resumable);
            if(changed||pad_calls%12==0||aim.fault){
                char line[768]{};const int n=std::snprintf(line,sizeof(line),
                    "{\"kind\":\"native_aim_trial\",\"ms\":%llu,\"held\":%s,\"owned\":%s,\"fault\":%s,\"before\":%u,\"after\":%u,\"camera_read\":%s,\"camera_active\":%u,\"pitch\":%.9g,\"yaw\":%.9g,\"zoom\":%.9g}\n",
                    GetTickCount64(),held?"true":"false",aim.owned?"true":"false",aim.fault?"true":"false",
                    unsigned(aim.before),unsigned(aim.after),aim.camera_read?"true":"false",unsigned(aim.camera_active),
                    static_cast<double>(aim.pitch),static_cast<double>(aim.yaw),static_cast<double>(aim.zoom));
                if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
            }
        }
        if(s.right_weapon==9200000&&f.focused&&aim.owned&&!aim.fault&&!f.interrupted&&!magazine.reloading&&std::isfinite(dt)&&dt>0&&dt<=.1f)
            scope_fraction=std::min(1.f,scope_fraction+dt/.4f);
        else scope_fraction=0;
        if(view_enabled)dsr_mw2::vm_publish({s.player,GetTickCount64(),s.right_weapon,f.animation,magazine.loaded,
            static_cast<float>(f.elapsed),f.focused&&aim.owned&&!aim.fault&&!magazine.fault&&!f.interrupted,
            magazine.reloading,magazine.empty_reload,static_cast<float>(magazine.reload_elapsed),scope_fraction});
        if(f.focused){
            auto actions=s.actions;
            dsr_mw2::m9_route_actions(actions,request,f.reload||magazine.reloading,aim_enabled);
            std::memcpy(reinterpret_cast<void*>(manipulator+0x84),actions.data(),actions.size());
        }
        if(request||magazine.fault||pad_calls%30==0){
            char line[512]{};const int n=std::snprintf(line,sizeof(line),
                "{\"kind\":\"magazine_control\",\"ms\":%llu,\"request\":%d,\"loaded\":%d,\"native_total\":%d,\"reloading\":%s,\"credited\":%s,\"fault\":%s,\"animation\":%d,\"elapsed\":%.9g}\n",
                GetTickCount64(),request,magazine.loaded,s.first_bolt.quantity,magazine.reloading?"true":"false",magazine.credited?"true":"false",magazine.fault?"true":"false",f.animation,f.elapsed);
            if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        }
    }else if(gun_enabled){magazine.step({});if(aim_enabled)aim.stop(reader,base,s);if(view_enabled)dsr_mw2::vm_publish({});}
    // Never replay a kick after a weapon/focus/menu/aim ownership transition.
    // Native orientation is left intact when ownership ends; no stale undo.
    if(!aim.owned||aim.fault||magazine.fault)recoil.reset();
    if(pad_calls<=3||pad_calls%60==0||animations!=previous_animations||s.actions!=previous_pad||
       (gun_enabled&&(animations[7]>=0||dsr_mw2::m9_action_slot(animations)==5))){
        char line[4096]{};
        const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_post_input\",\"ms\":%llu,\"count\":%llu,\"thread\":%lu,\"snapshot\":%u,"
            "\"identity_matches\":%s,\"dt\":%.9g,\"bolts\":%d,\"animation_read\":%s,\"animations\":[",
            GetTickCount64(),pad_calls,GetCurrentThreadId(),static_cast<unsigned>(status),
            manipulator==s.manipulator&&control==actual_control?"true":"false",static_cast<double>(dt),s.first_bolt.quantity,animation_read?"true":"false");
        if(n>0&&n<static_cast<int>(sizeof(line)-3000)){
            auto used=static_cast<std::size_t>(n);
            for(unsigned i=0;i<31;++i){
                char number[48]="null";
                if(std::isfinite(elapsed[i]))std::snprintf(number,sizeof(number),"%.9g",static_cast<double>(elapsed[i]));
                const int added=std::snprintf(line+used,sizeof(line)-used,"%s[%d,%s]",i?",":"",animations[i],number);
                if(added>0)used+=static_cast<std::size_t>(added);
            }
            const int added=std::snprintf(line+used,sizeof(line)-used,"],\"actions\":[");if(added>0)used+=static_cast<std::size_t>(added);
            for(unsigned i=0;i<s.actions.size();++i){const int add=std::snprintf(line+used,sizeof(line)-used,"%s%u",i?",":"",unsigned(s.actions[i]));if(add>0)used+=static_cast<std::size_t>(add);}
            const char* end="],\"observation\":\"native_input_before_optional_driver\"}\n";std::memcpy(line+used,end,std::strlen(end));used+=std::strlen(end);
            DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(used),&written,nullptr);
        }
    }
    previous_animations=animations;previous_pad=s.actions;
    ReleaseSRWLockExclusive(&frame_lock);
}
int post_delta(dsr_mw2::Address equip,int index,int delta,unsigned char flag,unsigned char extra){
    using Function=int(*)(dsr_mw2::Address,int,int,unsigned char,unsigned char);
    LocalReader reader;dsr_mw2::Snapshot before,after;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const auto caller=reinterpret_cast<dsr_mw2::Address>(__builtin_return_address(0));
    const auto first=dsr_mw2::observe(reader,base,before);
    const bool keep=unlimited_ammo&&gun_enabled&&first==dsr_mw2::ReadStatus::ok&&equip==before.equip_data&&
        index==before.first_bolt.index&&dsr_mw2::is_m9(before.right_weapon)&&caller==base+0x35b149&&
        delta==-1&&flag==0&&extra==0&&before.first_bolt.quantity>0;
    const int result=keep?before.first_bolt.quantity:original<Function>(dsr_mw2::EntryPoint::item_delta)(equip,index,delta,flag,extra);
    const auto second=keep?first:dsr_mw2::observe(reader,base,after);
    if(keep)after=before;
    // Receipt seen by the magazine/recoil/sound: the native one, or one virtual round.
    const int receipt_before=before.first_bolt.quantity;
    const int receipt_after=keep?receipt_before-1:after.first_bolt.quantity;
    const int receipt_result=keep?receipt_before-1:result;
    if(!frame_finished&&frame_log!=INVALID_HANDLE_VALUE&&TryAcquireSRWLockExclusive(&frame_lock)){
        ++delta_calls;char line[1024]{};
        const bool identity=first==dsr_mw2::ReadStatus::ok&&second==dsr_mw2::ReadStatus::ok&&
            equip==before.equip_data&&equip==after.equip_data&&before.player==after.player&&
            index==before.first_bolt.index&&before.right_weapon==after.right_weapon&&dsr_mw2::is_m9(before.right_weapon);
        if(gun_enabled&&identity&&caller==base+0x35b149&&delta==-1&&flag==0&&extra==0){
            magazine.consume(before.player,receipt_before,receipt_after,receipt_result,static_cast<double>(GetTickCount64())/1000.);
            if(!magazine.fault&&receipt_result==receipt_after&&receipt_before-receipt_after==1){
                if(view_enabled)dsr_mw2::vm_native_shot(magazine.loaded==0);
                if(audio_enabled)dsr_mw2::shot_audio_play(before.right_weapon==9200000);
            }
            if(camera_enabled&&!recoil_fault&&!magazine.fault&&aim.owned&&aim.player==before.player&&
               pad_thread==GetCurrentThreadId()){
                // Original deterministic uniform sampler; authentic M9 impulse
                // ranges/centering are in the attributed IW4 adapter. This is
                // not a claim to reproduce MW2's engine RNG sequence.
                auto sample=[](){
                    recoil_random^=recoil_random<<13;recoil_random^=recoil_random>>17;recoil_random^=recoil_random<<5;
                    return static_cast<float>(recoil_random>>8)/16777215.f;
                };
                const float pitch_sample=sample(),yaw_sample=sample();
                const bool accepted=recoil.shot(before.player,receipt_before,receipt_after,
                    receipt_result,true,pitch_sample,yaw_sample,before.right_weapon==9200000);
                char event[384]{};const int length=std::snprintf(event,sizeof(event),
                    "{\"kind\":\"native_recoil_receipt\",\"ms\":%llu,\"accepted\":%s,\"before\":%d,\"after\":%d,\"pitch_velocity\":%.9g,\"yaw_velocity\":%.9g}\n",
                    GetTickCount64(),accepted?"true":"false",before.first_bolt.quantity,after.first_bolt.quantity,
                    static_cast<double>(before.right_weapon==9200000?30.f+55.f*pitch_sample:25.f+20.f*pitch_sample),static_cast<double>(before.right_weapon==9200000?70.f-145.f*yaw_sample:55.f-110.f*yaw_sample));
                if(length>0&&length<static_cast<int>(sizeof(event))){DWORD written=0;WriteFile(frame_log,event,static_cast<DWORD>(length),&written,nullptr);}
            }
        }
        const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_post_ammo\",\"ms\":%llu,\"count\":%llu,\"thread\":%lu,\"identity_matches\":%s,"
            "\"return_rva\":\"%llx\",\"index\":%d,\"delta\":%d,\"flag\":%u,\"extra\":%u,\"native_return\":%d,"
            "\"before\":%d,\"after\":%d,\"unlimited_kept\":%s,\"inventory_writes_by_observer\":false}\n",
            GetTickCount64(),delta_calls,GetCurrentThreadId(),identity?"true":"false",static_cast<unsigned long long>(caller-base),
            index,delta,unsigned(flag),unsigned(extra),result,before.first_bolt.quantity,after.first_bolt.quantity,keep?"true":"false");
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        ReleaseSRWLockExclusive(&frame_lock);
    }
    return result;
}
void scoped_camera(dsr_mw2::Address camera,float dt,dsr_mw2::Address player){
    using Function=void(*)(dsr_mw2::Address,float,dsr_mw2::Address);
    const auto native=original<Function>(dsr_mw2::EntryPoint::aim_camera);
    if(frame_finished||!TryAcquireSRWLockExclusive(&frame_lock)){native(camera,dt,player);return;}
    ++camera_calls;
    LocalReader reader;dsr_mw2::Snapshot s;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const auto status=dsr_mw2::observe(reader,base,s);
    dsr_mw2::Address bullet=0,chr=0,actual=0,vtable=0;
    std::array<float,8> before{},after{};
    std::array<float,2> lens_before{},lens_after{};
    const bool identity=status==dsr_mw2::ReadStatus::ok&&player==s.player&&s.hp&&
        dsr_mw2::is_m9(s.right_weapon)&&reader.get(base,0x1c7a488,bullet)&&
        reader.get(bullet,0x60,chr)&&reader.get(chr,0x68,actual)&&actual==camera&&
        reader.get(camera,0,vtable)&&vtable==base+0x12ee118&&
        reader.read(camera+0xb0,before.data(),sizeof(before))&&
        reader.read(camera+0x134,lens_before.data(),sizeof(lens_before));
    bool finite=std::isfinite(dt)&&dt>0&&dt<=.1f;
    for(float f:before)finite=finite&&std::isfinite(f)&&std::abs(f)<=10.f;
    for(float f:lens_before)finite=finite&&std::isfinite(f)&&f>.01f&&f<3.f;
    DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
    // First60 calls observe the exact camera/player/thread identity without
    // altering anything. Scoped offsets use the native interpolation/collision
    // path; no persistent camera-coordinate, inventory or character write.
    const bool scoped=camera_enabled&&!camera_fault&&camera_calls>60&&identity&&finite&&
        pad_thread==GetCurrentThreadId()&&aim.owned&&aim.player==player&&
        foreground==GetCurrentProcessId();
    // Use the measured source sight-line eye height, undoing the rejected
    // empirical -3cm correction. Forward remains at the preceding .15 control.
    // Native post-update matrix/eye observations below qualify the mapping.
    // Native interpolation/collision runs and both endpoints restore each call.
    constexpr std::array<float,8> shoulder{.060312f,1.415102f,.15f,0.f,.060312f,1.415102f,.15f,0.f};
    // Native231812..23182e interpolates these radian endpoints into +50.
    // The projection path uses cot(vertical_fov/2), divided by aspect for X.
    // Explicit 50-degree vertical diagnostic; MW2's authored65 convention is
    // not yet qualified. Near/far and the native renderer remain untouched.
    // IW4's 15-degree scope uses a 4:3 horizontal convention. Convert
    // explicitly to DSR vertical FOV, then interpolate over source ADS-in .4s.
    const float scope_fov=2.f*std::atan(std::tan(15.f*3.14159265359f/360.f)*.75f);
    const float fov=s.right_weapon==9200000?.872664626f+(scope_fov-.872664626f)*scope_fraction:.872664626f;
    const std::array<float,2> lens{fov,fov};
    // Exact native update reads +14c/+150 before adding real input and building
    // the camera basis. Add only the checked *delta* from a genuine shot's kick,
    // preserving native mouse input, limits and collision. No HP/ammo writes.
    std::array<float,2> angle_before{},angle_written{},angle_native{};
    bool recoil_applied=false;
    const auto kick=recoil.step(player,dt,scoped&&!recoil_fault&&!aim.fault&&!magazine.fault);
    if(kick.valid&&(kick.pitch!=0||kick.yaw!=0)){
        float low=0,high=0;
        if(reader.get(camera,0xf4,low)&&reader.get(camera,0xf0,high)&&
           reader.read(camera+0x14c,angle_before.data(),sizeof(angle_before))&&
           dsr_mw2::m9_camera_angles(angle_before,low,high,kick.pitch,kick.yaw,angle_written)){
            std::memcpy(reinterpret_cast<void*>(camera+0x14c),angle_written.data(),sizeof(angle_written));
            recoil_applied=true;
        }else{recoil_fault=true;recoil.reset();}
    }
    if(scoped){
        std::memcpy(reinterpret_cast<void*>(camera+0xb0),shoulder.data(),sizeof(shoulder));
        std::memcpy(reinterpret_cast<void*>(camera+0x134),lens.data(),sizeof(lens));
        ++camera_scoped_calls;
    }
    ReleaseSRWLockExclusive(&frame_lock);
    native(camera,dt,player);
    bool restored=!scoped;
    if(scoped){
        dsr_mw2::Address current=0;
        if(reader.get(camera,0,current)&&current==vtable&&reader.read(camera+0xb0,after.data(),sizeof(after))&&after==shoulder&&
           reader.read(camera+0x134,lens_after.data(),sizeof(lens_after))&&lens_after==lens){
            std::memcpy(reinterpret_cast<void*>(camera+0xb0),before.data(),sizeof(before));
            std::memcpy(reinterpret_cast<void*>(camera+0x134),lens_before.data(),sizeof(lens_before));
            restored=reader.read(camera+0xb0,after.data(),sizeof(after))&&after==before&&
                reader.read(camera+0x134,lens_after.data(),sizeof(lens_after))&&lens_after==lens_before;
        }
    }
    if(!TryAcquireSRWLockExclusive(&frame_lock))return;
    if(!restored)camera_fault=true;
    if(recoil_applied||recoil_fault){
        const bool read=reader.read(camera+0x14c,angle_native.data(),sizeof(angle_native))&&
            std::isfinite(angle_native[0])&&std::isfinite(angle_native[1]);
        if(!read){angle_native={};recoil_fault=true;recoil.reset();}
        char line[768]{};const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_recoil_camera\",\"ms\":%llu,\"applied\":%s,\"fault\":%s,\"dt\":%.9g,\"delta\":[%.9g,%.9g],\"before\":[%.9g,%.9g],\"written\":[%.9g,%.9g],\"native_after\":[%.9g,%.9g]}\n",
            GetTickCount64(),recoil_applied?"true":"false",recoil_fault?"true":"false",static_cast<double>(dt),
            static_cast<double>(kick.pitch),static_cast<double>(kick.yaw),static_cast<double>(angle_before[0]),static_cast<double>(angle_before[1]),
            static_cast<double>(angle_written[0]),static_cast<double>(angle_written[1]),static_cast<double>(angle_native[0]),static_cast<double>(angle_native[1]));
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
    }
    // Exact native code copies basis vectors to +10/+20/+30 and computes the
    // post-offset eye at +40; +90 is the actor anchor. Read only after native
    // collision/interpolation. +50/+54/+58/+5c feed the native projection.
    if(identity&&camera_calls%12==0){
        std::array<float,16> matrix{};std::array<float,4> anchor{};
        std::array<float,4> projection{};
        const bool measured=reader.read(camera+0x10,matrix.data(),sizeof(matrix))&&
            reader.read(camera+0x90,anchor.data(),sizeof(anchor))&&
            reader.read(camera+0x50,projection.data(),sizeof(projection))&&
            std::all_of(matrix.begin(),matrix.end(),[](float v){return std::isfinite(v)&&std::fabs(v)<100000;})&&
            std::all_of(anchor.begin(),anchor.end(),[](float v){return std::isfinite(v)&&std::fabs(v)<100000;})&&
            std::all_of(projection.begin(),projection.end(),[](float v){return std::isfinite(v)&&std::fabs(v)<100000;});
        if(measured){
            char line[1536]{};int n=std::snprintf(line,sizeof(line),
                "{\"kind\":\"native_camera_geometry\",\"ms\":%llu,\"scoped\":%s,\"basis_eye\":[",
                GetTickCount64(),scoped?"true":"false");
            for(unsigned i=0;i<matrix.size();++i)n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"%s%.9g",i?",":"",static_cast<double>(matrix[i]));
            n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"],\"anchor\":[");
            for(unsigned i=0;i<anchor.size();++i)n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"%s%.9g",i?",":"",static_cast<double>(anchor[i]));
            n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"],\"fov_aspect_near_far\":[");
            for(unsigned i=0;i<projection.size();++i)n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"%s%.9g",i?",":"",static_cast<double>(projection[i]));
            n+=std::snprintf(line+n,sizeof(line)-static_cast<std::size_t>(n),"]}\n");
            if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        }
    }
    if(camera_calls<=3||camera_calls%30==0||scoped||camera_fault){
        char line[1024]{};
        const int n=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_camera_scope\",\"ms\":%llu,\"count\":%llu,\"thread\":%lu,\"pad_thread\":%lu,\"identity\":%s,\"dt\":%.9g,\"scoped\":%s,\"restored\":%s,\"fault\":%s,\"before\":[%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g]}\n",
            GetTickCount64(),camera_calls,GetCurrentThreadId(),pad_thread,identity?"true":"false",static_cast<double>(dt),scoped?"true":"false",restored?"true":"false",camera_fault?"true":"false",
            static_cast<double>(before[0]),static_cast<double>(before[1]),static_cast<double>(before[2]),static_cast<double>(before[3]),
            static_cast<double>(before[4]),static_cast<double>(before[5]),static_cast<double>(before[6]),static_cast<double>(before[7]));
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
    }
    ReleaseSRWLockExclusive(&frame_lock);
}
void frame_sample(const dsr_mw2::EntryRegisters& registers){
    if(frame_finished||frame_log==INVALID_HANDLE_VALUE||!TryAcquireSRWLockExclusive(&frame_lock))return;
    const auto now=GetTickCount64();if(!frame_start)frame_start=now;
    ++frame_calls;
    LocalReader reader;dsr_mw2::Snapshot s;
    const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const auto status=dsr_mw2::observe(reader,base,s);
    if(frame_calls<=3||frame_calls%30==0||s.actions!=previous_frame.actions||
       s.first_bolt.quantity!=previous_frame.first_bolt.quantity||s.player!=previous_frame.player){
        char line[3072]{};std::uint64_t xmm0=0,xmm1=0;
        std::memcpy(&xmm0,registers.xmm[0],8);std::memcpy(&xmm1,registers.xmm[1],8);
        DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
        const int count=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_frame_entry\",\"elapsed_ms\":%llu,\"count\":%llu,\"thread\":%lu,"
            "\"rcx\":\"%llx\",\"rdx\":\"%llx\",\"r8\":\"%llx\",\"r9\":\"%llx\",\"xmm0\":\"%llx\",\"xmm1\":\"%llx\","
            "\"return_rva\":\"%llx\",\"snapshot\":%u,\"hp\":%u,\"weapon\":%d,\"bolts\":%d,\"focused\":%s,"
            "\"player\":\"%llx\",\"manipulator\":\"%llx\",\"active_state\":%u,\"passive_state\":%u,\"actions\":[",
            now-frame_start,frame_calls,GetCurrentThreadId(),registers.rcx,registers.rdx,registers.r8,registers.r9,
            static_cast<unsigned long long>(xmm0),static_cast<unsigned long long>(xmm1),
            static_cast<unsigned long long>(registers.return_address>=base?registers.return_address-base:0),
            static_cast<unsigned>(status),s.hp,s.right_weapon,s.first_bolt.quantity,
            foreground==GetCurrentProcessId()?"true":"false",static_cast<unsigned long long>(s.player),
            static_cast<unsigned long long>(s.manipulator),s.active_state,s.passive_state);
        if(count>0&&count<static_cast<int>(sizeof(line)-300)){
            std::size_t length=static_cast<std::size_t>(count);
            for(std::size_t i=0;i<s.actions.size();++i){
                const int n=std::snprintf(line+length,sizeof(line)-length,"%s%u",i?",":"",unsigned(s.actions[i]));
                if(n>0)length+=static_cast<std::size_t>(n);}
            const char* ending="],\"inventory_writes\":false}\n";
            std::memcpy(line+length,ending,std::strlen(ending));length+=std::strlen(ending);
            DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(length),&written,nullptr);
        }
    }
    previous_frame=s;
    if(now-frame_start>=frame_limit_ms()){
        if(aim_enabled)aim.stop(reader,base,s);
        if(view_enabled){
            dsr_mw2::vm_publish({});dsr_mw2::vm_stop();dsr_mw2::shot_audio_stop();
            if(visibility_installed){
                if(status==dsr_mw2::ReadStatus::ok&&s.player){using Function=void(*)(dsr_mw2::Address);original<Function>(dsr_mw2::EntryPoint::player_visibility)(s.player);}
                dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::player_visibility);
            }
            if(view_installed)dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::render_present);
        }
        if(hud_installed){
            const bool restored=restore_hud(reader,base);
            const bool removed=dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::hud_reticle);
            char line[320]{};const int n=std::snprintf(line,sizeof(line),
                "{\"hud_hook_removed\":%s,\"hud_restored\":%s,\"hud_calls\":%llu,\"hud_scoped_calls\":%llu,\"hud_restores\":%llu,\"hud_fault\":%s}\n",
                removed?"true":"false",restored?"true":"false",hud_calls,hud_scoped_calls,hud_restores,hud_fault?"true":"false");
            if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        }
        frame_finished=true;
        if(camera_installed){
            const bool camera_removed=dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::aim_camera);
            char line[256]{};const int n=std::snprintf(line,sizeof(line),
                "{\"camera_hook_removed\":%s,\"camera_calls\":%llu,\"camera_scoped_calls\":%llu,\"camera_fault\":%s}\n",
                camera_removed?"true":"false",camera_calls,camera_scoped_calls,camera_fault?"true":"false");
            if(n>0&&n<static_cast<int>(sizeof(line))){DWORD written=0;WriteFile(frame_log,line,static_cast<DWORD>(n),&written,nullptr);}
        }
        const bool removed=dsr_mw2::remove_entry_observer();
        if(contracts_enabled){
            const bool pad=dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::pad);
            const bool delta=dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::item_delta);
            const bool set=dsr_mw2::remove_entry_observer(dsr_mw2::EntryPoint::set_count);
            char result[512]{};const int count=std::snprintf(result,sizeof(result),
                "{\"pad_hook_removed\":%s,\"delta_hook_removed\":%s,\"set_hook_removed\":%s,\"pad_calls\":%llu,\"delta_calls\":%llu,\"set_calls\":%llu,\"frame_calls\":%llu}\n",
                pad?"true":"false",delta?"true":"false",set?"true":"false",pad_calls,delta_calls,set_calls,frame_calls);
            if(count>0&&count<static_cast<int>(sizeof(result))){DWORD n=0;WriteFile(frame_log,result,static_cast<DWORD>(count),&n,nullptr);}
        }
        const char* result=removed?"{\"frame_hook_removed\":true}\n":"{\"frame_hook_removed\":false}\n";
        DWORD n=0;WriteFile(frame_log,result,static_cast<DWORD>(std::strlen(result)),&n,nullptr);
    }
    ReleaseSRWLockExclusive(&frame_lock);
}
BOOL CALLBACK initialize(PINIT_ONCE,PVOID,PVOID*) {
    // The renamed retail Windows DLL cannot see Wine's controller devices.
    // Use the installed CrossOver system module, as the other input exports do.
    // A different basename prevents recursion into this xinput1_3 proxy.
    backend=LoadLibraryW(L"C:\\windows\\system32\\xinput1_4.dll");
    if(backend){
        const auto p=GetProcAddress(backend,"XInputGetState");
        static_assert(sizeof(p)==sizeof(get_state));
        std::memcpy(&get_state,&p,sizeof(p));
    }
    char trial[64]{};wchar_t exe[1024]{};
    GetModuleFileNameW(nullptr,exe,1024);
    if(GetEnvironmentVariableA("DSR_MW2_NATIVE_INPUT_TRIAL",trial,64)==13 &&
       !std::strcmp(trial,"validation-v1") &&
       (!_wcsicmp(exe,L"C:\\Games\\DSR-MW2\\DarkSoulsRemastered.exe")||
        !_wcsicmp(exe,L"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DARK SOULS REMASTERED\\DarkSoulsRemastered.exe"))) {
        log_file=CreateFileW(L"C:\\Tools\\DSR-MW2\\native-input-v1.jsonl",FILE_APPEND_DATA,FILE_SHARE_READ,
                             nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        char gun_mode[64]{};
        gun_enabled=GetEnvironmentVariableA("DSR_MW2_GUN_TRIAL",gun_mode,64)==7&&!std::strcmp(gun_mode,"play-v1");
        char session_mode[64]{},loadout_mode[64]{};
        loadout_session=gun_enabled&&GetEnvironmentVariableA("DSR_MW2_LOADOUT_TRIAL",loadout_mode,64)==10&&!std::strcmp(loadout_mode,"bonfire-v1")&&
            GetEnvironmentVariableA("DSR_MW2_SESSION_TRIAL",session_mode,64)==15&&!std::strcmp(session_mode,"loadout-600s-v1");
        owner_session=gun_enabled&&!std::strcmp(loadout_mode,"bonfire-v1")&&
            GetEnvironmentVariableA("DSR_MW2_SESSION_TRIAL",session_mode,64)==16&&!std::strcmp(session_mode,"owner-2h-test-v1");
        unlimited_ammo=owner_session;
        if(owner_session){
            crash_base=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
            const bool guarded=dsr_mw2::install_input_lookup_guard(crash_base);
            const char* message=guarded?"{\"input_lookup_empty_guard\":true}\n":"{\"input_lookup_empty_guard\":false}\n";
            if(log_file!=INVALID_HANDLE_VALUE){DWORD written=0;WriteFile(log_file,message,static_cast<DWORD>(std::strlen(message)),&written,nullptr);}
            crash_log=CreateFileW(L"C:\\Tools\\DSR-MW2\\native-crash-v1.jsonl",FILE_APPEND_DATA,FILE_SHARE_READ,
                                 nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(crash_log!=INVALID_HANDLE_VALUE)AddVectoredExceptionHandler(0,record_native_crash);
        }
        char aim_mode[64]{};
        aim_enabled=gun_enabled&&GetEnvironmentVariableA("DSR_MW2_AIM_TRIAL",aim_mode,64)==7&&!std::strcmp(aim_mode,"hold-v1");
        char camera_mode[64]{};
        camera_enabled=aim_enabled&&GetEnvironmentVariableA("DSR_MW2_CAMERA_TRIAL",camera_mode,64)==8&&!std::strcmp(camera_mode,"frame-v1");
        char hud_mode[64]{};
        hud_enabled=camera_enabled&&GetEnvironmentVariableA("DSR_MW2_HUD_TRIAL",hud_mode,64)==10&&!std::strcmp(hud_mode,"reticle-v1");
        char view_mode[64]{};
        view_enabled=hud_enabled&&GetEnvironmentVariableA("DSR_MW2_VIEWMODEL_TRIAL",view_mode,64)==12&&
            !std::strcmp(view_mode,"source-vm-v1")&&dsr_mw2::vm_load(L"C:\\Tools\\DSR-MW2\\viewmodel-v1\\m9.dsrvm")&&dsr_mw2::vm_load(L"C:\\Tools\\DSR-MW2\\viewmodel-v1\\intervention.dsrvm",true);
        audio_enabled=view_enabled&&gun_enabled&&
            dsr_mw2::shot_audio_load(L"C:\\Tools\\DSR-MW2\\viewmodel-v1\\m9-shot.wav",false)&&
            dsr_mw2::shot_audio_load(L"C:\\Tools\\DSR-MW2\\viewmodel-v1\\intervention-shot.wav",true);
        char frame_mode[64]{};
        if(GetEnvironmentVariableA("DSR_MW2_FRAME_TRIAL",frame_mode,64)==10){
            post_enabled=!std::strcmp(frame_mode,"observe-v3");
            contracts_enabled=post_enabled||!std::strcmp(frame_mode,"observe-v2");
            frame_enabled=contracts_enabled||!std::strcmp(frame_mode,"observe-v1");
        }
    }
    return TRUE;
}
// Read-only ESD state trace (owner sessions only): discovers the player's live
// EzState records by signature, then logs every machine-0/machine-1 state change
// with the live HP. Region-checked reads never touch guard/no-access pages.
struct ProbeReader final:dsr_mw2::Reader {
    struct Region{std::uintptr_t base,end;bool ok;};
    mutable Region cache[64]{};mutable unsigned next=0;
    void clear(){for(auto& r:cache)r={0,0,false};next=0;}
    bool readable(std::uintptr_t at,std::size_t n)const{
        for(const auto& r:cache)if(r.end&&at>=r.base&&at<r.end)return r.ok&&n<=r.end-at;
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<void*>(at),&m,sizeof(m)))return false;
        const DWORD access=PAGE_READONLY|PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY;
        const bool ok=m.State==MEM_COMMIT&&(m.Protect&access)&&!(m.Protect&(PAGE_GUARD|PAGE_NOACCESS));
        const auto base=reinterpret_cast<std::uintptr_t>(m.BaseAddress);
        cache[next++%64]={base,base+m.RegionSize,ok};
        return ok&&n<=base+m.RegionSize-at;
    }
    bool read(dsr_mw2::Address at,void* dst,std::size_t bytes)const override {
        if(!readable(static_cast<std::uintptr_t>(at),bytes))return false;
        SIZE_T n=0;return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(at),dst,bytes,&n)&&n==bytes;
    }
};
dsr_mw2::EsdStateProbe esd_probe{dsr_mw2::esd_state_table,sizeof(dsr_mw2::esd_state_table)/sizeof(dsr_mw2::esd_state_table[0]),dsr_mw2::esd_state_span};
ProbeReader esd_reader;
dsr_mw2::Address esd_root=0;
std::size_t esd_logged=0;
bool esd_finish_logged=false;
ULONGLONG esd_started=0,esd_retry_at=0,esd_cache_at=0,esd_heartbeat=0,esd_window=0;
unsigned esd_lines=0,esd_suppressed=0;
void esd_write(const char* text,int n){
    if(n>0&&log_file!=INVALID_HANDLE_VALUE){DWORD written=0;WriteFile(log_file,text,static_cast<DWORD>(n),&written,nullptr);}
}
void esd_tick(ULONGLONG now){
    if(!owner_session||!esd_root)return;
    if(esd_root!=esd_probe.root()||(esd_retry_at&&now>=esd_retry_at)){
        esd_reader.clear();esd_probe.reset(esd_root);esd_logged=0;esd_finish_logged=false;
        esd_started=now;esd_retry_at=0;esd_cache_at=now;
    }
    if(now-esd_cache_at>=2000){esd_reader.clear();esd_cache_at=now;}
    if(!esd_probe.finished())esd_probe.step(esd_reader,256);
    char line[512];
    while(esd_logged<esd_probe.holders()){
        const auto& h=esd_probe.holder(esd_logged);
        char path[96]{};int at=0;
        for(std::uint8_t k=0;k<h.length&&at<80;++k)at+=std::snprintf(path+at,sizeof(path)-static_cast<std::size_t>(at),"%s%u",k?",":"",static_cast<unsigned>(h.path[k]));
        esd_write(line,std::snprintf(line,sizeof(line),"{\"kind\":\"esd_holder\",\"ms\":%llu,\"holder\":%zu,\"path\":[%s],\"machine\":%d,\"state\":%d,\"near_buffer\":%s,\"root\":\"%llx\"}\n",
            now,esd_logged,path,h.last.machine,h.last.state,h.near_buffer?"true":"false",static_cast<unsigned long long>(esd_root)));
        ++esd_logged;
    }
    if(esd_probe.finished()&&!esd_finish_logged){
        esd_finish_logged=true;
        esd_write(line,std::snprintf(line,sizeof(line),"{\"kind\":\"esd_probe\",\"ms\":%llu,\"status\":\"%s\",\"holders\":%zu,\"nodes\":%zu,\"reads\":%zu,\"internal\":%zu,\"elapsed_ms\":%llu}\n",
            now,esd_probe.holders()?"finished":"not_found",esd_probe.holders(),esd_probe.nodes(),esd_probe.reads(),esd_probe.internal(),now-esd_started));
        if(!esd_probe.holders())esd_retry_at=now+30000;
    }
    if(!esd_logged)return;
    if(now-esd_window>=1000){
        if(esd_suppressed)esd_write(line,std::snprintf(line,sizeof(line),"{\"kind\":\"esd_suppressed\",\"ms\":%llu,\"lines\":%u}\n",now,esd_suppressed));
        esd_window=now;esd_lines=0;esd_suppressed=0;
    }
    std::uint32_t hp=0;const bool hp_read=esd_reader.get(esd_root,0x3e8,hp);
    for(std::size_t i=0;i<esd_logged;++i){
        auto& h=esd_probe.holder(i);
        const auto hit=esd_probe.resolve(esd_reader,i);
        if(hit==h.last)continue;
        if(esd_lines>=60){++esd_suppressed;continue;}
        ++esd_lines;
        esd_write(line,std::snprintf(line,sizeof(line),"{\"kind\":\"esd_state\",\"ms\":%llu,\"holder\":%zu,\"machine\":%d,\"state\":%d,\"from_machine\":%d,\"from\":%d,\"hp\":%d}\n",
            now,i,hit.machine,hit.state,h.last.machine,h.last.state,hp_read?static_cast<int>(hp):-1));
        h.last=hit;
    }
    if(now-esd_heartbeat>=5000){
        esd_heartbeat=now;
        char states[24*16]{};int at=0;
        for(std::size_t i=0;i<esd_logged&&at<static_cast<int>(sizeof(states))-16;++i)
            at+=std::snprintf(states+at,sizeof(states)-static_cast<std::size_t>(at),"%s[%d,%d]",i?",":"",esd_probe.holder(i).last.machine,esd_probe.holder(i).last.state);
        esd_write(line,std::snprintf(line,sizeof(line),"{\"kind\":\"esd_heartbeat\",\"ms\":%llu,\"hp\":%d,\"states\":[%s]}\n",now,hp_read?static_cast<int>(hp):-1,states));
    }
}
// Read-only interaction trace (owner sessions only): ladders/doors never
// raised native requests 43/47. On each Cross/A or E press, record the native
// action bits, weapons, stance and live ESD states for 1.5 s whenever they change.
ULONGLONG interact_until=0;bool interact_was_down=false;
std::array<std::uint8_t,0x35> interact_last{};
std::uint64_t guard_logged=0;ULONGLONG guard_log_at=0;
// Read-only snapshots of the player instance, its two model objects and its
// control block at load, aim start/release, HP reaching zero and each
// interaction press, so state left changed by aiming can be diffed offline.
bool dump_was_aiming=false;dsr_mw2::Address dump_player=0;bool dump_hp_zero=false;
void chr_dump(ULONGLONG now,const char* reason,dsr_mw2::Address player){
    LocalReader reader;
    dsr_mw2::Address model=0,model2=0,control=0;
    reader.get(player,0x60,model);reader.get(player,0x850,model2);reader.get(player,0x68,control);
    const struct {const char* name;dsr_mw2::Address at;std::size_t size;} regions[]={
        {"chr",player,0x900},{"model",model,0x100},{"model2",model2,0x100},{"control",control,0x200}};
    static char line[16384];
    int at=std::snprintf(line,sizeof(line),"{\"kind\":\"chr_dump\",\"ms\":%llu,\"reason\":\"%s\",\"player\":\"%llx\"",
        now,reason,static_cast<unsigned long long>(player));
    for(const auto& r:regions){
        static std::uint8_t bytes[0x900];std::memset(bytes,0,sizeof(bytes));
        const bool ok=r.at>=0x10000&&reader.read(r.at,bytes,r.size);
        at+=std::snprintf(line+at,sizeof(line)-static_cast<std::size_t>(at),",\"%s\":\"",r.name);
        for(std::size_t i=0;ok&&i<r.size&&at+3<static_cast<int>(sizeof(line))-64;++i)
            at+=std::snprintf(line+at,sizeof(line)-static_cast<std::size_t>(at),"%02x",bytes[i]);
        at+=std::snprintf(line+at,sizeof(line)-static_cast<std::size_t>(at),"\"");
    }
    at+=std::snprintf(line+at,sizeof(line)-static_cast<std::size_t>(at),"}\n");
    esd_write(line,at);
}
void interact_tick(ULONGLONG now,DWORD result,const XINPUT_STATE* state){
    if(!owner_session||log_file==INVALID_HANDLE_VALUE)return;
    const auto hits=dsr_mw2::input_lookup_guard_hits();
    if(hits!=guard_logged&&now-guard_log_at>=1000){
        char note[160];
        esd_write(note,std::snprintf(note,sizeof(note),"{\"kind\":\"input_lookup_empty\",\"ms\":%llu,\"hits\":%llu,\"new\":%llu}\n",
            now,static_cast<unsigned long long>(hits),static_cast<unsigned long long>(hits-guard_logged)));
        guard_logged=hits;guard_log_at=now;
    }
    const bool pad_down=result==ERROR_SUCCESS&&state&&(state->Gamepad.wButtons&XINPUT_GAMEPAD_A);
    DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
    const bool focused=foreground==GetCurrentProcessId();
    const bool down=focused&&(pad_down||(GetAsyncKeyState('E')&0x8000));
    const bool press=down&&!interact_was_down;interact_was_down=down;
    if(press)interact_until=now+1500;
    if(esd_root&&esd_root!=dump_player){dump_player=esd_root;dump_hp_zero=false;chr_dump(now,"loaded",esd_root);}
    const bool aiming=aim.owned;
    if(esd_root&&aiming!=dump_was_aiming)chr_dump(now,aiming?"aim_started":"aim_released",esd_root);
    dump_was_aiming=aiming;
    if(esd_root){
        std::uint32_t live_hp=1;LocalReader hp_reader;
        if(hp_reader.get(esd_root,0x3e8,live_hp)){
            if(!live_hp&&!dump_hp_zero){dump_hp_zero=true;chr_dump(now,"hp_zero",esd_root);}
            else if(live_hp)dump_hp_zero=false;
        }
    }
    if(press&&esd_root)chr_dump(now,"interact_press",esd_root);
    if(now>interact_until)return;
    LocalReader reader;dsr_mw2::Snapshot s;
    const auto status=dsr_mw2::observe(reader,reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr)),s);
    if(!press&&s.actions==interact_last)return;
    interact_last=s.actions;
    char bits[200]{};int at=0;
    for(unsigned i=0;i<s.actions.size()&&at<180;++i)if(s.actions[i])at+=std::snprintf(bits+at,sizeof(bits)-static_cast<std::size_t>(at),"%s%u",at?",":"",i);
    char states[64]{};int sat=0;
    for(std::size_t i=0;i<esd_logged&&i<3;++i)
        sat+=std::snprintf(states+sat,sizeof(states)-static_cast<std::size_t>(sat),"%s[%d,%d]",i?",":"",esd_probe.holder(i).last.machine,esd_probe.holder(i).last.state);
    char line[512];
    esd_write(line,std::snprintf(line,sizeof(line),
        "{\"kind\":\"interact_trace\",\"ms\":%llu,\"press\":%s,\"pad\":%s,\"snapshot\":%u,\"hp\":%u,\"right\":%d,\"left\":%d,\"style\":%u,\"actions\":[%s],\"esd\":[%s],\"guard_hits\":%llu}\n",
        now,press?"true":"false",pad_down?"true":"false",static_cast<unsigned>(status),s.hp,s.right_weapon,s.left_weapon,s.weapon_style,bits,states,static_cast<unsigned long long>(dsr_mw2::input_lookup_guard_hits())));
}
void sample(DWORD slot,DWORD result,const XINPUT_STATE* state,dsr_mw2::Address caller) {
    AcquireSRWLockExclusive(&controller_lock);
    if(result==ERROR_SUCCESS&&state&&(controller_slot==slot||controller_slot>=4||GetTickCount64()-controller_stamp>=250)){
        controller=state->Gamepad;controller_slot=slot;controller_stamp=GetTickCount64();
    }else if(result!=ERROR_SUCCESS&&controller_slot==slot){controller={};controller_slot=4;controller_stamp=0;}
    ReleaseSRWLockExclusive(&controller_lock);
    if(log_file==INVALID_HANDLE_VALUE || !TryAcquireSRWLockExclusive(&log_lock))return;
    ++calls;
    const auto now=GetTickCount64();
    esd_tick(now);
    interact_tick(now,result,state);
    if(now-last_sample>=500) {
        last_sample=now;
        LocalReader reader;dsr_mw2::Snapshot s;
        const auto status=dsr_mw2::observe(reader,reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr)),s);
        if(status==dsr_mw2::ReadStatus::ok)esd_root=s.player;
        const auto base=reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
        DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
        if(frame_enabled&&!frame_attempted&&status==dsr_mw2::ReadStatus::ok&&s.hp&&dsr_mw2::is_m9(s.right_weapon)&&
           foreground==GetCurrentProcessId()){
            frame_attempted=true;
            frame_log=CreateFileW(gun_enabled?L"C:\\Tools\\DSR-MW2\\native-gun-v1.jsonl":post_enabled?L"C:\\Tools\\DSR-MW2\\native-post-v3.jsonl":contracts_enabled?L"C:\\Tools\\DSR-MW2\\native-contracts-v2.jsonl":L"C:\\Tools\\DSR-MW2\\native-frame-v1.jsonl",FILE_APPEND_DATA,FILE_SHARE_READ,
                                 nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(frame_log!=INVALID_HANDLE_VALUE){
                const bool installed=dsr_mw2::install_entry_observer(reinterpret_cast<void*>(base+0x15ce90),frame_sample);
                if(installed&&contracts_enabled){
                    const bool pad=post_enabled?dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(base+0x396860),reinterpret_cast<void*>(&post_pad),dsr_mw2::EntryPoint::pad):
                        dsr_mw2::install_entry_observer(reinterpret_cast<void*>(base+0x396860),pad_sample,dsr_mw2::EntryPoint::pad);
                    const bool delta=post_enabled?dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(base+0x749310),reinterpret_cast<void*>(&post_delta),dsr_mw2::EntryPoint::item_delta):
                        dsr_mw2::install_entry_observer(reinterpret_cast<void*>(base+0x749310),delta_sample,dsr_mw2::EntryPoint::item_delta);
                    const bool set=dsr_mw2::install_entry_observer(reinterpret_cast<void*>(base+0x747ed0),set_sample,dsr_mw2::EntryPoint::set_count);
                    if(camera_enabled)camera_installed=dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(base+0x231620),reinterpret_cast<void*>(&scoped_camera),dsr_mw2::EntryPoint::aim_camera);
                    if(view_enabled){
                        view_installed=dsr_mw2::install_entry_observer(reinterpret_cast<void*>(base+0xcd4630),view_present,dsr_mw2::EntryPoint::render_present);
                        if(view_installed)visibility_installed=dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(base+0x3549e0),reinterpret_cast<void*>(&view_visibility),dsr_mw2::EntryPoint::player_visibility);
                        if(!view_installed||!visibility_installed){dsr_mw2::vm_stop();view_enabled=false;}
                    }
                    if(hud_enabled&&pad&&camera_installed&&hud_contract(base))
                        hud_installed=dsr_mw2::install_entry_redirect(reinterpret_cast<void*>(base+0x67bb20),reinterpret_cast<void*>(&scoped_hud),dsr_mw2::EntryPoint::hud_reticle);
                    char result[320]{};const int n=std::snprintf(result,sizeof(result),
                        "{\"pad_installed\":%s,\"delta_installed\":%s,\"set_installed\":%s,\"hud_installed\":%s,\"max_ms\":%u}\n",pad?"true":"false",delta?"true":"false",set?"true":"false",hud_installed?"true":"false",frame_limit_ms());
                    if(n>0&&n<static_cast<int>(sizeof(result))){DWORD written=0;WriteFile(frame_log,result,static_cast<DWORD>(n),&written,nullptr);}
                }
                const char* message=installed?"{\"frame_hook_installed\":true,\"frame_only_max_ms\":30000}\n":"{\"frame_hook_installed\":false}\n";
                DWORD written=0;WriteFile(frame_log,message,static_cast<DWORD>(std::strlen(message)),&written,nullptr);
            }
        }
        const auto p=result==ERROR_SUCCESS&&state?state->Gamepad:XINPUT_GAMEPAD{};
        char line[1536]{};
        const int count=std::snprintf(line,sizeof(line),
            "{\"kind\":\"native_xinput_call\",\"ms\":%llu,\"calls\":%llu,\"thread\":%lu,\"slot\":%lu,\"result\":%lu,\"caller_rva\":\"%llx\","
            "\"buttons\":%u,\"lt\":%u,\"rt\":%u,\"lx\":%d,\"ly\":%d,\"rx\":%d,\"ry\":%d,\"focused\":%s,"
            "\"snapshot\":%u,\"hp\":%u,\"weapon\":%d,\"bolts\":%d,\"player\":\"%llx\",\"manipulator\":\"%llx\","
            "\"actions\":[%u,%u,%u,%u,%u,%u],\"input_modified\":false}\n",
            now,calls,GetCurrentThreadId(),slot,result,static_cast<unsigned long long>(caller>=base?caller-base:0),static_cast<unsigned>(p.wButtons),
            static_cast<unsigned>(p.bLeftTrigger),static_cast<unsigned>(p.bRightTrigger),
            static_cast<int>(p.sThumbLX),static_cast<int>(p.sThumbLY),static_cast<int>(p.sThumbRX),static_cast<int>(p.sThumbRY),
            foreground==GetCurrentProcessId()?"true":"false",static_cast<unsigned>(status),s.hp,s.right_weapon,s.first_bolt.quantity,
            static_cast<unsigned long long>(s.player),static_cast<unsigned long long>(s.manipulator),
            s.actions[0],s.actions[1],s.actions[2],s.actions[3],s.actions[4],s.actions[5]);
        if(count>0&&count<static_cast<int>(sizeof(line))) {DWORD written=0;WriteFile(log_file,line,static_cast<DWORD>(count),&written,nullptr);}
    }
    ReleaseSRWLockExclusive(&log_lock);
}
}
extern "C" DWORD WINAPI XInputGetState(DWORD index,XINPUT_STATE* state) {
    InitOnceExecuteOnce(&once,initialize,nullptr,nullptr);
    if(!get_state)return ERROR_DEVICE_NOT_CONNECTED;
    const DWORD result=get_state(index,state);
    sample(index,result,state,reinterpret_cast<dsr_mw2::Address>(__builtin_return_address(0)));
    return result;
}
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID){return TRUE;}
