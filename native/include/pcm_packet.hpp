// Original bounded reader for the checked OAT PCM container, no decoder.
#pragma once
#include <cstdint>
#include <cstring>
#include <cstddef>
namespace dsr_mw2 {
struct PcmInfo {std::uint16_t channels=0;std::uint32_t bytes=0;};
inline bool pcm_info(const unsigned char* data,std::size_t size,PcmInfo& out){
    out={};if(size<44||size>8*1024*1024)return false;
    auto u16=[&](unsigned at){std::uint16_t v=0;std::memcpy(&v,data+at,2);return v;};
    auto u32=[&](unsigned at){std::uint32_t v=0;std::memcpy(&v,data+at,4);return v;};
    const auto channels=u16(22),block=u16(32);const auto bytes=u32(40);
    if(std::memcmp(data,"RIFF",4)||std::memcmp(data+8,"WAVEfmt ",8)||std::memcmp(data+36,"data",4)||
       u32(4)!=size-8||u32(16)!=16||u16(20)!=1||(channels!=1&&channels!=2)||
       u32(24)!=44100||block!=channels*2||u32(28)!=44100u*block||u16(34)!=16||
       !bytes||bytes!=size-44||bytes%block)return false;
    out={channels,bytes};return true;
}
}
