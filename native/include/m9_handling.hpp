// Original controller. Native counts are authoritative; no shadow ammo balance.
#pragma once
#include "dsr_snapshot.hpp"
#include "iw4_view_kick.hpp"

namespace dsr_mw2 {
constexpr std::int32_t m9_capacity = 15;
// Seconds from the hash-pinned beretta_mp export; not animation clip lengths.
constexpr double m9_fire_interval = 0.080;
constexpr double m9_reload_add = 1.200;
constexpr double m9_reload_tactical = 1.630;
constexpr double m9_reload_empty = 1.917;
constexpr double m9_ads_time = 0.100;
constexpr double m9_ads_fov = 65.0;
constexpr double m9_view_pitch_min = 25.0, m9_view_pitch_max = 45.0;
constexpr double m9_view_yaw_min = 55.0, m9_view_yaw_max = -55.0;
constexpr double m9_view_center_speed = 750.0;

struct InventoryView { Snapshot native; Item reserve; };
ReadStatus observe_inventory(const Reader&, Address image_base, InventoryView&);
bool same_item(const Item&, const Item&);
bool same_inventory(const InventoryView&, const InventoryView&);
bool same_inventory_values(const InventoryView&, const InventoryView&);

struct Transfer {
    InventoryView expected;
    std::int32_t rounds = 0;
    // A final native shot may destroy/unequip the bolt stack. A verified native
    // writer must recreate AND equip it, never write through a stale address.
    bool recreate_first_bolt = false;
};
enum class TransferStatus { committed, stale, unavailable, rolled_back, failed };
struct InventoryPort {
    virtual ReadStatus read(InventoryView&) = 0;
    // All-or-nothing contract: same game thread, no save/interleaving between
    // debit and credit, compare all preconditions, read back final state.
    // On failure, restore both stacks/equipment before returning. If restoration
    // is impossible, stop the integration; never retry a partially applied write.
    virtual TransferStatus transfer(const Transfer&) = 0;
    virtual ~InventoryPort() = default;
};
// Safe production default. Real memory can be observed but cannot be changed.
struct ReadOnlyInventory final : InventoryPort {
    const Reader& memory;
    Address base;
    ReadOnlyInventory(const Reader& m, Address b) : memory(m), base(b) {}
    ReadStatus read(InventoryView& out) override { return observe_inventory(memory, base, out); }
    TransferStatus transfer(const Transfer&) override { return TransferStatus::unavailable; }
};

// Semantic native API boundary, NOT a guessed game function-pointer typedef.
// The future version-pinned driver must implement these through verified native
// add/remove/equip calls. No implementation that mutates a game is included.
struct NativeInventoryApi {
    // Acquire a game-thread/no-save-interleaving scope or return false. Mere
    // possession of an inventory address is not sufficient authorization.
    virtual bool begin(const InventoryView& expected) = 0;
    virtual void end() = 0;
    virtual bool set_count(std::uint32_t category, std::int32_t id, std::int32_t quantity) = 0;
    virtual bool equip_first_bolt(std::int32_t id) = 0;
    virtual ~NativeInventoryApi() = default;
};
struct TransactionalInventory final : InventoryPort {
    const Reader& memory;
    Address base;
    NativeInventoryApi& api;
    bool faulted = false;
    TransactionalInventory(const Reader& m, Address b, NativeInventoryApi& a) : memory(m), base(b), api(a) {}
    ReadStatus read(InventoryView& out) override { return observe_inventory(memory, base, out); }
    TransferStatus transfer(const Transfer&) override;
};

// These assertions must come from a verified game-thread driver, not user config.
// There is no such installed driver yet. Defaults deliberately enable nothing.
struct Capabilities {
    bool game_thread = false, input_phase = false, inventory_transaction = false;
    bool zero_stack_recreation = false, shot_confirmation = false, reload_confirmation = false;
};
struct ShotReceipt {
    std::uint64_t sequence = 0;
    Address player = 0;
    std::int32_t weapon = -1, before = 0, after = 0;
};
enum class ReloadState { unavailable, playing, complete, cancelled };
// This is a semantic receipt from a future verified native action callback.
// It must not be synthesized from a button press or a wall-clock timer.
struct ReloadReceipt {
    std::uint64_t sequence = 0;
    Address player = 0;
    std::int32_t weapon = -1;
    double elapsed = 0;
    ReloadState state = ReloadState::unavailable;
};
struct Frame {
    double now = 0;
    std::uint64_t load_epoch = 0;
    bool focused = false, gameplay = false, magazine_data = false;
    // Verified native weapon idle/action-acceptance phase, not just "no button".
    bool weapon_action_ready = false;
    bool trigger = false, reload = false, aim = false, cancel_action = false;
    ShotReceipt shot;
    ReloadReceipt reload_action;
    // Deterministic samples provided by the future native firing callback.
    double pitch_sample = 0.5, yaw_sample = 0.5;
};
enum class Phase { inactive, ready, awaiting_reload, reloading, fault };
struct Output {
    Phase phase = Phase::inactive;
    ReadStatus read_status = ReadStatus::unloaded;
    std::int32_t magazine = 0, reserve = 0;
    bool take_input_ownership = false, allow_primary_shot = false;
    bool suppress_alternate_shot = false, reload_requested = false, reload_started = false, ammo_transferred = false;
    bool reload_finished = false, reload_cancelled = false, confirmed_shot = false;
    double ads_blend = 0, ads_target_fov = m9_ads_fov;
    // Raw exported view-kick impulse values, NOT assumed DSR camera degrees.
    // Mapping them into the native camera is deliberately a separate gate.
    double recoil_pitch_impulse = 0, recoil_yaw_impulse = 0;
    // IW4L view-kick model, evaluated only after a confirmed native shot.
    // Degrees in the source camera convention; DSR sign/ownership mapping is
    // a separate native integration gate. No camera is changed here.
    std::array<float, 3> view_kick_degrees{};
};

class M9Controller {
public:
    Output step(InventoryPort&, const Capabilities&, const Frame&);
    void reset();
private:
    bool initialized_ = false, trigger_ = false, reload_ = false, committed_ = false, fault_ = false;
    double last_time_ = 0, reload_start_ = 0, reload_duration_ = 0, last_request_ = -100, reload_elapsed_ = 0;
    double ads_ = 0;
    std::uint64_t epoch_ = 0, shot_sequence_ = 0, reload_sequence_ = 0;
    Phase phase_ = Phase::inactive;
    InventoryView previous_{}, reload_inventory_{};
    Iw4ViewKick view_kick_;
    double kick_ms_remainder_ = 0;
};

} // namespace dsr_mw2
