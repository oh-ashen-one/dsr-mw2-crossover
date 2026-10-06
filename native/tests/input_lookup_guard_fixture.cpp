#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include "input_lookup_guard.hpp"
extern "C" std::uint64_t guard_fixture(void*,std::uintptr_t,std::uintptr_t,std::uintptr_t);
extern "C" void guard_fixture_empty();
extern "C" void guard_fixture_resume();
int main(){
    void* page=VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!page)return 1;
    const auto code=dsr_mw2::input_lookup_code(reinterpret_cast<std::uintptr_t>(&guard_fixture_resume),reinterpret_cast<std::uintptr_t>(&guard_fixture_empty));
    std::memcpy(page,code.data(),code.size());DWORD old=0;
    if(!VirtualProtect(page,4096,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),page,code.size()))return 2;
    std::array<std::uintptr_t,16> object{};object[13]=1234;
    std::uintptr_t binding=reinterpret_cast<std::uintptr_t>(object.data());
    auto begin=reinterpret_cast<std::uintptr_t>(&binding);
    const auto empty=guard_fixture(page,0,0,0);
    const auto valid=guard_fixture(page,begin,begin+8,begin+8);
    const auto reserved=guard_fixture(page,begin,begin,begin+8);
    // Empty result takes native completion; valid and reserved vectors retain
    // all original instructions. Carry flag survives both control-flow paths.
    const bool okay=empty==0x100000001ULL&&valid==0x100000002ULL&&reserved==0x100000002ULL;
    std::printf("{\"empty_completed\":%s,\"valid_preserved\":%s,\"reserved_preserved\":%s,\"flags_preserved\":%s}\n",
        (empty&0xffffffff)==1?"true":"false",(valid&0xffffffff)==2?"true":"false",
        (reserved&0xffffffff)==2?"true":"false",okay?"true":"false");
    VirtualFree(page,0,MEM_RELEASE);return okay?0:3;
}
