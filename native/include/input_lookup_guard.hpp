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
inline std::array<unsigned char,77> input_lookup_code(std::uintptr_t resume,std::uintptr_t empty){
    std::array<unsigned char,77> code{};
    const unsigned char checks[]={
        0x9c, // pushfq; stack offsets below account for this eight-byte push
        0x48,0x83,0x7c,0x24,0x70,0,0x75,34,
        0x48,0x83,0x7c,0x24,0x78,0,0x75,26,
        0x48,0x83,0xbc,0x24,0x80,0,0,0,0,0x75,15,
        0x9d,0xff,0x25,0,0,0,0};
    static_assert(sizeof(checks)==35);
    std::memcpy(code.data(),checks,sizeof(checks));
    std::memcpy(code.data()+35,&empty,8);
    code[43]=0x9d;
    std::memcpy(code.data()+44,input_lookup_prefix.data(),input_lookup_prefix.size());
    code[63]=0xff;code[64]=0x25;
    std::memcpy(code.data()+69,&resume,8);
    return code;
}
bool install_input_lookup_guard(std::uintptr_t base);
}
