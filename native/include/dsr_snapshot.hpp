// Original read-only native DSR adapter. See native/README.md for provenance.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace dsr_mw2 {
using Address = std::uint64_t;
// Implementations must return false for inaccessible memory, not fault/zero-fill.
struct Reader {
    virtual bool read(Address address, void* destination, std::size_t size) const = 0;
    virtual ~Reader() = default;
    template<class T> bool get(Address base, std::uint32_t offset, T& value) const {
        if (base < 0x10000 || base > std::numeric_limits<Address>::max() - offset - sizeof(T)) return false;
        return read(base + offset, &value, sizeof(value));
    }
};

constexpr std::uint32_t world_rva = 0x1c77e50;
constexpr std::uint32_t game_data_rva = 0x1c8a530;
constexpr std::uint32_t standard_bolt = 2100000;
constexpr std::int32_t m9_reserve_id = 9000001;
constexpr std::uint32_t goods_category = 0x40000000;
enum class ReadStatus : std::uint32_t { ok, unloaded, unreadable, invalid, changed };

struct Item {
    std::int32_t index = -1;
    std::uint32_t category = 0;
    std::int32_t id = -1;
    std::int32_t quantity = 0;
    std::uint8_t active = 0;
};

struct Snapshot {
    Address player = 0, player_data = 0, equip_data = 0, manipulator = 0;
    std::uint32_t hp = 0, max_hp = 0, active_state = 0, passive_state = 0;
    std::uint32_t left_slot = 0, right_slot = 0, weapon_style = 0;
    std::int32_t left_weapon = -1, right_weapon = -1;
    std::array<std::int32_t, 2> left_weapons{{-1, -1}}, right_weapons{{-1, -1}};
    std::int32_t first_bolt_equipped_id = -1, second_bolt_equipped_id = -1;
    Item first_bolt, second_bolt;
    std::array<std::uint8_t, 0x35> actions{};
};

bool is_m9(std::int32_t weapon_id);
ReadStatus observe(const Reader& memory, Address image_base, Snapshot& output);
// Inventory slots may have vanished after the final native shot. Absence is a
// successful read with id=-1/quantity=0; it is not fabricated ammunition.
ReadStatus inventory_item(const Reader& memory, Address equip_data, std::int32_t index, Item& output);
// Bounded scan of the real native inventory, rejecting duplicate active stacks
// and changes to its backing lists. Does not manufacture absent reserve ammo.
ReadStatus find_inventory_item(const Reader& memory, Address equip_data, std::uint32_t category,
                              std::int32_t id, Item& output);
} // namespace dsr_mw2
