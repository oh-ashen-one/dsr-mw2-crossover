#include "memory_fixture.hpp"

int main() {
    unsigned checks = 0;
    auto check = [&](bool ok) { assert(ok); ++checks; };
    Snapshot s;
    Fixture m;
    check(observe(m, m.image, s) == ReadStatus::ok);
    check(s.right_weapon == 1250000 && is_m9(s.right_weapon) && !is_m9(s.left_weapon));
    check(s.first_bolt.id == 2100000 && s.first_bolt.quantity == 15);
    check(s.second_bolt.index == 3 && s.second_bolt.quantity == 84);
    check(s.hp == 500 && s.max_hp == 600);
    check(!is_m9(-1) && !is_m9(1250016) && is_m9(1250605));
    Fixture inactive;
    inactive.put(inactive.equip+0xa8,std::int32_t(212000));
    inactive.put(inactive.equip+0x90,std::uint32_t(0));
    check(observe(inactive,inactive.image,s)==ReadStatus::ok && s.right_weapon==212000
          && s.right_weapons[1]==1250000 && !is_m9(s.right_weapon));
    inactive.put(inactive.equip+0x90,std::uint32_t(1));
    check(observe(inactive,inactive.image,s)==ReadStatus::ok && s.right_weapon==1250000
          && s.right_weapons[0]==212000);
    m.put(m.list_one + 0x1c + 8, std::int32_t(0));
    check(observe(m, m.image, s) == ReadStatus::ok && s.first_bolt.quantity == 0);
    m.put(m.list_one + 0x1c + 0x10, std::uint8_t(0));
    m.put(m.list_one + 0x1c + 8, std::int32_t(-1));
    check(observe(m, m.image, s) == ReadStatus::ok && s.first_bolt.id == -1);
    m.put(m.equip + 0x38, std::int32_t(-1));
    check(observe(m, m.image, s) == ReadStatus::ok && s.first_bolt.index == -1);
    m.put(m.equip + 0x38, std::int32_t(8192));
    check(observe(m, m.image, s) == ReadStatus::invalid && s.player == 0);
    Fixture mismatch; mismatch.put(mismatch.equip+0xb8, std::int32_t(2103000));
    check(observe(mismatch, m.image, s) == ReadStatus::changed);
    Fixture character; character.put(character.global+0x10, character.data+8);
    check(observe(character, m.image, s) == ReadStatus::invalid);
    Fixture changed; changed.change_root = true;
    check(observe(changed, m.image, s) == ReadStatus::changed && s.player == 0);
    Fixture unloaded; unloaded.put(unloaded.world+0x68, Address(0));
    check(observe(unloaded, m.image, s) == ReadStatus::unloaded);
    Fixture bad_input; bad_input.put(bad_input.pad+0x84, std::uint8_t(7));
    check(observe(bad_input, m.image, s) == ReadStatus::invalid);
    Fixture inaccessible; inaccessible.put(inaccessible.equip+0x150, Address(0x300000000));
    check(observe(inaccessible, m.image, s) == ReadStatus::unreadable);
    Fixture overflow; overflow.put(overflow.equip+0x150, std::numeric_limits<Address>::max()-4);
    check(observe(overflow, m.image, s) == ReadStatus::unreadable);
    std::cout << checks << " native adapter fixture checks passed; no game was attached\n";
}
