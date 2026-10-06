#include "memory_fixture.hpp"
#include "m9_handling.hpp"
#include <cmath>

struct Port : InventoryPort {
    Fixture memory;
    unsigned transfers = 0;
    TransferStatus simulate = TransferStatus::committed;
    bool partial_write = false;
    Port() {
        memory.item(Fixture::list_two + 2 * 0x1c, m9_reserve_id, 84);
        memory.put(Fixture::list_two + 2 * 0x1c, goods_category);
    }
    ReadStatus read(InventoryView& out) override { return observe_inventory(memory, Fixture::image, out); }
    void magazine(int rounds) {
        memory.item(Fixture::list_one + 0x1c, static_cast<std::int32_t>(standard_bolt), rounds);
        memory.put(Fixture::equip + 0x38, std::int32_t(1));
        memory.put(Fixture::equip + 0xb8, static_cast<std::int32_t>(standard_bolt));
    }
    void reserve(int rounds) { memory.put(Fixture::list_two + 2 * 0x1c + 8, std::int32_t(rounds)); }
    void consume() {
        InventoryView view;
        assert(read(view) == ReadStatus::ok && view.native.first_bolt.quantity > 0);
        magazine(view.native.first_bolt.quantity - 1);
        if (view.native.first_bolt.quantity == 1) {
            memory.put(Fixture::list_one + 0x1c + 0x10, std::uint8_t(0));
            memory.put(Fixture::equip + 0x38, std::int32_t(-1));
        }
    }
    TransferStatus transfer(const Transfer& t) override {
        ++transfers;
        InventoryView current;
        if (read(current) != ReadStatus::ok || !same_inventory(current, t.expected)) return TransferStatus::stale;
        assert(t.rounds > 0 && t.rounds <= current.reserve.quantity);
        assert(current.native.first_bolt.quantity + t.rounds <= m9_capacity);
        assert(t.recreate_first_bolt == (current.native.first_bolt.id == -1));
        if (simulate != TransferStatus::committed) return simulate;
        magazine(current.native.first_bolt.quantity + t.rounds);
        if (!partial_write) reserve(current.reserve.quantity - t.rounds);
        return TransferStatus::committed;
    }
};
// Test-only native API: all mutation goes into the same bounded byte-array
// fixture read by the production snapshot reader. No live process is involved.
struct Api : NativeInventoryApi {
    Port& port;
    bool granted = true, active = false, fail_forever = false, interleave_damage = false;
    unsigned calls = 0, fail_on = 0, ends = 0;
    explicit Api(Port& p) : port(p) {}
    bool begin(const InventoryView& expected) override {
        if (!granted || active || expected.native.player != Fixture::player) return false;
        active = true; return true;
    }
    void end() override { assert(active); active = false; ++ends; }
    bool fails() { assert(active); ++calls; return fail_on && (calls == fail_on || (fail_forever && calls >= fail_on)); }
    bool set_count(std::uint32_t category, std::int32_t id, std::int32_t quantity) override {
        if (fails()) return false;
        if (interleave_damage && calls == 1) port.memory.put(Fixture::player + 0x3e8, std::uint32_t(499));
        if (category == goods_category && id == m9_reserve_id) {
            port.memory.item(Fixture::list_two + 2 * 0x1c, id, quantity);
            port.memory.put(Fixture::list_two + 2 * 0x1c, goods_category);
            if (!quantity) port.memory.put(Fixture::list_two + 2 * 0x1c + 0x10, std::uint8_t(0));
        } else {
            assert(category == 0 && id == static_cast<std::int32_t>(standard_bolt));
            port.magazine(quantity);
            if (!quantity) {
                port.memory.put(Fixture::list_one + 0x1c + 0x10, std::uint8_t(0));
                port.memory.put(Fixture::equip + 0x38, std::int32_t(-1));
                port.memory.put(Fixture::equip + 0xb8, std::int32_t(-1));
            }
        }
        return true;
    }
    bool equip_first_bolt(std::int32_t id) override {
        if (fails()) return false;
        port.memory.put(Fixture::equip + 0xb8, id);
        port.memory.put(Fixture::equip + 0x38, std::int32_t(id == -1 ? -1 : 1));
        return true;
    }
};
struct Harness {
    Port port;
    M9Controller controller;
    Capabilities caps{true, true, true, true, true, true};
    Frame f;
    Output o;
    bool simulate_native_reload = true;
    double native_reload_duration = 0;
    Harness() { f.focused = f.gameplay = f.magazine_data = f.weapon_action_ready = true; f.load_epoch = 1; tick(0); }
    Output tick(double dt) {
        f.now += dt;
        // Explicit test-only action callback simulation, never production code.
        if (simulate_native_reload) {
            if (o.reload_requested) {
                native_reload_duration = o.magazine ? m9_reload_tactical : m9_reload_empty;
                f.reload_action = {f.reload_action.sequence + 1, Fixture::player, 1250000, 0, ReloadState::playing};
            } else if (f.reload_action.state == ReloadState::playing) {
                f.reload_action.elapsed += dt;
                if (f.reload_action.elapsed + 1e-9 >= native_reload_duration) f.reload_action.state = ReloadState::complete;
            }
        }
        o = controller.step(port, caps, f);
        if (o.reload_cancelled) f.reload_action.state = ReloadState::cancelled;
        return o;
    }
    void wait(double duration) {
        // Exercise every simulated game frame, never skip directly past a pause.
        while (duration > 0.000001) { auto dt = std::min(0.010, duration); tick(dt); duration -= dt; }
    }
    void reload() { f.reload = true; tick(0.010); f.reload = false; tick(0); }
};
int main() {
    unsigned checks = 0;
    auto check = [&](bool value) { ++checks; if (!value) std::cerr << "Failed check " << checks << '\n'; assert(value); };
    Harness h;
    check(h.o.magazine == 15 && h.o.reserve == 84 && h.o.take_input_ownership);
    h.f.trigger = true;
    check(h.tick(0.010).allow_primary_shot && !h.o.confirmed_shot);
    check(!h.tick(0.100).allow_primary_shot && !h.o.confirmed_shot);
    h.port.consume();
    h.f.shot = {1, Fixture::player, 1250000, 15, 14};
    check(h.tick(0.010).confirmed_shot && h.o.recoil_pitch_impulse == 35 && h.o.recoil_yaw_impulse == 0);
    check(std::abs(h.o.view_kick_degrees[0] + 0.33125f) < 1e-6f && h.o.view_kick_degrees[1] == 0);
    check(!h.tick(0.010).confirmed_shot);
    h.f.trigger = false; h.tick(0.010); h.reload();
    check(h.o.reload_started && h.o.phase == Phase::reloading);
    h.wait(1.190);
    check(h.port.transfers == 0 && h.o.magazine == 14 && h.o.reserve == 84);
    h.tick(0.010);
    check(h.o.ammo_transferred && h.o.magazine == 15 && h.o.reserve == 83 && h.port.transfers == 1);
    h.wait(0.420);
    check(h.o.phase == Phase::reloading);
    check(h.tick(0.010).reload_finished && h.o.phase == Phase::ready);
    h.wait(0.100); check(h.port.transfers == 1);

    Harness empty; empty.port.magazine(1); empty.tick(0.010); empty.port.consume();
    empty.f.shot = {1, Fixture::player, 1250000, 1, 0};
    check(empty.tick(0.010).confirmed_shot && empty.o.magazine == 0);
    empty.reload(); empty.wait(1.200);
    check(empty.o.ammo_transferred && empty.o.magazine == 15 && empty.o.reserve == 69);
    empty.wait(0.710); check(empty.o.phase == Phase::reloading);
    check(empty.tick(0.007).reload_finished && empty.o.phase == Phase::ready);
    InventoryView saved; check(empty.port.read(saved) == ReadStatus::ok && saved.native.first_bolt.index == 1);
    M9Controller resumed;
    auto loaded = resumed.step(empty.port, empty.caps, empty.f);
    check(loaded.magazine == 15 && loaded.reserve == 69); // no counter reset/refill

    Harness limited; limited.port.magazine(2); limited.port.reserve(3); limited.reload(); limited.wait(1.200);
    check(limited.o.magazine == 5 && limited.o.reserve == 0);
    limited.wait(0.500); limited.reload(); check(!limited.o.reload_started);
    Harness full; full.reload(); check(!full.o.reload_started && full.port.transfers == 0);

    for (int reason = 0; reason < 8; ++reason) {
        Harness c; c.port.magazine(5); c.reload(); c.wait(0.500);
        switch (reason) {
        case 0: c.f.focused = false; break;
        case 1: c.f.gameplay = false; break;
        case 2: c.port.memory.put(Fixture::player + 0x3e8, std::uint32_t(0)); break;
        case 3: c.port.memory.put(Fixture::player + 0x3e8, std::uint32_t(499)); break;
        case 4: c.port.memory.put(Fixture::pad + 0x84 + 15, std::uint8_t(1)); break;
        case 5: c.f.cancel_action = true; break;
        case 6: c.f.load_epoch++; break;
        case 7: c.port.reserve(83); break;
        }
        check(c.tick(0.010).reload_cancelled && c.port.transfers == 0);
        InventoryView v; check(c.port.read(v) == ReadStatus::ok && v.native.first_bolt.quantity == 5);
    }
    Harness after; after.port.magazine(5); after.reload(); after.wait(1.200); after.f.cancel_action = true;
    check(after.tick(0.010).reload_cancelled && after.o.magazine == 15 && after.o.reserve == 74);
    Harness stale; stale.port.magazine(2); stale.reload(); stale.port.simulate = TransferStatus::stale; stale.wait(1.200);
    check(stale.o.reload_cancelled && stale.o.magazine == 2 && stale.o.reserve == 84);
    Harness broken; broken.port.magazine(2); broken.reload(); broken.port.partial_write = true; broken.wait(1.200);
    check(broken.o.phase == Phase::fault && !broken.o.allow_primary_shot);
    broken.wait(0.500); check(broken.port.transfers == 1 && broken.o.phase == Phase::fault);
    broken.f.focused = false;
    check(broken.tick(0.010).phase == Phase::fault && !broken.o.take_input_ownership);
    broken.f.focused = true;
    broken.port.memory.put(Fixture::equip + 0xb0, std::int32_t(1000000));
    check(broken.tick(0.010).phase == Phase::fault && !broken.o.take_input_ownership);
    broken.port.memory.put(Fixture::equip + 0xb0, std::int32_t(1250000));
    check(broken.tick(0.010).phase == Phase::fault && broken.o.take_input_ownership && broken.port.transfers == 1);
    Harness slow; slow.port.magazine(2); slow.reload(); check(slow.tick(1.500).reload_cancelled && slow.port.transfers == 0);
    Harness backwards; backwards.port.magazine(2); backwards.reload();
    check(backwards.tick(-0.010).reload_cancelled && backwards.port.transfers == 0);
    Harness swapped; swapped.port.magazine(2); swapped.reload();
    swapped.port.memory.put(Fixture::equip + 0xb0, std::int32_t(1250100));
    check(swapped.tick(0.010).reload_cancelled && swapped.port.transfers == 0);
    Harness gated; gated.caps.input_phase = false; gated.f.trigger = gated.f.reload = true;
    check(!gated.tick(0.010).take_input_ownership && gated.port.transfers == 0);
    Harness no_reload_contract; no_reload_contract.caps.reload_confirmation = false;
    no_reload_contract.port.magazine(2); no_reload_contract.reload();
    check(!no_reload_contract.o.take_input_ownership && !no_reload_contract.o.reload_requested);
    Harness no_ack; no_ack.simulate_native_reload = false; no_ack.port.magazine(2);
    no_ack.f.reload = true;
    check(no_ack.tick(0.010).reload_requested && !no_ack.o.reload_started && no_ack.o.phase == Phase::awaiting_reload);
    no_ack.wait(0.250);
    check(no_ack.o.phase == Phase::awaiting_reload && no_ack.port.transfers == 0);
    check(no_ack.tick(0.010).reload_cancelled && no_ack.port.transfers == 0);
    no_ack.wait(1.500);
    check(no_ack.o.phase == Phase::ready && no_ack.port.transfers == 0);
    no_ack.f.reload_action = {1, Fixture::player, 1250000, 1.3, ReloadState::playing};
    check(!no_ack.tick(0.010).reload_started && no_ack.port.transfers == 0); // late acknowledgement cannot revive cancelled request
    Harness paused_action; paused_action.port.magazine(2); paused_action.reload();
    paused_action.simulate_native_reload = false; paused_action.wait(2.0);
    check(paused_action.o.phase == Phase::reloading && paused_action.port.transfers == 0);
    paused_action.simulate_native_reload = true; paused_action.wait(1.200);
    check(paused_action.o.ammo_transferred && paused_action.o.magazine == 15 && paused_action.o.reserve == 71);
    paused_action.simulate_native_reload = false;
    paused_action.f.reload_action.elapsed = 1.4; paused_action.tick(0.010);
    paused_action.f.reload_action.elapsed = 1.63; paused_action.tick(0.010);
    check(paused_action.o.phase == Phase::reloading && !paused_action.o.reload_finished);
    paused_action.f.reload_action.state = ReloadState::complete;
    check(paused_action.tick(0.010).reload_finished && paused_action.port.transfers == 1);
    for (unsigned reason = 0; reason < 7; ++reason) {
        Harness invalid_action; invalid_action.port.magazine(2); invalid_action.reload(); invalid_action.wait(0.500);
        invalid_action.simulate_native_reload = false;
        switch (reason) {
        case 0: invalid_action.f.reload_action.sequence++; break;
        case 1: invalid_action.f.reload_action.player++; break;
        case 2: invalid_action.f.reload_action.weapon++; break;
        case 3: invalid_action.f.reload_action.elapsed = 0.1; break;
        case 4: invalid_action.f.reload_action.elapsed = 1.2; break;
        case 5: invalid_action.f.reload_action.state = ReloadState::complete; break;
        case 6: invalid_action.f.reload_action.elapsed = std::numeric_limits<double>::quiet_NaN(); break;
        }
        check(invalid_action.tick(0.010).reload_cancelled && invalid_action.port.transfers == 0);
    }
    Harness cancelled_action; cancelled_action.port.magazine(2); cancelled_action.reload(); cancelled_action.wait(1.200);
    cancelled_action.simulate_native_reload = false; cancelled_action.f.reload_action.state = ReloadState::cancelled;
    check(cancelled_action.tick(0.010).reload_cancelled && cancelled_action.o.magazine == 15 && cancelled_action.o.reserve == 71);
    Harness busy; busy.port.magazine(2); busy.f.weapon_action_ready = false; busy.f.trigger = true; busy.reload();
    check(!busy.o.reload_started && !busy.o.allow_primary_shot && busy.port.transfers == 0);
    Harness legacy; legacy.port.magazine(99); check(legacy.tick(0.010).phase == Phase::inactive);
    Harness wrong_ammo; wrong_ammo.port.memory.put(Fixture::equip + 0x38, std::int32_t(-1));
    wrong_ammo.port.memory.put(Fixture::equip + 0xb8, std::int32_t(2103000));
    check(wrong_ammo.tick(0.010).phase == Phase::inactive);
    Harness rate; rate.f.trigger = true; check(rate.tick(0.010).allow_primary_shot);
    rate.f.trigger = false; rate.tick(0.020); rate.f.trigger = true;
    check(!rate.tick(0.020).allow_primary_shot);
    rate.f.trigger = false; rate.tick(0.020); rate.f.trigger = true;
    check(rate.tick(0.020).allow_primary_shot);
    Harness held; held.f.trigger = true; held.f.load_epoch++;
    check(!held.tick(0.010).allow_primary_shot && !held.tick(0.100).allow_primary_shot);
    Harness aim; aim.f.aim = true; check(std::abs(aim.tick(0.050).ads_blend - 0.5) < 1e-8);
    check(aim.tick(0.050).ads_blend == 1); aim.f.aim = false;
    check(aim.tick(0.100).ads_blend == 0);
    Harness bad_shot; bad_shot.port.consume();
    check(!bad_shot.tick(0.010).confirmed_shot); // external removal != firing
    bad_shot.f.shot = {1, Fixture::player, 1250000, 15, 14};
    check(!bad_shot.tick(0.010).confirmed_shot); // stale receipt != firing
    bad_shot.f.now = std::numeric_limits<double>::quiet_NaN();
    check(bad_shot.tick(0).phase == Phase::inactive);
    Item found;
    check(find_inventory_item(h.port.memory, Fixture::equip, goods_category, m9_reserve_id, found) == ReadStatus::ok && found.quantity == 83);
    h.port.memory.item(Fixture::list_one, m9_reserve_id, 1); h.port.memory.put(Fixture::list_one, goods_category);
    check(find_inventory_item(h.port.memory, Fixture::equip, goods_category, m9_reserve_id, found) == ReadStatus::invalid);
    ReadOnlyInventory readonly(empty.port.memory, Fixture::image);
    check(readonly.transfer({saved, 1, false}) == TransferStatus::unavailable);
    Iw4ViewKick recoil;
    check(recoil.impulse(35, 55) && recoil.degrees()[0] == 0); // velocity, not an immediate 35-degree jump
    check(recoil.step(5, 750) && std::abs(recoil.degrees()[0] + 0.175f) < 1e-6f);
    check(std::abs(recoil.degrees()[1] - 0.275f) < 1e-6f && std::abs(recoil.degrees()[2] + 0.1375f) < 1e-6f);
    check(recoil.step(5, 750) && std::abs(recoil.degrees()[0] + 0.33125f) < 1e-6f);
    for (int i=0; i<40; ++i) check(recoil.step(50, 750));
    check(recoil.degrees()[0] == 0 && recoil.degrees()[1] == 0 && recoil.degrees()[2] == 0);
    check(!recoil.impulse(std::numeric_limits<float>::quiet_NaN(), 0));
    check(!recoil.step(251, 750) && !recoil.step(-1, 750) && !recoil.step(5, 0));
    check(recoil.impulse(1000, 0) && recoil.step(15, 750) && recoil.degrees()[0] == -10);
    check(recoil.step(5, 750) && recoil.degrees()[0] > -10 && recoil.degrees()[0] < 0);
    recoil.reset(); check(recoil.degrees()[0] == 0 && recoil.velocity()[0] == 0);
    for (unsigned failure = 0; failure <= 3; ++failure) {
        Port p; p.magazine(2); Api api(p); api.fail_on = failure;
        TransactionalInventory transaction(p.memory, Fixture::image, api);
        InventoryView before, after;
        check(transaction.read(before) == ReadStatus::ok);
        auto status = transaction.transfer({before, 13, false});
        check(transaction.read(after) == ReadStatus::ok && !api.active && api.ends == 1);
        if (!failure) {
            check(status == TransferStatus::committed && after.native.first_bolt.quantity == 15 && after.reserve.quantity == 71);
        } else {
            check(status == TransferStatus::rolled_back && same_inventory_values(before, after) && !transaction.faulted);
        }
    }
    Port zero; zero.magazine(1); zero.consume(); zero.memory.put(Fixture::equip + 0xb8, std::int32_t(-1));
    Api zero_api(zero); TransactionalInventory tx(zero.memory, Fixture::image, zero_api);
    InventoryView before, final;
    check(tx.read(before) == ReadStatus::ok);
    check(tx.transfer({before, 15, true}) == TransferStatus::committed);
    check(tx.read(final) == ReadStatus::ok && final.native.first_bolt.quantity == 15 && final.reserve.quantity == 69);
    check(tx.transfer({before, 15, true}) == TransferStatus::stale); // old snapshot cannot double credit
    zero_api.granted = false;
    check(tx.transfer({final, 1, false}) == TransferStatus::unavailable);
    Port damage; damage.magazine(2); Api bad_api(damage); bad_api.fail_on = 2; bad_api.fail_forever = true;
    TransactionalInventory bad_tx(damage.memory, Fixture::image, bad_api);
    check(bad_tx.read(before) == ReadStatus::ok);
    check(bad_tx.transfer({before, 13, false}) == TransferStatus::failed && bad_tx.faulted && !bad_api.active);
    const auto attempts = bad_api.calls;
    check(bad_tx.transfer({before, 13, false}) == TransferStatus::failed && bad_api.calls == attempts);
    Port interleaved; interleaved.magazine(2); Api interrupted_api(interleaved); interrupted_api.interleave_damage = true;
    TransactionalInventory interrupted_tx(interleaved.memory, Fixture::image, interrupted_api);
    check(interrupted_tx.read(before) == ReadStatus::ok);
    check(interrupted_tx.transfer({before, 13, false}) == TransferStatus::failed && interrupted_tx.faulted);
    check(interrupted_api.calls == 3 && !interrupted_api.active); // no further writes after observing violated transaction scope
    std::cout << checks << " handling/inventory fixture checks passed; no native game writes executed\n";
}
