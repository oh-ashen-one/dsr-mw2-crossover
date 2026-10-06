#include "dsr_snapshot.hpp"

namespace dsr_mw2 {
bool is_m9(std::int32_t id) {
    // Standalone bonfire-armory suppressor variant; no invented upgrade range.
    if(id==9100000||id==9200000)return true;
    // Exact native Light Crossbow family records. Reinforcement occupies +0..15.
    // The PARAM audit, not this predicate, decides which upgrade levels exist.
    for (const int root : {1250000, 1250100, 1250200, 1250400, 1250600, 1250800})
        if (id >= root && id <= root + 15) return true;
    return false;
}

ReadStatus inventory_item(const Reader& m, Address equip, std::int32_t index, Item& out) {
    out = {};
    if (index == -1) return ReadStatus::ok;
    if (index < 0 || index >= 8192) return ReadStatus::invalid;
    std::int32_t count{}, boundary{};
    Address list{};
    // EquipInventoryData is inline at EquipGameData+0x120.
    if (!m.get(equip, 0x130, count) || !m.get(equip, 0x140, boundary)) return ReadStatus::unreadable;
    if (count < 0 || count > 8192 || boundary < 0 || boundary > count || index >= count) return ReadStatus::invalid;
    if (!m.get(equip, index < boundary ? 0x150 : 0x158, list) || list < 0x10000) return ReadStatus::unreadable;
    const auto offset = static_cast<std::uint32_t>(index) * 0x1c;
    Item item;
    item.index = index;
    if (!m.get(list, offset, item.category) || !m.get(list, offset + 4, item.id) ||
        !m.get(list, offset + 8, item.quantity) || !m.get(list, offset + 0x10, item.active)) return ReadStatus::unreadable;
    if (item.active > 1) return ReadStatus::invalid;
    if (!item.active) return ReadStatus::ok;
    if (item.quantity < 0 || item.quantity > 999 || (item.category & 0x0fffffff) || item.id < 0) return ReadStatus::invalid;
    out = item;
    return ReadStatus::ok;
}

ReadStatus observe(const Reader& m, Address base, Snapshot& out) {
    out = {};
    Snapshot s;
    Address world{}, global_data{}, global_player{};
    if (!m.get(base, world_rva, world) || !m.get(base, game_data_rva, global_data)) return ReadStatus::unreadable;
    if (!world || !global_data) return ReadStatus::unloaded;
    if (!m.get(world, 0x68, s.player) || !m.get(global_data, 0x10, global_player)) return ReadStatus::unreadable;
    if (!s.player || !global_player) return ReadStatus::unloaded;
    if (!m.get(s.player, 0x578, s.player_data) || !m.get(s.player, 0x70, s.manipulator)) return ReadStatus::unreadable;
    if (s.player_data != global_player || s.player_data < 0x10000 || s.manipulator < 0x10000) return ReadStatus::invalid;
    if (s.player_data > std::numeric_limits<Address>::max() - 0x500) return ReadStatus::invalid;
    s.equip_data = s.player_data + 0x280;
    if (!m.get(s.player, 0x3e8, s.hp) || !m.get(s.player, 0x3ec, s.max_hp) ||
        !m.get(s.equip_data, 0x88, s.weapon_style) ||
        !m.get(s.equip_data, 0x8c, s.left_slot) || !m.get(s.equip_data, 0x90, s.right_slot)) return ReadStatus::unreadable;
    if (s.max_hp > 100000 || s.hp > s.max_hp || s.left_slot > 1 || s.right_slot > 1) return ReadStatus::invalid;
    // Observe inactive slots too: a selected sword cannot establish whether
    // the M9 exists in the other slot. No equip action is sent or inferred.
    for (std::uint32_t slot=0; slot<2; ++slot) {
        if (!m.get(s.equip_data, 0xa4 + 8*slot, s.left_weapons[slot]) ||
            !m.get(s.equip_data, 0xa8 + 8*slot, s.right_weapons[slot])) return ReadStatus::unreadable;
    }
    s.left_weapon=s.left_weapons[s.left_slot];
    s.right_weapon=s.right_weapons[s.right_slot];
    if (!m.get(s.manipulator, 0x1ec, s.active_state) || !m.get(s.manipulator, 0x1f0, s.passive_state) ||
        !m.get(s.manipulator, 0x84, s.actions)) return ReadStatus::unreadable;
    for (auto action : s.actions) if (action > 1) return ReadStatus::invalid;
    for (unsigned slot : {5u, 7u}) {
        std::int32_t index{}, equipped_id{};
        if (!m.get(s.equip_data, 0x24 + 4 * slot, index) || !m.get(s.equip_data, 0xa4 + 4 * slot, equipped_id)) return ReadStatus::unreadable;
        Item& item = slot == 5 ? s.first_bolt : s.second_bolt;
        (slot == 5 ? s.first_bolt_equipped_id : s.second_bolt_equipped_id) = equipped_id;
        auto result = inventory_item(m, s.equip_data, index, item);
        if (result != ReadStatus::ok) return result;
        if (item.id != -1 && (item.category != 0 || item.id != equipped_id)) return ReadStatus::changed;
    }
    // A loaded-character transition may invalidate a whole pointer chain. Do not
    // hand an old character's inventory to the eventual game-thread writer.
    Address check_world{}, check_data{}, check_player{}, check_player_data{};
    if (!m.get(base, world_rva, check_world) || !m.get(base, game_data_rva, check_data) ||
        !m.get(world, 0x68, check_player) || !m.get(global_data, 0x10, check_player_data)) return ReadStatus::unreadable;
    if (world != check_world || global_data != check_data || s.player != check_player || s.player_data != check_player_data) return ReadStatus::changed;
    out = s;
    return ReadStatus::ok;
}

ReadStatus find_inventory_item(const Reader& m, Address equip, std::uint32_t category,
                              std::int32_t id, Item& out) {
    out = {};
    std::int32_t count{}, boundary{};
    Address first{}, second{};
    if (id < 0 || (category & 0x0fffffff)) return ReadStatus::invalid;
    if (!m.get(equip, 0x130, count) || !m.get(equip, 0x140, boundary) ||
        !m.get(equip, 0x150, first) || !m.get(equip, 0x158, second)) return ReadStatus::unreadable;
    if (count < 0 || count > 8192 || boundary < 0 || boundary > count) return ReadStatus::invalid;
    Item found;
    for (std::int32_t index = 0; index < count; ++index) {
        Item item;
        auto status = inventory_item(m, equip, index, item);
        if (status != ReadStatus::ok) return status;
        if (item.active && item.category == category && item.id == id) {
            if (found.active) return ReadStatus::invalid;
            found = item;
        }
    }
    std::int32_t count2{}, boundary2{};
    Address first2{}, second2{};
    if (!m.get(equip, 0x130, count2) || !m.get(equip, 0x140, boundary2) ||
        !m.get(equip, 0x150, first2) || !m.get(equip, 0x158, second2)) return ReadStatus::unreadable;
    if (count != count2 || boundary != boundary2 || first != first2 || second != second2) return ReadStatus::changed;
    out = found;
    return ReadStatus::ok;
}
} // namespace dsr_mw2
