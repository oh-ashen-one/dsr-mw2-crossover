// Original bounded debugger instrumentation, disposable offline validation only.
// No DLL injection, executable patch, inventory write or input synthesis.
// Hardware debug-register edits are restored before detach. Not a game feature.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <bcrypt.h>
#include <array>
#include <vector>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include "dsr_snapshot.hpp"

namespace {
struct Reader final:dsr_mw2::Reader {
    HANDLE process;
    explicit Reader(HANDLE p):process(p){}
    bool read(dsr_mw2::Address at,void* out,std::size_t bytes)const override {
        SIZE_T n=0;return ReadProcessMemory(process,reinterpret_cast<const void*>(at),out,bytes,&n)&&n==bytes;
    }
};
bool private_image(HANDLE game) {
    wchar_t path[1024]{};DWORD n=1024;
    if(!QueryFullProcessImageNameW(game,0,path,&n))return false;
    if(_wcsicmp(path,L"C:\\Games\\DSR-MW2\\DarkSoulsRemastered.exe") &&
       _wcsicmp(path,L"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DARK SOULS REMASTERED\\DarkSoulsRemastered.exe"))return false;
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    BCRYPT_ALG_HANDLE alg=nullptr;BCRYPT_HASH_HANDLE h=nullptr;
    bool ok=BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0;
    if(ok)ok=BCryptCreateHash(alg,&h,nullptr,0,nullptr,0,0)>=0;
    std::array<UCHAR,65536> block{};
    while(ok){if(!ReadFile(file,block.data(),static_cast<DWORD>(block.size()),&n,nullptr)){ok=false;break;}
        if(!n)break;
        ok=BCryptHashData(h,block.data(),n,0)>=0;}
    std::array<UCHAR,32> hash{};
    if(ok)ok=BCryptFinishHash(h,hash.data(),32,0)>=0;
    const std::array<UCHAR,32> expected{0xa4,0x5a,0xaa,0x36,0xdd,0x2f,0x6c,0xc1,0x51,0x67,0x0a,0x63,0x9e,0xa5,0x54,0x70,
        0x43,0xcf,0x38,0xea,0x79,0xff,0x41,0x78,0xb9,0x63,0xc6,0xed,0x71,0xf9,0x8d,0x7b};
    if(h)BCryptDestroyHash(h);
    if(alg)BCryptCloseAlgorithmProvider(alg,0);
    CloseHandle(file);
    return ok&&hash==expected;
}
constexpr std::array<DWORD64,4> rvas{0x15ce90,0x396860,0x749310,0x747ed0};
constexpr const char* names[]{"frame_entry","pad_step","item_delta_candidate","item_set_quantity_candidate"};
struct Thread { DWORD id; HANDLE handle; CONTEXT original; bool changed=false; };
bool arm(Thread& thread,DWORD64 base) {
    thread.original={};thread.original.ContextFlags=CONTEXT_DEBUG_REGISTERS;
    if(!GetThreadContext(thread.handle,&thread.original))return false;
    const auto& old=thread.original;
    // Preserve another debugger's or runtime's existing hardware instrumentation.
    if(old.Dr0||old.Dr1||old.Dr2||old.Dr3||(old.Dr7&0xff))return false;
    CONTEXT next=old;next.Dr0=base+rvas[0];next.Dr1=base+rvas[1];
    next.Dr2=base+rvas[2];next.Dr3=base+rvas[3];next.Dr6=0;next.Dr7=(old.Dr7&0xff00)|0x55;
    // Mark before the call: a failed API is not permission to assume no change.
    thread.changed=true;
    return SetThreadContext(thread.handle,&next)!=FALSE;
}
bool restore(Thread& thread) {
    if(!thread.changed)return true;
    if(WaitForSingleObject(thread.handle,0)==WAIT_OBJECT_0){thread.changed=false;return true;}
    if(SuspendThread(thread.handle)==DWORD(-1))return false;
    const bool ok=SetThreadContext(thread.handle,&thread.original)!=FALSE;
    const bool resumed=ResumeThread(thread.handle)!=DWORD(-1);
    if(ok)thread.changed=false;
    return ok&&resumed;
}
}

int main() {
    char permission[64]{};
    if(GetEnvironmentVariableA("DSR_MW2_DISPOSABLE_TRACE",permission,64)!=21 ||
       std::strcmp(permission,"validation-20-seconds"))return 64;
    HANDLE list=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(list==INVALID_HANDLE_VALUE)return 65;
    PROCESSENTRY32W p{};p.dwSize=sizeof(p);DWORD pid=0;unsigned matches=0;
    for(BOOL ok=Process32FirstW(list,&p);ok;ok=Process32NextW(list,&p))
        if(!_wcsicmp(p.szExeFile,L"DarkSoulsRemastered.exe")){pid=p.th32ProcessID;++matches;}
    CloseHandle(list);if(matches!=1)return 66;
    HANDLE game=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ|SYNCHRONIZE,FALSE,pid);
    if(!game||!private_image(game)){if(game)CloseHandle(game);return 67;}
    HANDLE modules=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
    MODULEENTRY32W mod{};mod.dwSize=sizeof(mod);DWORD64 base=0;
    if(modules!=INVALID_HANDLE_VALUE){
        for(BOOL ok=Module32FirstW(modules,&mod);ok;ok=Module32NextW(modules,&mod))
            if(!_wcsicmp(mod.szModule,L"DarkSoulsRemastered.exe"))base=reinterpret_cast<DWORD64>(mod.modBaseAddr);
        CloseHandle(modules);}
    Reader reader(game);dsr_mw2::Snapshot initial;
    if(!base||dsr_mw2::observe(reader,base,initial)!=dsr_mw2::ReadStatus::ok||!initial.hp||!dsr_mw2::is_m9(initial.right_weapon)){
        CloseHandle(game);return 68;}
    const std::array<std::array<unsigned char,4>,4> prefixes{{
        {{0x48,0x8b,0xc4,0x57}},{{0x48,0x8b,0xc4,0x55}},
        {{0x40,0x53,0x56,0x57}},{{0x48,0x89,0x5c,0x24}}}};
    for(unsigned i=0;i<4;++i){std::array<unsigned char,4> bytes{};
        if(!reader.read(base+rvas[i],bytes.data(),bytes.size())||bytes!=prefixes[i]){CloseHandle(game);return 68;}}
    if(!DebugActiveProcess(pid)){
        std::printf("{\"error\":\"debug_attach_unsupported_or_refused\",\"code\":%lu}\n",GetLastError());CloseHandle(game);return 69;}
    if(!DebugSetProcessKillOnExit(FALSE)){
        std::printf("{\"error\":\"non_killing_debug_mode_unavailable\",\"code\":%lu}\n",GetLastError());
        DebugActiveProcessStop(pid);CloseHandle(game);return 70;}
    std::vector<Thread> threads;threads.reserve(128);
    const ULONGLONG start=GetTickCount64();bool good=true,exited=false,first_break=true;
    std::array<unsigned,4> hits{};
    std::printf("{\"status\":\"attached\",\"pid\":%lu,\"maximum_ms\":20000,\"inventory_writes\":false}\n",pid);std::fflush(stdout);
    while(good && GetTickCount64()-start<20000) {
        DEBUG_EVENT ev{};
        if(!WaitForDebugEvent(&ev,100)){if(GetLastError()==ERROR_SEM_TIMEOUT)continue;good=false;break;}
        DWORD disposition=DBG_CONTINUE;
        if(ev.dwProcessId!=pid){good=false;disposition=DBG_EXCEPTION_NOT_HANDLED;}
        else if(ev.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT||ev.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT){
            HANDLE handle=ev.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT?ev.u.CreateProcessInfo.hThread:ev.u.CreateThread.hThread;
            if(ev.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT){
                if(ev.u.CreateProcessInfo.hFile)CloseHandle(ev.u.CreateProcessInfo.hFile);
                if(ev.u.CreateProcessInfo.hProcess)CloseHandle(ev.u.CreateProcessInfo.hProcess);}
            if(threads.size()>=128){CloseHandle(handle);good=false;}
            else {threads.push_back({ev.dwThreadId,handle,{}});good=arm(threads.back(),base);
                if(!good)std::printf("{\"error\":\"hardware_context_unavailable_or_busy\",\"code\":%lu}\n",GetLastError());}
        } else if(ev.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT){if(ev.u.LoadDll.hFile)CloseHandle(ev.u.LoadDll.hFile);}
        else if(ev.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT){exited=true;}
        else if(ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT){
            const auto code=ev.u.Exception.ExceptionRecord.ExceptionCode;
            if(code==EXCEPTION_BREAKPOINT && first_break){first_break=false;}
            else if(code==EXCEPTION_SINGLE_STEP){
                Thread* thread=nullptr;for(auto& t:threads)if(t.id==ev.dwThreadId){thread=&t;break;}
                CONTEXT c{};c.ContextFlags=CONTEXT_ALL;
                if(!thread||!GetThreadContext(thread->handle,&c)){good=false;disposition=DBG_EXCEPTION_NOT_HANDLED;}
                else {
                    int index=-1;for(unsigned i=0;i<4;++i)if((c.Dr6&(DWORD64{1}<<i)) && c.Rip==base+rvas[i])index=static_cast<int>(i);
                    if(index<0){good=false;disposition=DBG_EXCEPTION_NOT_HANDLED;}
                    else {
                        const auto i=static_cast<unsigned>(index);++hits[i];
                        if(i>=2||hits[i]<=3||hits[i]%60==0){
                            DWORD64 ret=0;reader.read(c.Rsp,&ret,sizeof(ret));
                            std::printf("{\"kind\":\"%s\",\"ms\":%llu,\"thread\":%lu,\"count\":%u,\"rcx\":\"%llx\",\"rdx\":\"%llx\",\"r8\":\"%llx\",\"r9\":\"%llx\",\"xmm0_low\":\"%llx\",\"xmm1_low\":\"%llx\",\"return_rva\":\"%llx\"}\n",
                              names[i],GetTickCount64()-start,ev.dwThreadId,hits[i],c.Rcx,c.Rdx,c.R8,c.R9,c.Xmm0.Low,c.Xmm1.Low,ret>=base?ret-base:0);
                            std::fflush(stdout);}
                        // Resume flag skips this execution breakpoint once. Only
                        // debug/control fields are written, never argument registers.
                        c.EFlags|=0x10000;c.Dr6=0;c.ContextFlags=CONTEXT_CONTROL|CONTEXT_DEBUG_REGISTERS;
                        good=SetThreadContext(thread->handle,&c)!=FALSE;
                    }
                }
            } else disposition=DBG_EXCEPTION_NOT_HANDLED;
        }
        if(!ContinueDebugEvent(ev.dwProcessId,ev.dwThreadId,disposition))good=false;
        if(exited)break;
    }
    bool restored=true;
    if(!exited)for(auto& t:threads)restored=restore(t)&&restored;
    const bool detached=exited||DebugActiveProcessStop(pid)!=FALSE;
    for(auto& t:threads)CloseHandle(t.handle);
    CloseHandle(game);
    std::printf("{\"status\":\"finished\",\"clean\":%s,\"debug_registers_restored\":%s,\"detached\":%s,\"hits\":[%u,%u,%u,%u]}\n",
        good&&restored&&detached?"true":"false",restored?"true":"false",detached?"true":"false",hits[0],hits[1],hits[2],hits[3]);
    return good&&restored&&detached?0:71;
}
