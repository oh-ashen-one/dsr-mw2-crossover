// Original bounded native precision-aim trial. No camera/inventory/HP writer.
// Interface facts: pinned DSR gyro source d451f3f and independently inspected
// exact retail SetAim leaf at325e80. It changes only player+2a6 bit4 after the
// native context gate. All73 bytes must match before any call.
#pragma once
#include "dsr_snapshot.hpp"
#include "m9_aim_latch.hpp"
#include <array>
#include <cmath>
#include <cstring>

namespace dsr_mw2 {
class M9NativeAim {
public:
    bool owned=false,fault=false;Address player=0,camera=0;
    unsigned char before=0,after=0,camera_active=0;
    float pitch=0,yaw=0,zoom=0;
    bool camera_read=false;
    bool step(const Reader& reader,Address base,const Snapshot& s,bool allowed,bool held,bool native_request,bool resumable=false){
        if(s.player!=player){owned=false;latch.reset();player=s.player;hp=s.hp;}
        if(s.hp<hp){allowed=false;resumable=false;}
        hp=s.hp;
        Address menu=0,control=0,context=0;float menu_time=0;std::uint32_t context_flags=0;
        const bool safe=s.player&&reader.get(s.player,0x2a6,before)&&
            reader.get(s.player,0x68,control)&&reader.get(control,0x48,context)&&
            reader.get(context,0xa4,context_flags);
        const bool ui=reader.get(base,0x1c7b648,menu)&&
            (!menu||(reader.get(menu,0xc2c,menu_time)&&std::isfinite(menu_time)&&menu_time<=0));
        const bool desired=latch.desired(safe&&ui&&!fault&&!(context_flags&0x08000000),
            allowed,held,native_request,owned,resumable,bool(before&0x10));
        bool changed=false;
        if(safe&&(desired||owned)){
            if(desired!=owned||bool(before&0x10)!=desired){
                if(!set(reader,base,s.player,desired)){fault=true;}
                else {owned=desired;changed=true;}
            }
        }
        after=before;reader.get(s.player,0x2a6,after);
        if(changed&&((after^before)&0xef))fault=true;
        if(changed&&bool(after&0x10)!=desired){fault=true;owned=false;}
        read_camera(reader,base);
        return changed;
    }
    void stop(const Reader& reader,Address base,const Snapshot& s){
        if(owned&&s.player==player)set(reader,base,player,false);
        owned=false;latch.reset();
    }
private:
    M9AimLatch latch;unsigned hp=0;
    static bool set(const Reader& reader,Address base,Address actor,bool active){
        constexpr unsigned char signature[]={
            0x44,0x0f,0xb6,0xc2,0x84,0xd2,0x74,0x2a,0x48,0x8b,0x41,0x68,0x48,0x85,0xc0,0x74,
            0x21,0x48,0x8b,0x50,0x48,0x48,0x85,0xd2,0x74,0x18,0x8b,0x82,0xa4,0x00,0x00,0x00,
            0xc1,0xe8,0x1b,0xa8,0x01,0x45,0x0f,0xb6,0xc0,0xb8,0x00,0x00,0x00,0x00,0x44,0x0f,
            0x45,0xc0,0x80,0xa1,0xa6,0x02,0x00,0x00,0xef,0x41,0x80,0xe0,0x01,0x41,0xc0,0xe0,
            0x04,0x44,0x08,0x81,0xa6,0x02,0x00,0x00,0xc3};
        std::array<unsigned char,sizeof(signature)> bytes{};
        if(!actor||!reader.read(base+0x325e80,bytes.data(),bytes.size())||std::memcmp(bytes.data(),signature,bytes.size()))return false;
        using Fn=void(*)(Address,bool);Fn native=nullptr;auto address=base+0x325e80;
        static_assert(sizeof(native)==sizeof(address));std::memcpy(&native,&address,sizeof(native));
        native(actor,active);return true;
    }
    void read_camera(const Reader& reader,Address base){
        Address bullet=0,chr=0,vtable=0;camera=0;
        camera_read=reader.get(base,0x1c7a488,bullet)&&reader.get(bullet,0x60,chr)&&
            reader.get(chr,0x68,camera)&&reader.get(camera,0,vtable)&&vtable==base+0x12ee118&&
            reader.get(camera,0x18c,camera_active)&&reader.get(camera,0x14c,pitch)&&
            reader.get(camera,0x150,yaw)&&reader.get(camera,0x13c,zoom)&&
            std::isfinite(pitch)&&std::isfinite(yaw)&&std::isfinite(zoom);
        if(!camera_read){pitch=yaw=zoom=0;camera_active=0;}
    }
};
}
