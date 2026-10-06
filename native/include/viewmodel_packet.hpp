#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include "packet_buffer.hpp"

namespace dsr_mw2 {
struct VmVertex {float position[3],normal[3],uv[2];std::uint16_t bones[4];float weights[4];};
static_assert(sizeof(VmVertex)==56);
struct VmDraw {std::uint32_t first,count,texture,suppressor;};
struct VmTexture {std::uint32_t width=0,height=0;PacketBuffer<unsigned char> rgba;};
using VmMatrix=std::array<float,12>;
struct VmClip {unsigned frames=0;float duration=0;PacketBuffer<VmMatrix> poses;};
struct VmPacket {
    unsigned bones=0;PacketBuffer<VmVertex> vertices;PacketBuffer<VmDraw> draws;
    PacketBuffer<VmTexture> textures;PacketBuffer<VmClip> clips;
    template<class Buffer>bool parse(const Buffer& bytes){
        *this={};
        if(bytes.size()<32||bytes.size()>32*1024*1024||std::memcmp(bytes.data(),"DSRVM001",8))return false;
        std::size_t at=8;
        auto take=[&](void* destination,std::size_t size){
            if(size>bytes.size()-at)return false;
            std::memcpy(destination,bytes.data()+at,size);at+=size;return true;
        };
        std::array<unsigned,6> header{};
        if(!take(header.data(),sizeof(header))||header[0]!=1||header[1]!=76||!header[2]||header[2]>60000||header[2]%3||
           !header[3]||header[3]>16||!header[4]||header[4]>8||header[5]!=7)return false;
        bones=header[1];if(!vertices.resize(header[2])||!draws.resize(header[3])||!textures.resize(header[4])||!clips.resize(header[5]))return false;
        if(!take(vertices.data(),vertices.size()*sizeof(VmVertex))||!take(draws.data(),draws.size()*sizeof(VmDraw)))return false;
        for(const auto& v:vertices){
            float sum=0;
            for(float x:v.position)if(!std::isfinite(x)||std::fabs(x)>256)return false;
            for(float x:v.normal)if(!std::isfinite(x)||std::fabs(x)>1.1f)return false;
            for(float x:v.uv)if(!std::isfinite(x)||std::fabs(x)>32)return false;
            for(unsigned i=0;i<4;++i){if(v.bones[i]>=bones||!std::isfinite(v.weights[i])||v.weights[i]<0||v.weights[i]>1)return false;sum+=v.weights[i];}
            if(std::fabs(sum-1.f)>.0001f)return false;
        }
        unsigned next=0;
        for(const auto& d:draws){
            if(d.first!=next||d.count%3||!d.count||d.count>vertices.size()-next||d.texture>=textures.size()||d.suppressor>1)return false;
            next+=d.count;
        }
        if(next!=vertices.size())return false;
        for(auto& t:textures){
            if(!take(&t.width,4)||!take(&t.height,4)||!t.width||!t.height||t.width>2048||t.height>2048||
               (t.width&(t.width-1))||(t.height&(t.height-1)))return false;
            const std::size_t size=std::size_t(t.width)*t.height*4;
            if(size>bytes.size()-at)return false;
            if(!t.rgba.resize(size)||!take(t.rgba.data(),size))return false;
        }
        for(auto& c:clips){
            if(!take(&c.frames,4)||!take(&c.duration,4)||!c.frames||c.frames>301||!std::isfinite(c.duration)||c.duration<0||c.duration>5||
               std::fabs(static_cast<float>(c.frames-1)-std::ceil(c.duration*60.f))>1.f)return false;
            const std::size_t count=std::size_t(c.frames)*2*bones,size=count*sizeof(VmMatrix);
            if(size>bytes.size()-at)return false;
            if(!c.poses.resize(count)||!take(c.poses.data(),size))return false;
            for(const auto& m:c.poses)for(float x:m)if(!std::isfinite(x)||std::fabs(x)>512)return false;
        }
        return at==bytes.size();
    }
    bool pose(unsigned clip,float seconds,float ads,std::array<VmMatrix,76>& out)const{
        if(bones!=76||clip>=clips.size()||!std::isfinite(seconds)||!std::isfinite(ads)||seconds<0||ads<0||ads>1)return false;
        const auto& c=clips[clip];if(!c.frames||c.poses.size()!=std::size_t(c.frames)*2*bones)return false;
        const float t=std::min(seconds*60.f,static_cast<float>(c.frames-1));
        const auto a=static_cast<unsigned>(t),b=std::min(a+1,c.frames-1);const float f=t-static_cast<float>(a);
        for(unsigned j=0;j<bones;++j)for(unsigned k=0;k<12;++k){
            auto sample=[&](unsigned mode){const float x=c.poses[(a*2+mode)*bones+j][k];return x+(c.poses[(b*2+mode)*bones+j][k]-x)*f;};
            const float hip=sample(0);out[j][k]=hip+(sample(1)-hip)*ads;
        }
        return true;
    }
};
}
