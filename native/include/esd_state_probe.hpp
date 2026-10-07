// Original read-only discovery of the player's live EzState (ESD) state records.
// Breadth-first walk of pointers reachable from the player instance. A pointer
// whose target matches a shipped state signature (id plus condition/enter/exit/
// ongoing counts) is a holder; its path from the root is re-read later to report
// which state each machine currently occupies. Never writes memory.
#pragma once
#include "dsr_snapshot.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace dsr_mw2 {
struct EsdStateSignature { std::int32_t machine, state, conditions, enter, exit, ongoing; };
struct EsdStateHit { std::int32_t machine = -1, state = -1; };
inline bool operator==(EsdStateHit a, EsdStateHit b) { return a.machine == b.machine && a.state == b.state; }
inline bool operator!=(EsdStateHit a, EsdStateHit b) { return !(a == b); }

constexpr std::size_t esd_state_record_size = 0x48;  // 9 x int64 (64-bit DSR varints)

inline EsdStateHit match_state_record(const std::uint8_t* bytes, const EsdStateSignature* table, std::size_t count) {
    std::uint64_t f[9];
    std::memcpy(f, bytes, sizeof(f));
    if (f[0] > 0x7fffffffu) return {};
    for (int i : {2, 4, 6, 8}) if (f[i] > 0xffff || (f[i] && !f[i - 1])) return {};
    for (std::size_t i = 0; i < count; ++i) {
        const auto& s = table[i];
        if (std::uint64_t(s.state) == f[0] && std::uint64_t(s.conditions) == f[2] && std::uint64_t(s.enter) == f[4] &&
            std::uint64_t(s.exit) == f[6] && std::uint64_t(s.ongoing) == f[8]) return {s.machine, s.state};
    }
    return {};
}

class EsdStateProbe {
public:
    static constexpr unsigned max_depth = 4;          // pointer hops from the root to a holder field
    static constexpr std::size_t window = 0x400;      // bytes scanned per object
    static constexpr std::size_t node_cap = 12288;
    static constexpr std::size_t visit_cap = 1u << 17;
    static constexpr std::size_t holder_cap = 24;
    struct Holder {
        std::uint8_t length = 0;                      // offsets in path (root field first)
        std::array<std::uint16_t, max_depth + 1> path{};
        EsdStateHit last;
        bool near_buffer = false;                     // within the ESD size of its target; may be ESD-internal
    };

    EsdStateProbe(const EsdStateSignature* table, std::size_t count, std::size_t esd_span)
        : table_(table), count_(count), span_(esd_span) {}

    void reset(Address root) {
        root_ = root; node_count_ = 0; next_ = 0; slot_ = 0; loaded_ = false; holders_ = 0;
        internal_ = 0; reads_ = 0; finished_ = root < 0x10000; std::memset(visited_, 0, sizeof(visited_)); used_ = 0;
        if (!finished_) push(root, -1, 0, 0);
    }
    Address root() const { return root_; }
    bool finished() const { return finished_; }
    std::size_t holders() const { return holders_; }
    std::size_t nodes() const { return node_count_; }
    std::size_t reads() const { return reads_; }
    std::size_t internal() const { return internal_; }
    const Holder& holder(std::size_t i) const { return holder_[i]; }
    Holder& holder(std::size_t i) { return holder_[i]; }

    // Advances discovery by at most `budget` memory reads. Returns the index of
    // the first holder added during this call, or holders() if none was added.
    std::size_t step(const Reader& memory, std::size_t budget) {
        const std::size_t first = holders_;
        std::size_t used = 0;
        while (!finished_ && used < budget) {
            if (next_ >= node_count_ || holders_ >= holder_cap) { finished_ = true; break; }
            Node& node = nodes_[next_];
            if (!loaded_) {
                ++used; ++reads_;
                size_ = load(memory, node.at);
                loaded_ = true; slot_ = 0;
                if (!size_) { ++next_; loaded_ = false; continue; }
            }
            while (slot_ + 8 <= size_ && used < budget) {
                const std::size_t offset = slot_; slot_ += 8;
                std::uint64_t value;
                std::memcpy(&value, buffer_ + offset, sizeof(value));
                if (value < 0x10000 || value >= 0x00007fffffff0000ull || (value & 7) || !visit(value)) continue;
                std::uint8_t record[esd_state_record_size];
                ++used; ++reads_;
                if (!memory.read(value, record, sizeof(record))) continue;
                const EsdStateHit hit = match_state_record(record, table_, count_);
                if (hit.state >= 0) {
                    const Address location = node.at + offset;
                    const Address distance = location > value ? location - value : value - location;
                    // Live state pointers can also sit near the buffer; keep them,
                    // flagged, and let the change trace show which ones move.
                    const bool inside_span = distance < span_;
                    if (inside_span) ++internal_;
                    if (holders_ < holder_cap) {
                        Holder& h = holder_[holders_++];
                        h.near_buffer = inside_span;
                        h.length = static_cast<std::uint8_t>(node.depth + 1);
                        fill_path(next_, h);
                        h.path[node.depth] = static_cast<std::uint16_t>(offset);
                        h.last = hit;
                    }
                    continue;
                }
                if (node.depth + 1u < max_depth && node_count_ < node_cap)
                    push(value, static_cast<std::int32_t>(next_), static_cast<std::uint16_t>(offset), static_cast<std::uint8_t>(node.depth + 1));
            }
            if (slot_ + 8 > size_) { ++next_; loaded_ = false; }
        }
        return first;
    }

    // Re-reads a holder path from the root; unreadable or non-state targets yield {-1,-1}.
    EsdStateHit resolve(const Reader& memory, std::size_t i) const {
        const Holder& h = holder_[i];
        Address at = root_;
        for (std::uint8_t k = 0; k + 1 < h.length; ++k) {
            if (!memory.get(at, h.path[k], at) || at < 0x10000) return {};
        }
        Address target = 0;
        if (!memory.get(at, h.path[h.length - 1], target) || target < 0x10000) return {};
        std::uint8_t record[esd_state_record_size];
        if (!memory.read(target, record, sizeof(record))) return {};
        return match_state_record(record, table_, count_);
    }

private:
    struct Node { Address at; std::int32_t parent; std::uint16_t offset; std::uint8_t depth; };
    void push(Address at, std::int32_t parent, std::uint16_t offset, std::uint8_t depth) {
        nodes_[node_count_++] = {at, parent, offset, depth};
    }
    void fill_path(std::size_t index, Holder& h) const {
        // Offsets from the root down to (not including) the holder field.
        std::size_t i = index;
        while (nodes_[i].parent >= 0) {
            h.path[nodes_[i].depth - 1] = nodes_[i].offset;
            i = static_cast<std::size_t>(nodes_[i].parent);
        }
    }
    std::size_t load(const Reader& memory, Address at) {
        for (std::size_t size : {window, std::size_t(0x100), std::size_t(0x40)})
            if (memory.read(at, buffer_, size)) return size;
        return 0;
    }
    bool visit(Address value) {
        if (used_ * 10 >= visit_cap * 7) return false;  // table full: stop expanding
        std::size_t i = static_cast<std::size_t>((value >> 3) * 0x9E3779B97F4A7C15ull) & (visit_cap - 1);
        while (visited_[i]) {
            if (visited_[i] == value) return false;
            i = (i + 1) & (visit_cap - 1);
        }
        visited_[i] = value; ++used_;
        return true;
    }

    const EsdStateSignature* table_;
    std::size_t count_, span_;
    Address root_ = 0;
    Node nodes_[node_cap]{};
    std::size_t node_count_ = 0, next_ = 0, slot_ = 0, size_ = 0;
    bool loaded_ = false, finished_ = true;
    std::uint8_t buffer_[window]{};
    Address visited_[visit_cap]{};
    std::size_t used_ = 0;
    Holder holder_[holder_cap]{};
    std::size_t holders_ = 0, internal_ = 0, reads_ = 0;
};
} // namespace dsr_mw2
