// Synthetic-memory tests for the read-only ESD state probe. No game data is read.
#include "esd_state_table.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <memory>
#include <vector>
using namespace dsr_mw2;

namespace {
struct Memory : Reader {
    struct Region { Address at; std::vector<std::uint8_t> data; };
    std::vector<Region> regions;
    mutable std::size_t reads = 0;
    void add(Address at, std::size_t size) { regions.push_back({at, std::vector<std::uint8_t>(size)}); }
    bool read(Address at, void* out, std::size_t size) const override {
        ++reads;
        for (auto& r : regions) if (at >= r.at && at - r.at + size <= r.data.size()) {
            std::memcpy(out, r.data.data() + (at - r.at), size); return true;
        }
        return false;
    }
    template<class T> void put(Address at, T value) {
        for (auto& r : regions) if (at >= r.at && at - r.at + sizeof(T) <= r.data.size()) {
            std::memcpy(r.data.data() + (at - r.at), &value, sizeof(T)); return;
        }
        assert(false);
    }
    void record(Address at, std::int32_t machine, std::int32_t state) {
        for (const auto& s : esd_state_table) if (s.machine == machine && s.state == state) {
            const std::uint64_t f[9] = {std::uint64_t(state), 0x100, std::uint64_t(s.conditions), 0x200, std::uint64_t(s.enter),
                                        0x300, std::uint64_t(s.exit), s.ongoing ? 0x400u : 0u, std::uint64_t(s.ongoing)};
            for (unsigned i = 0; i < 9; ++i) put(at + 8u * i, f[i]);
            return;
        }
        assert(false);
    }
};

constexpr Address root = 0x300000000, a = 0x400000000, b = 0x410000000, decoy = 0x420000000;
constexpr Address esd = 0x500000000, m1_idle = esd + 0x2000, m0_idle = esd + 0x3000, m1_hold = esd + 0x4000;

std::unique_ptr<Memory> world() {
    auto m = std::make_unique<Memory>();
    m->add(root, 0x1000); m->add(a, 0x400); m->add(b, 0x400); m->add(decoy, 0x400); m->add(esd, 0x70000);
    m->record(m1_idle, 1, 0); m->record(m0_idle, 0, 0); m->record(m1_hold, 1, 9003);
    m->put(root + 0x68, a); m->put(a + 0x30, b);
    m->put(b + 0x18, m1_idle); m->put(b + 0x20, m0_idle);
    m->put(root + 0x80, decoy);                       // decoy object: ints, floats, dangling pointers
    m->put(decoy + 0x8, std::uint64_t(0x7777777777770));
    m->put(decoy + 0x10, std::uint64_t(42)); m->put(decoy + 0x18, 1.5f);
    m->put(root + 0x90, esd + 0x1000);                // pointer into the ESD buffer (condition data)
    m->put(esd + 0x1000, m1_hold);                    // internal next-state pointer: not a live holder
    m->put(root + 0x3e8, std::uint32_t(0));           // HP field: plain data
    return m;
}

void found_by_path() {
    auto m = world();
    auto probe = std::make_unique<EsdStateProbe>(esd_state_table, std::size(esd_state_table), esd_state_span);
    probe->reset(root);
    while (!probe->finished()) probe->step(*m, 1u << 20);
    assert(probe->holders() == 2);
    assert(probe->internal() == 1);
    bool saw_m1 = false, saw_m0 = false;
    for (std::size_t i = 0; i < probe->holders(); ++i) {
        const auto& h = probe->holder(i);
        assert(h.length == 3 && h.path[0] == 0x68 && h.path[1] == 0x30);
        if (h.path[2] == 0x18) { assert((h.last == EsdStateHit{1, 0})); saw_m1 = true; }
        if (h.path[2] == 0x20) { assert((h.last == EsdStateHit{0, 0})); saw_m0 = true; }
        assert(probe->resolve(*m, i) == h.last);
    }
    assert(saw_m1 && saw_m0);
    // Live transition: machine 1 enters the scoped hold; re-reading the path reports it.
    m->put(b + 0x18, m1_hold);
    for (std::size_t i = 0; i < probe->holders(); ++i)
        if (probe->holder(i).path[2] == 0x18) assert((probe->resolve(*m, i) == EsdStateHit{1, 9003}));
    // Broken chain is unreadable, not a fabricated state.
    m->put(a + 0x30, std::uint64_t(0));
    for (std::size_t i = 0; i < probe->holders(); ++i) assert(probe->resolve(*m, i).state == -1);
}

void small_budget_matches() {
    auto m = world();
    auto probe = std::make_unique<EsdStateProbe>(esd_state_table, std::size(esd_state_table), esd_state_span);
    probe->reset(root);
    std::size_t calls = 0;
    while (!probe->finished()) {
        const std::size_t before = m->reads;
        probe->step(*m, 3);
        assert(m->reads - before <= 3 + 2);              // window fallbacks may add two reads
        ++calls;
    }
    assert(calls > 2 && probe->holders() == 2 && probe->internal() == 1);
}

void rejects_lookalikes() {
    std::uint8_t bytes[esd_state_record_size]{};
    std::uint64_t f[9] = {0, 0, 36, 0, 3, 0, 6, 0, 0};    // counts without offsets
    std::memcpy(bytes, f, sizeof(f));
    assert(match_state_record(bytes, esd_state_table, std::size(esd_state_table)).state == -1);
    f[0] = 123456789; f[1] = 1; f[3] = 1; f[5] = 1;
    std::memcpy(bytes, f, sizeof(f));
    assert(match_state_record(bytes, esd_state_table, std::size(esd_state_table)).state == -1);
}

void null_root() {
    auto m = world();
    auto probe = std::make_unique<EsdStateProbe>(esd_state_table, std::size(esd_state_table), esd_state_span);
    probe->reset(0);
    assert(probe->finished() && probe->holders() == 0);
    probe->step(*m, 100);
    assert(probe->holders() == 0);
}
} // namespace

int main() {
    found_by_path(); small_budget_matches(); rejects_lookalikes(); null_root();
    std::cout << "esd state probe tests passed\n";
}
