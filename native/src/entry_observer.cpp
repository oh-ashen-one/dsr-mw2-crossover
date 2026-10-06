// Original one-entry native trace. No remote process/debug attachment or game
// state writes. Local executable mutation is explicit and exact-byte bounded.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <array>
#include <cstring>
#include "entry_observer.hpp"
#include "input_lookup_guard.hpp"

extern "C" void DsrEntryObserverShim0();
extern "C" void DsrEntryObserverShim1();
extern "C" void DsrEntryObserverShim2();
extern "C" void DsrEntryObserverShim3();
extern "C" void DsrEntryObserverShim4();
extern "C" void DsrEntryObserverShim5();
extern "C" void DsrEntryObserverShim6();
extern "C" void DsrEntryObserverShim7();
extern "C" {void* DsrEntryTrampolines[8]={};}
namespace {
struct Slot {
    void* entry=nullptr;
    bool published=false;
    dsr_mw2::EntryCallback notify=nullptr;
    std::array<unsigned char,21> patch{};
};
std::array<Slot,8> slots{};
const unsigned char* prefixes[]={dsr_mw2::frame_prefix,dsr_mw2::pad_prefix,dsr_mw2::delta_prefix,dsr_mw2::set_count_prefix,dsr_mw2::aim_camera_prefix,dsr_mw2::hud_reticle_prefix,dsr_mw2::player_visibility_prefix,dsr_mw2::render_present_prefix};
constexpr std::size_t sizes[]={16,21,16,16,16,18,20,17};
void(*const shims[])()={DsrEntryObserverShim0,DsrEntryObserverShim1,DsrEntryObserverShim2,DsrEntryObserverShim3,DsrEntryObserverShim4,DsrEntryObserverShim5,DsrEntryObserverShim6,DsrEntryObserverShim7};
// Preallocated handles: no C++ allocation while other native threads suspend.
struct FrozenThreads {
    std::array<HANDLE,512> handles{};
    std::size_t count=0,suspended=0;
    bool freeze(const void* address,std::size_t size){
        const auto first=reinterpret_cast<DWORD64>(address);
        HANDLE list=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
        if(list==INVALID_HANDLE_VALUE)return false;
        THREADENTRY32 t{};t.dwSize=sizeof(t);bool okay=true;
        for(BOOL more=Thread32First(list,&t);more;more=Thread32Next(list,&t)){
            if(t.th32OwnerProcessID!=GetCurrentProcessId()||t.th32ThreadID==GetCurrentThreadId())continue;
            if(count==handles.size()){okay=false;break;}
            HANDLE h=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,t.th32ThreadID);
            if(!h){okay=false;break;}handles[count++]=h;
        }
        CloseHandle(list);
        if(!okay)return false;
        for(std::size_t i=0;i<count;++i){
            if(SuspendThread(handles[i])==DWORD(-1))return false;
            ++suspended;
            CONTEXT c{};c.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(handles[i],&c)||(c.Rip>=first&&c.Rip<first+size))return false;
        }
        return true;
    }
    ~FrozenThreads(){
        for(std::size_t i=0;i<suspended;++i)ResumeThread(handles[i]);
        for(std::size_t i=0;i<count;++i)CloseHandle(handles[i]);
    }
};
void jump(unsigned char* data,const void* destination){
    data[0]=0xff;data[1]=0x25;std::memset(data+2,0,4);
    std::memcpy(data+6,&destination,sizeof(destination));
}
bool replace(Slot& slot,std::size_t size,const void* expected,const void* replacement){
    void* entry=slot.entry;
    FrozenThreads frozen;
    if(!frozen.freeze(entry,size)||std::memcmp(entry,expected,size))return false;
    DWORD old=0;
    if(!VirtualProtect(entry,size,PAGE_EXECUTE_READWRITE,&old))return false;
    std::memcpy(entry,replacement,size);
    const bool flushed=FlushInstructionCache(GetCurrentProcess(),entry,size)!=FALSE;
    DWORD unused=0;const bool restored=VirtualProtect(entry,size,old,&unused)!=FALSE;
    return flushed&&restored;
}
}
extern "C" void DsrEntryObserverRecord(const dsr_mw2::EntryRegisters* regs,unsigned index){
    if(index<slots.size()&&slots[index].notify&&regs)slots[index].notify(*regs);
}
namespace dsr_mw2 {
bool install_input_lookup_guard(std::uintptr_t base){
    static Slot guard;
    if(guard.published)return true;
    const auto* completion=reinterpret_cast<const void*>(base+0x54c618);
    constexpr unsigned char completion_prefix[]={0x48,0x8b,0x56,0x08,0x48,0x8b,0x0e};
    auto* target=reinterpret_cast<void*>(base+0x54c4c4);
    if(std::memcmp(target,input_lookup_prefix.data(),input_lookup_prefix.size())||
       std::memcmp(completion,completion_prefix,sizeof(completion_prefix)))return false;
    auto* executable=VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!executable)return false;
    const auto code=input_lookup_code(base+0x54c4d7,base+0x54c618);
    std::memcpy(executable,code.data(),code.size());DWORD old=0;
    if(!VirtualProtect(executable,4096,PAGE_EXECUTE_READ,&old)||
       !FlushInstructionCache(GetCurrentProcess(),executable,code.size())){
        VirtualFree(executable,0,MEM_RELEASE);return false;
    }
    guard.entry=target;guard.patch.fill(0x90);jump(guard.patch.data(),executable);
    // Reuse the existing thread-freeze and exact-byte replacement protocol.
    // A published executable page lives until process exit, including a rare
    // cache/protection failure after copying the patch; never free a jump target.
    guard.published=replace(guard,input_lookup_prefix.size(),input_lookup_prefix.data(),guard.patch.data());
    return guard.published;
}
bool install(void* target,EntryCallback callback,void* redirect,EntryPoint point){
    const auto index=static_cast<unsigned>(point);
    if(index>=slots.size())return false;
    auto& slot=slots[index];const auto size=sizes[index];const auto* prefix=prefixes[index];
    if(slot.published||slot.entry||!target||(!callback&&!redirect)||std::memcmp(target,prefix,size))return false;
    auto* trampoline=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!trampoline)return false;
    std::memcpy(trampoline,prefix,size);jump(trampoline+size,static_cast<unsigned char*>(target)+size);
    DWORD old=0;
    if(!VirtualProtect(trampoline,4096,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),trampoline,size+14)){
        VirtualFree(trampoline,0,MEM_RELEASE);return false;}
    slot.patch.fill(0x90);jump(slot.patch.data(),redirect?redirect:reinterpret_cast<void*>(shims[index]));
    slot.entry=target;slot.notify=callback;DsrEntryTrampolines[index]=trampoline;slot.published=true;
    if(replace(slot,size,prefix,slot.patch.data()))return true;
    // A failed protection/flush after memcpy may still have changed the entry.
    // Keep its valid trampoline/callback alive; never free beneath patched code.
    if(!std::memcmp(slot.entry,slot.patch.data(),size))return false;
    VirtualFree(trampoline,0,MEM_RELEASE);slot.entry=nullptr;slot.notify=nullptr;DsrEntryTrampolines[index]=nullptr;return false;
}
bool install_entry_observer(void* target,EntryCallback callback,EntryPoint point){
    return install(target,callback,nullptr,point);
}
bool install_entry_redirect(void* target,void* redirect,EntryPoint point){
    return install(target,nullptr,redirect,point);
}
void* entry_trampoline(EntryPoint point){
    const auto index=static_cast<unsigned>(point);
    return index<slots.size()?DsrEntryTrampolines[index]:nullptr;
}
bool remove_entry_observer(EntryPoint point){
    const auto index=static_cast<unsigned>(point);
    if(index>=slots.size())return false;
    auto& slot=slots[index];if(!slot.entry)return false;
    if(!replace(slot,sizes[index],slot.patch.data(),prefixes[index]))return false;
    // Keep each tiny trampoline until process exit: an in-flight shim may use it.
    slot.entry=nullptr;return true;
}
}
