#include "m9_handling.hpp"
#include <algorithm>
#include <cmath>

namespace dsr_mw2 {
bool same_item(const Item& a, const Item& b) {
    return a.index == b.index && a.category == b.category && a.id == b.id &&
           a.quantity == b.quantity && a.active == b.active;
}
static bool same_actor(const InventoryView& a, const InventoryView& b) {
    const auto& x = a.native;
    const auto& y = b.native;
    return x.player == y.player && x.player_data == y.player_data && x.equip_data == y.equip_data &&
        x.manipulator == y.manipulator && x.right_weapon == y.right_weapon && x.left_weapon == y.left_weapon &&
        x.right_slot == y.right_slot && x.left_slot == y.left_slot && x.weapon_style == y.weapon_style;
}
bool same_inventory(const InventoryView& a, const InventoryView& b) {
    return same_actor(a, b) && a.native.first_bolt_equipped_id == b.native.first_bolt_equipped_id &&
           a.native.second_bolt_equipped_id == b.native.second_bolt_equipped_id && same_item(a.native.first_bolt, b.native.first_bolt) &&
           same_item(a.native.second_bolt, b.native.second_bolt) && same_item(a.reserve, b.reserve);
}
static bool same_item_values(const Item& a, const Item& b) {
    // Zero-count native stacks may be deleted or reallocated on rollback.
    if (a.quantity == 0 && b.quantity == 0) return true;
    return a.id == b.id && a.category == b.category && a.quantity == b.quantity && a.active == b.active;
}
bool same_inventory_values(const InventoryView& a, const InventoryView& b) {
    return same_actor(a, b) && a.native.first_bolt_equipped_id == b.native.first_bolt_equipped_id &&
        a.native.second_bolt_equipped_id == b.native.second_bolt_equipped_id &&
        same_item_values(a.native.first_bolt, b.native.first_bolt) &&
        same_item_values(a.native.second_bolt, b.native.second_bolt) && same_item_values(a.reserve, b.reserve);
}
ReadStatus observe_inventory(const Reader& memory, Address base, InventoryView& out) {
    out = {};
    InventoryView candidate;
    auto status = observe(memory, base, candidate.native);
    if (status != ReadStatus::ok) return status;
    status = find_inventory_item(memory, candidate.native.equip_data, goods_category, m9_reserve_id, candidate.reserve);
    if (status != ReadStatus::ok) return status;
    // Two-pass identity/quantity check: the scan may span an inventory mutation.
    Snapshot after;
    status = observe(memory, base, after);
    if (status != ReadStatus::ok) return status;
    InventoryView second{after, {}};
    status = find_inventory_item(memory, after.equip_data, goods_category, m9_reserve_id, second.reserve);
    if (status != ReadStatus::ok) return status;
    if (!same_inventory(candidate, second) || candidate.native.hp != after.hp) return ReadStatus::changed;
    out = second;
    return ReadStatus::ok;
}
void M9Controller::reset() { *this = M9Controller{}; }
static bool supported(const InventoryView& view) {
    const auto& s = view.native;
    const auto& b = s.first_bolt;
    const auto& r = view.reserve;
    return s.player && s.hp && is_m9(s.right_weapon) && !is_m9(s.left_weapon) &&
        (s.first_bolt_equipped_id == -1 || s.first_bolt_equipped_id == static_cast<std::int32_t>(standard_bolt)) &&
        (b.id == -1 || (b.category == 0 && b.id == static_cast<std::int32_t>(standard_bolt) && b.active)) &&
        b.quantity >= 0 && b.quantity <= m9_capacity &&
        (r.id == -1 || (r.category == goods_category && r.id == m9_reserve_id && r.active)) &&
        r.quantity >= 0 && r.quantity <= 999;
}
static bool interrupt_action(const Snapshot& s) {
    // Verified action byte indices. Sprint/menu/animation phase are supplied by
    // the driver through Frame; no speculative native offsets are used here.
    return s.actions[10] || s.actions[14] || s.actions[15] || s.actions[42];
}
TransferStatus TransactionalInventory::transfer(const Transfer& request) {
    if (faulted) return TransferStatus::failed;
    if (!api.begin(request.expected)) return TransferStatus::unavailable;
    struct Scope { NativeInventoryApi& api; ~Scope() { api.end(); } } scope{api};
    InventoryView before;
    if (read(before) != ReadStatus::ok || !same_inventory(before, request.expected) ||
        !supported(before) || before.native.hp != request.expected.native.hp ||
        request.rounds <= 0 || request.rounds > before.reserve.quantity ||
        request.rounds > m9_capacity - before.native.first_bolt.quantity ||
        request.recreate_first_bolt != (before.native.first_bolt.id == -1)) return TransferStatus::stale;
    const auto magazine = before.native.first_bolt.quantity;
    const auto reserve = before.reserve.quantity;
    const auto bolt_id = static_cast<std::int32_t>(standard_bolt);
    // Debit first; do not expose a momentary ammo duplication even inside the
    // required non-interleaved scope. Readback must prove both sides succeeded.
    const bool changed = api.set_count(goods_category, m9_reserve_id, reserve - request.rounds) &&
        api.set_count(0, bolt_id, magazine + request.rounds) && api.equip_first_bolt(bolt_id);
    InventoryView after;
    const bool readable = read(after) == ReadStatus::ok;
    if (changed && readable && same_actor(before, after) && before.native.hp == after.native.hp &&
        after.native.first_bolt.active && after.native.first_bolt.id == bolt_id && after.native.first_bolt.category == 0 &&
        after.native.first_bolt_equipped_id == bolt_id && after.native.first_bolt.quantity == magazine + request.rounds &&
        after.reserve.quantity == reserve - request.rounds &&
        (after.reserve.quantity == 0 || (after.reserve.id == m9_reserve_id && after.reserve.category == goods_category)) &&
        after.native.second_bolt_equipped_id == before.native.second_bolt_equipped_id &&
        same_item(before.native.second_bolt, after.native.second_bolt)) return TransferStatus::committed;
    // Never restore into a changed character. Unexpected interleaving violates
    // begin()'s contract and requires stopping the driver, not a blind retry.
    if (!readable || !same_actor(before, after) || before.native.hp != after.native.hp) {
        faulted = true;
        return TransferStatus::failed;
    }
    const bool mag_restored = api.set_count(0, bolt_id, magazine);
    const bool reserve_restored = api.set_count(goods_category, m9_reserve_id, reserve);
    const bool slot_restored = api.equip_first_bolt(before.native.first_bolt_equipped_id);
    InventoryView restored;
    if (mag_restored && reserve_restored && slot_restored && read(restored) == ReadStatus::ok &&
        same_inventory_values(before, restored)) return TransferStatus::rolled_back;
    faulted = true;
    return TransferStatus::failed;
}
Output M9Controller::step(InventoryPort& port, const Capabilities& caps, const Frame& f) {
    Output o;
    InventoryView current;
    o.read_status = port.read(current);
    const bool was_reloading = phase_ == Phase::reloading || phase_ == Phase::awaiting_reload;
    const bool enabled = caps.game_thread && caps.input_phase && caps.inventory_transaction &&
        caps.zero_stack_recreation && caps.shot_confirmation && caps.reload_confirmation;
    if (fault_) {
        o.phase = Phase::fault;
        // Keep the fault latched, but never capture another actor/weapon/menu's
        // input after a failed transaction. Only an explicit reset clears it.
        o.take_input_ownership = o.read_status == ReadStatus::ok && enabled && f.focused && f.gameplay &&
            f.magazine_data && f.load_epoch == epoch_ && supported(current) && same_actor(previous_, current);
        o.suppress_alternate_shot = o.take_input_ownership;
        return o;
    }
    if (o.read_status != ReadStatus::ok || !enabled || !f.focused || !f.gameplay || !f.magazine_data ||
        !std::isfinite(f.now) || !std::isfinite(f.pitch_sample) || !std::isfinite(f.yaw_sample) ||
        !supported(current)) {
        reset();
        o.reload_cancelled = was_reloading;
        return o;
    }
    const bool changed = initialized_ && (!same_actor(previous_, current) || f.load_epoch != epoch_ ||
        f.now < last_time_ || f.now - last_time_ > 0.250);
    if (!initialized_ || changed) {
        reset();
        initialized_ = true;
        phase_ = Phase::ready;
        epoch_ = f.load_epoch;
        last_time_ = f.now;
        previous_ = current;
        // Never fire/reload from a held input during a load, focus or slot change.
        trigger_ = f.trigger;
        reload_ = f.reload;
        shot_sequence_ = f.shot.sequence;
        o.reload_cancelled = was_reloading;
    }
    const double dt = f.now - last_time_;
    o.take_input_ownership = true;
    o.suppress_alternate_shot = true;
    o.magazine = current.native.first_bolt.quantity;
    o.reserve = current.reserve.quantity;
    const bool interrupted = f.cancel_action || interrupt_action(current.native) || current.native.hp < previous_.native.hp;
    if (was_reloading && (interrupted || !same_inventory(reload_inventory_, current))) {
        phase_ = Phase::ready;
        committed_ = false;
        o.reload_cancelled = true;
    }
    const auto& action = f.reload_action;
    const bool action_identity = action.player == current.native.player && action.weapon == current.native.right_weapon;
    if (phase_ == Phase::awaiting_reload) {
        if (action_identity && action.sequence > reload_sequence_ && action.state == ReloadState::playing &&
            std::isfinite(action.elapsed) && action.elapsed >= 0 && action.elapsed <= 0.250) {
            reload_sequence_ = action.sequence;
            reload_elapsed_ = 0;
            phase_ = Phase::reloading;
            o.reload_started = true;
        } else if (f.now - reload_start_ > 0.250 || action.sequence > reload_sequence_) {
            phase_ = Phase::ready;
            o.reload_cancelled = true;
        }
    }
    if (phase_ == Phase::reloading) {
        // Wall time can expire a missing acknowledgement, but cannot credit
        // ammo or finish a reload. Those follow the verified native action.
        const bool valid = action_identity && action.sequence == reload_sequence_ &&
            (action.state == ReloadState::playing || action.state == ReloadState::complete) &&
            std::isfinite(action.elapsed) && action.elapsed + 1e-9 >= reload_elapsed_ &&
            action.elapsed - reload_elapsed_ <= 0.250 + 1e-9 && action.elapsed <= reload_duration_ + 0.250;
        if (!valid || (action.state == ReloadState::complete && action.elapsed + 1e-9 < reload_duration_)) {
            phase_ = Phase::ready;
            committed_ = false;
            o.reload_cancelled = true;
        }
    }
    if (phase_ == Phase::reloading) {
        const double elapsed = action.elapsed;
        reload_elapsed_ = elapsed;
        if (!committed_ && elapsed + 1e-9 >= m9_reload_add) {
            const auto rounds = std::min(m9_capacity - o.magazine, o.reserve);
            const Transfer request{current, rounds, current.native.first_bolt.id == -1};
            const auto result = port.transfer(request);
            InventoryView after;
            const auto read_back = port.read(after);
            if (result == TransferStatus::committed && read_back == ReadStatus::ok &&
                same_actor(current, after) && after.native.first_bolt.active &&
                after.native.first_bolt.id == static_cast<std::int32_t>(standard_bolt) &&
                after.native.first_bolt_equipped_id == static_cast<std::int32_t>(standard_bolt) &&
                after.native.first_bolt.category == 0 && after.native.first_bolt.quantity == o.magazine + rounds &&
                after.reserve.quantity == o.reserve - rounds &&
                (after.reserve.quantity == 0 || (after.reserve.id == m9_reserve_id && after.reserve.category == goods_category)) &&
                after.native.hp == current.native.hp && after.native.second_bolt_equipped_id == current.native.second_bolt_equipped_id &&
                same_item(current.native.second_bolt, after.native.second_bolt)) {
                current = after;
                reload_inventory_ = after;
                committed_ = true;
                o.ammo_transferred = true;
                o.magazine = after.native.first_bolt.quantity;
                o.reserve = after.reserve.quantity;
            } else if (read_back == ReadStatus::ok &&
                       (((result == TransferStatus::stale || result == TransferStatus::unavailable) && same_inventory(current, after)) ||
                        (result == TransferStatus::rolled_back && same_inventory_values(current, after)))) {
                phase_ = Phase::ready;
                o.reload_cancelled = true;
                current = after;
            } else {
                // Unknown partial write: do not retry, grant fire or invent a
                // successful rollback. An explicit driver recovery is required.
                fault_ = true;
                o.phase = Phase::fault;
                return o;
            }
        }
        if (phase_ == Phase::reloading && committed_ && action.state == ReloadState::complete && elapsed + 1e-9 >= reload_duration_) {
            phase_ = Phase::ready;
            o.reload_finished = true;
        }
    }
    if (phase_ == Phase::ready && f.weapon_action_ready && !interrupted && !o.reload_cancelled && f.reload && !reload_ &&
        o.magazine < m9_capacity && o.reserve > 0) {
        phase_ = Phase::awaiting_reload;
        committed_ = false;
        reload_start_ = f.now;
        reload_duration_ = o.magazine ? m9_reload_tactical : m9_reload_empty;
        reload_inventory_ = current;
        reload_sequence_ = action.sequence;
        reload_elapsed_ = 0;
        o.reload_requested = true;
    }
    // Match a native projectile/ammo receipt to the observed one-round decrement.
    // Button presses, drops and unexplained stack changes never produce recoil.
    const auto& receipt = f.shot;
    const bool consumed = receipt.sequence > shot_sequence_ && receipt.player == current.native.player &&
        receipt.weapon == current.native.right_weapon && receipt.before > 0 && receipt.after == receipt.before - 1 &&
        receipt.before == previous_.native.first_bolt.quantity && receipt.after == current.native.first_bolt.quantity &&
        same_item(previous_.reserve, current.reserve) && !o.ammo_transferred && !changed;
    if (receipt.sequence > shot_sequence_) shot_sequence_ = receipt.sequence;
    if (consumed) {
        o.confirmed_shot = true;
        o.recoil_pitch_impulse = m9_view_pitch_min + (m9_view_pitch_max - m9_view_pitch_min) * std::clamp(f.pitch_sample, 0.0, 1.0);
        // Export really stores 55 -> -55; interpolate without sorting it.
        o.recoil_yaw_impulse = m9_view_yaw_min + (m9_view_yaw_max - m9_view_yaw_min) * std::clamp(f.yaw_sample, 0.0, 1.0);
        view_kick_.impulse(static_cast<float>(o.recoil_pitch_impulse), static_cast<float>(o.recoil_yaw_impulse));
    }
    const double kick_ms = dt * 1000 + kick_ms_remainder_;
    const auto whole_ms = static_cast<int>(std::floor(kick_ms + 1e-7));
    kick_ms_remainder_ = std::max(0.0, kick_ms - whole_ms);
    view_kick_.step(whole_ms, static_cast<float>(m9_view_center_speed));
    o.view_kick_degrees = view_kick_.degrees();
    const bool aim = f.aim && phase_ == Phase::ready && !interrupted;
    ads_ = std::clamp(ads_ + (aim ? dt : -dt) / m9_ads_time, 0.0, 1.0);
    if (phase_ == Phase::ready && f.weapon_action_ready && !interrupted && !o.reload_cancelled && f.trigger && !trigger_ &&
        o.magazine > 0 && f.now - last_request_ + 1e-9 >= m9_fire_interval) {
        o.allow_primary_shot = true;
        last_request_ = f.now;
    }
    o.ads_blend = ads_;
    o.phase = phase_;
    previous_ = current;
    last_time_ = f.now;
    trigger_ = f.trigger;
    reload_ = f.reload;
    return o;
}
} // namespace dsr_mw2
