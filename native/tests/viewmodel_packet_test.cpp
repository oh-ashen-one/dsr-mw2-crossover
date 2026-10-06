// Runs natively on macOS: malformed packets and interpolation, no game/GPU.
#include "viewmodel_packet.hpp"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <limits>
#include <vector>
int main(int argc,char** argv){
    if(argc!=2)return 1;
    std::ifstream stream(argv[1],std::ios::binary);
    std::vector<unsigned char> bytes{std::istreambuf_iterator<char>(stream),{}};
    dsr_mw2::VmPacket packet;if(!packet.parse(bytes))return 2;
    unsigned checks=1;std::array<dsr_mw2::VmMatrix,90> pose{};
    for(unsigned c=0;c<packet.clips.size();++c){
        const auto& clip=packet.clips[c];
        for(unsigned f=0;f<clip.frames;++f)for(float ads:{0.f,.5f,1.f}){
            if(!packet.pose(c,static_cast<float>(f)/60.f,ads,pose))return 3;
            for(const auto& m:pose)for(float x:m)if(!std::isfinite(x))return 4;
            ++checks;
        }
    }
    if(packet.pose(static_cast<unsigned>(packet.clips.size()),0,0,pose)||packet.pose(0,-1,0,pose)||packet.pose(0,0,2,pose)||
       packet.pose(0,0,std::numeric_limits<float>::quiet_NaN(),pose))return 5;
    checks+=4;
    // Check truncations at every metadata/vertex field boundary and the tail.
    for(std::size_t size:{0u,7u,8u,12u,31u,32u,33u,64u,1000u}){
        dsr_mw2::VmPacket invalid;auto copy=bytes;copy.resize(size);if(invalid.parse(copy))return 6;++checks;
    }
    for(std::size_t offset:{8u,12u,16u,20u,24u,28u,32u,64u}){
        auto bad=bytes;std::memset(bad.data()+offset,255,4);dsr_mw2::VmPacket invalid;
        if(invalid.parse(bad))return 7;
        ++checks;
    }
    auto bad=bytes;bad.pop_back();dsr_mw2::VmPacket invalid;if(invalid.parse(bad))return 8;++checks;
    bad=bytes;bad.push_back(0);if(invalid.parse(bad))return 9;++checks;
    std::printf("{\"checks\":%u,\"bones\":%u,\"vertices\":%zu,\"runtime_verified\":false}\n",checks,packet.bones,packet.vertices.size());
}
