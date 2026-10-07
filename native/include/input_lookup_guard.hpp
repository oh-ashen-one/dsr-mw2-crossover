// Original guard for the exact native empty-vector dereference at RVA54c4c9.
// Preserve flags/registers and the original path for every nonempty result.
#pragma once
#include <array>
#include <cstdint>
#include <cstring>
namespace dsr_mw2 {
constexpr std::array<unsigned char,19> input_lookup_prefix={
    0x48,0x8b,0x5c,0x24,0x68,0x4c,0x8b,0x0b,0x49,0x8b,0x49,0x68,
    0x4d,0x63,0x04,0x07,0x49,0x8b,0xc0};
// Only the all-null path also increments `counter` (lock inc) so owner logs can
// show when the native binding lookup was empty instead of crashing.
inline std::array<unsigned char,93> input_lookup_code(std::uintptr_t resume,std::uintptr_t empty,std::uintptr_t counter){
    std::array<unsigned char,93> code{};
    const unsigned char checks[]={
        0x9c, // pushfq; stack offsets below account for this eight-byte push
        0x48,0x83,0x7c,0x24,0x70,0,0x75,50,
        0x48,0x83,0x7c,0x24,0x78,0,0x75,42,
        0x48,0x83,0xbc,0x24,0x80,0,0,0,0,0x75,31,
        0x50,0x48,0xb8};                        // push rax; mov rax,imm64
    static_assert(sizeof(checks)==31);
    std::memcpy(code.data(),checks,sizeof(checks));
    std::memcpy(code.data()+31,&counter,8);
    const unsigned char count[]={0xf0,0x48,0xff,0x00,0x58,0x9d,0xff,0x25,0,0,0,0}; // lock inc [rax]; pop rax; popfq; jmp [rip]
    std::memcpy(code.data()+39,count,sizeof(count));
    std::memcpy(code.data()+51,&empty,8);
    code[59]=0x9d;
    std::memcpy(code.data()+60,input_lookup_prefix.data(),input_lookup_prefix.size());
    code[79]=0xff;code[80]=0x25;
    std::memcpy(code.data()+85,&resume,8);
    return code;
}
std::uint64_t input_lookup_guard_hits();
bool install_input_lookup_guard(std::uintptr_t base);
}
