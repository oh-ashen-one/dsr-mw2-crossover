// Synthetic tests for the SCAR-H M203 projectile swap helpers. No game data.
#include "bullet_swap.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace dsr_mw2;

int main() {
    std::uint8_t bolt[16], grenade[16];
    for (int i = 0; i < 16; ++i) { bolt[i] = static_cast<std::uint8_t>(i + 1); grenade[i] = static_cast<std::uint8_t>(0x80 + i); }
    // A row split across two overlapped chunks is reported exactly once.
    std::vector<std::uint8_t> memory(100, 0);
    std::memcpy(memory.data() + 40, bolt, 16);
    PatternMatches found;
    const std::size_t chunk = 48, overlap = 15;
    std::uint64_t reported = 0;
    for (std::size_t start = 0; start < memory.size(); start += chunk - overlap) {
        const std::size_t length = std::min(chunk, memory.size() - start);
        scan_chunk(0x1000 + start, memory.data() + start, length, bolt, 16, reported, found);
        reported = 0x1000 + start + length - overlap;
        if (start + length >= memory.size()) break;
    }
    assert(found.count == 1 && found.at[0] == 0x1000 + 40);
    // Two copies are both counted; the adapter then refuses to write anywhere.
    std::memcpy(memory.data() + 70, bolt, 16);
    PatternMatches twice;
    scan_chunk(0x1000, memory.data(), memory.size(), bolt, 16, 0, twice);
    assert(twice.count == 2);
    // Swap decisions only move between the two known images.
    assert(decide_swap(true, bolt, bolt, grenade, 16) == SwapAction::to_grenade);
    assert(decide_swap(true, grenade, bolt, grenade, 16) == SwapAction::none);
    assert(decide_swap(false, grenade, bolt, grenade, 16) == SwapAction::to_bolt);
    assert(decide_swap(false, bolt, bolt, grenade, 16) == SwapAction::none);
    std::uint8_t other[16]{};
    assert(decide_swap(true, other, bolt, grenade, 16) == SwapAction::fault);
    assert(decide_swap(false, other, bolt, grenade, 16) == SwapAction::fault);
    std::cout << "bullet swap tests passed\n";
}
