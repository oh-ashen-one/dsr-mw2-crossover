#pragma once
#include <cstdlib>
#include <cstddef>
#include <new>
#include <utility>

namespace dsr_mw2 {
// Fixed-size, non-throwing storage for a bounded file section. Allocations only
// occur during packet load, never while submitting frames. No exception runtime
// or threading support is pulled into the native XInput forwarding module.
template<class T> class PacketBuffer {
    T* memory=nullptr;std::size_t count=0;
public:
    PacketBuffer()=default;
    PacketBuffer(const PacketBuffer&)=delete;
    PacketBuffer& operator=(const PacketBuffer&)=delete;
    PacketBuffer(PacketBuffer&& other)noexcept:memory(other.memory),count(other.count){other.memory=nullptr;other.count=0;}
    PacketBuffer& operator=(PacketBuffer&& other)noexcept{
        if(this!=&other){clear();memory=other.memory;count=other.count;other.memory=nullptr;other.count=0;}return *this;
    }
    ~PacketBuffer(){clear();}
    void clear(){for(std::size_t i=0;i<count;++i)memory[i].~T();std::free(memory);memory=nullptr;count=0;}
    bool resize(std::size_t n){
        if(n>32*1024*1024/sizeof(T))return false;
        auto* fresh=static_cast<T*>(std::malloc(n*sizeof(T)));
        if(n&&!fresh)return false;
        clear();memory=fresh;count=n;for(std::size_t i=0;i<n;++i)new(memory+i)T{};return true;
    }
    std::size_t size()const{return count;}
    T* data(){return memory;}const T* data()const{return memory;}
    T* begin(){return memory;}const T* begin()const{return memory;}
    T* end(){return count?memory+count:memory;}const T* end()const{return count?memory+count:memory;}
    T& operator[](std::size_t i){return memory[i];}const T& operator[](std::size_t i)const{return memory[i];}
};
}
