// Original external observer: private DSR only, no writes/injection/input.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <bcrypt.h>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include "dsr_snapshot.hpp"

namespace {
bool pinned_image(const wchar_t* path) {
    if (_wcsicmp(path,L"C:\\Games\\DSR-MW2\\DarkSoulsRemastered.exe") &&
        _wcsicmp(path,L"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DARK SOULS REMASTERED\\DarkSoulsRemastered.exe")) return false;
    HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(f==INVALID_HANDLE_VALUE)return false;
    BCRYPT_ALG_HANDLE alg=nullptr;BCRYPT_HASH_HANDLE h=nullptr;
    bool ok=BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0;
    if(ok)ok=BCryptCreateHash(alg,&h,nullptr,0,nullptr,0,0)>=0;
    std::array<UCHAR,65536> buffer{};DWORD n=0;
    while(ok){if(!ReadFile(f,buffer.data(),static_cast<DWORD>(buffer.size()),&n,nullptr)){ok=false;break;}
        if(!n)break;
        ok=BCryptHashData(h,buffer.data(),n,0)>=0;}
    std::array<UCHAR,32> hash{};
    if(ok)ok=BCryptFinishHash(h,hash.data(),static_cast<ULONG>(hash.size()),0)>=0;
    const std::array<UCHAR,32> expected{0xa4,0x5a,0xaa,0x36,0xdd,0x2f,0x6c,0xc1,0x51,0x67,0x0a,0x63,0x9e,0xa5,0x54,0x70,
        0x43,0xcf,0x38,0xea,0x79,0xff,0x41,0x78,0xb9,0x63,0xc6,0xed,0x71,0xf9,0x8d,0x7b};
    if(h)BCryptDestroyHash(h);
    if(alg)BCryptCloseAlgorithmProvider(alg,0);
    CloseHandle(f);
    return ok&&hash==expected;
}
struct RemoteReader final:dsr_mw2::Reader {
    HANDLE process;
    explicit RemoteReader(HANDLE p):process(p){}
    bool read(dsr_mw2::Address at,void* out,std::size_t size)const override{
        SIZE_T n=0;return ReadProcessMemory(process,reinterpret_cast<const void*>(at),out,size,&n)&&n==size;
    }
};
}

int main(int argc,char** argv){
    if(argc!=2)return 64;
    char* end=nullptr;long seconds=std::strtol(argv[1],&end,10);
    if(!end||*end||seconds<1||seconds>120)return 64;
    SetPriorityClass(GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS);
    HANDLE list=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(list==INVALID_HANDLE_VALUE)return 65;
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);DWORD pid=0;unsigned count=0;
    for(BOOL ok=Process32FirstW(list,&entry);ok;ok=Process32NextW(list,&entry)){
        if(!_wcsicmp(entry.szExeFile,L"DarkSoulsRemastered.exe")){pid=entry.th32ProcessID;++count;}}
    CloseHandle(list);if(count!=1){std::printf("{\"error\":\"expected_one_private_game\",\"count\":%u}\n",count);return 66;}
    HANDLE game=OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION|SYNCHRONIZE,FALSE,pid);
    if(!game){std::printf("{\"error\":\"readonly_open_failed\",\"code\":%lu}\n",GetLastError());return 67;}
    wchar_t path[1024]{};DWORD length=1024;
    if(!QueryFullProcessImageNameW(game,0,path,&length)||!pinned_image(path)){CloseHandle(game);return 68;}
    HANDLE modules=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
    MODULEENTRY32W module{};module.dwSize=sizeof(module);dsr_mw2::Address base=0;
    if(modules!=INVALID_HANDLE_VALUE){
        for(BOOL ok=Module32FirstW(modules,&module);ok;ok=Module32NextW(modules,&module))
            if(!_wcsicmp(module.szModule,L"DarkSoulsRemastered.exe"))base=reinterpret_cast<dsr_mw2::Address>(module.modBaseAddr);
        CloseHandle(modules);}
    RemoteReader reader(game);std::array<unsigned char,7> got{};
    const std::array<unsigned char,7> world{0x48,0x8b,0x05,0x23,0x38,0x4b,0x01};
    if(!base||!reader.get(base,0x7c4626,got)||got!=world){CloseHandle(game);return 69;}
    const ULONGLONG start=GetTickCount64();
    ULONGLONG capture_start=0;
    std::printf("{\"schema\":3,\"verified_private_image\":true,\"windows_pid\":%lu,\"read_only\":true,\"max_wait_ms\":300000,\"capture_ms\":%ld}\n",pid,seconds*1000);std::fflush(stdout);
    while(WaitForSingleObject(game,0)==WAIT_TIMEOUT){
        const ULONGLONG now=GetTickCount64();
        if((!capture_start&&now-start>=300000)||
           (capture_start&&now-capture_start>=static_cast<ULONGLONG>(seconds)*1000))break;
        dsr_mw2::Snapshot s;auto result=dsr_mw2::observe(reader,base,s);
        // Menus/loading are not a character session. Wait read-only, with a
        // strict deadline; do not consume the capture window at the title.
        if(!capture_start){
            if(result!=dsr_mw2::ReadStatus::ok||s.max_hp==0){Sleep(100);continue;}
            capture_start=now;
            std::printf("{\"status\":\"loaded_character_observed\",\"ms\":%llu}\n",now-start);
        }
        std::uint64_t actions=0;for(std::size_t i=0;i<s.actions.size();++i)if(s.actions[i])actions|=std::uint64_t{1}<<i;
        std::printf("{\"ms\":%llu,\"status\":%u,\"hp\":%u,\"max_hp\":%u,\"right_weapon\":%d,\"left_weapon\":%d,\"right_slot\":%u,\"right_weapons\":[%d,%d],\"left_weapons\":[%d,%d],\"bolt_id\":%d,\"bolts\":%d,\"active_state\":%u,\"passive_state\":%u,\"actions\":%llu}\n",
            GetTickCount64()-start,static_cast<unsigned>(result),s.hp,s.max_hp,s.right_weapon,s.left_weapon,s.right_slot,
            s.right_weapons[0],s.right_weapons[1],s.left_weapons[0],s.left_weapons[1],
            s.first_bolt.id,s.first_bolt.quantity,s.active_state,s.passive_state,static_cast<unsigned long long>(actions));
        std::fflush(stdout);Sleep(16);
    }
    std::printf("{\"status\":\"observer_finished\",\"character_observed\":%s}\n",capture_start?"true":"false");
    CloseHandle(game);return 0;
}
