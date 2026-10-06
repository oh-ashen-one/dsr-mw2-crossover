#pragma once
#include "dsr_snapshot.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>
using namespace dsr_mw2;

struct Fixture : Reader {
    struct Region { Address at; std::vector<std::uint8_t> data; };
    std::vector<Region> regions;
    static constexpr Address image = 0x140000000, world = 0x200000000, global = 0x200001000;
    static constexpr Address player = 0x200002000, data = 0x200003000, pad = 0x200004000;
    static constexpr Address list_one = 0x200005000, list_two = 0x200006000, equip = data + 0x280;
    mutable int root_reads = 0;
    bool change_root = false;
    Fixture() {
        for (Address at : {image + world_rva, image + game_data_rva, world, global, player, data, pad, list_one, list_two})
            regions.push_back({at, std::vector<std::uint8_t>(at > image && at < world ? 8 : 4096)});
        put(image + world_rva, world); put(image + game_data_rva, global);
        put(world + 0x68, player); put(global + 0x10, data);
        put(player + 0x578, data); put(player + 0x70, pad);
        put(player + 0x3e8, std::uint32_t(500)); put(player + 0x3ec, std::uint32_t(600));
        put(equip + 0x8c, std::uint32_t(0)); put(equip + 0x90, std::uint32_t(1));
        put(equip + 0xa4, std::int32_t(1500000)); put(equip + 0xb0, std::int32_t(1250000));
        put(equip + 0x130, std::int32_t(4)); put(equip + 0x140, std::int32_t(2));
        put(equip + 0x150, list_one); put(equip + 0x158, list_two);
        put(equip + 0x38, std::int32_t(1)); put(equip + 0xb8, std::int32_t(2100000));
        put(equip + 0x40, std::int32_t(3)); put(equip + 0xc0, std::int32_t(2101000));
        item(list_one + 0x1c, 2100000, 15);
        item(list_two + 3 * 0x1c, 2101000, 84);
    }
    template<class T> void put(Address at, T value) {
        for (auto& r : regions) if (at >= r.at && at - r.at + sizeof(T) <= r.data.size()) {
            std::memcpy(r.data.data() + (at-r.at), &value, sizeof(T)); return;
        }
        assert(false);
    }
    void item(Address at, std::int32_t id, std::int32_t quantity) {
        put(at, std::uint32_t(0)); put(at+4, id); put(at+8, quantity); put(at+0x10, std::uint8_t(1));
    }
    bool read(Address at, void* out, std::size_t size) const override {
        if (at == image + world_rva && ++root_reads > 1 && change_root) { Address changed = world+8; std::memcpy(out, &changed, size); return true; }
        for (const auto& r : regions) if (at >= r.at && at-r.at <= r.data.size() && size <= r.data.size()-(at-r.at)) {
            std::memcpy(out, r.data.data()+(at-r.at), size); return true;
        }
        return false;
    }
};
