// Original pure helpers for the SCAR-H M203 projectile swap: locate the live
// Standard Bolt Bullet row by its exact bytes, and decide each frame whether the
// row should hold the bolt or the grenade. Never writes on its own; refuses any
// row that is neither known image.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace dsr_mw2 {
struct PatternMatches {
    static constexpr std::size_t cap = 4;
    std::uint64_t at[cap]{};
    std::size_t count = 0;   // total matches seen (may exceed cap)
    void add(std::uint64_t address) { if (count < cap) at[count] = address; ++count; }
};

// Search one chunk read from `base`. Callers overlap consecutive chunks by
// `size - 1` bytes; `skip_before` drops matches already reported by the
// previous chunk's tail.
inline void scan_chunk(std::uint64_t base, const std::uint8_t* data, std::size_t length,
                       const std::uint8_t* pattern, std::size_t size, std::uint64_t skip_before,
                       PatternMatches& out) {
    if (!size || length < size) return;
    for (std::size_t i = 0; i + size <= length; ++i) {
        if (data[i] != pattern[0] || std::memcmp(data + i, pattern, size)) continue;
        const std::uint64_t address = base + i;
        if (address >= skip_before) out.add(address);
    }
}

enum class SwapAction { none, to_grenade, to_bolt, fault };

inline SwapAction decide_swap(bool want_grenade, const std::uint8_t* current, const std::uint8_t* bolt,
                              const std::uint8_t* grenade, std::size_t size) {
    const bool is_bolt = !std::memcmp(current, bolt, size), is_grenade = !std::memcmp(current, grenade, size);
    if (!is_bolt && !is_grenade) return SwapAction::fault;
    if (want_grenade) return is_grenade ? SwapAction::none : SwapAction::to_grenade;
    return is_bolt ? SwapAction::none : SwapAction::to_bolt;
}
} // namespace dsr_mw2
