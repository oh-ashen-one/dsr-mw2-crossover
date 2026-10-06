// Inactive diagnostic DLL. Nothing is started or hooked from DllMain.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <array>
#include <cstring>
#include "dsr_snapshot.hpp"

namespace {
INIT_ONCE compatibility_once = INIT_ONCE_STATIC_INIT;
bool compatible_image = false;
struct LocalReader final : dsr_mw2::Reader {
    bool read(dsr_mw2::Address at, void* out, std::size_t bytes) const override {
        SIZE_T actual = 0;
        return ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<const void*>(at), out, bytes, &actual) && actual == bytes;
    }
};

bool exact_private_image() {
    wchar_t path[1024]{};
    DWORD length = GetModuleFileNameW(nullptr, path, 1024);
    if (!length || length >= 1024 || _wcsicmp(path, L"C:\\Games\\DSR-MW2\\DarkSoulsRemastered.exe")) return false;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    bool ok = BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0;
    if (ok) ok = BCryptCreateHash(alg, &hash, nullptr, 0, nullptr, 0, 0) >= 0;
    std::array<UCHAR, 65536> block{};
    DWORD count{};
    while (ok) {
        if (!ReadFile(file, block.data(), static_cast<DWORD>(block.size()), &count, nullptr)) { ok = false; break; }
        if (!count) break;
        ok = BCryptHashData(hash, block.data(), count, 0) >= 0;
    }
    std::array<UCHAR, 32> digest{};
    if (ok) ok = BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    const std::array<UCHAR, 32> expected{0xa4,0x5a,0xaa,0x36,0xdd,0x2f,0x6c,0xc1,0x51,0x67,0x0a,0x63,0x9e,0xa5,0x54,0x70,
        0x43,0xcf,0x38,0xea,0x79,0xff,0x41,0x78,0xb9,0x63,0xc6,0xed,0x71,0xf9,0x8d,0x7b};
    if (hash) BCryptDestroyHash(hash);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    CloseHandle(file);
    if (!ok || digest != expected) return false;
    LocalReader reader;
    const auto base = reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr));
    const std::array<unsigned char, 7> world{0x48,0x8b,0x05,0x23,0x38,0x4b,0x01};
    const std::array<unsigned char, 7> game{0x48,0x8b,0x05,0x39,0x18,0x53,0x01};
    std::array<unsigned char, 7> found{};
    return reader.get(base, 0x7c4626, found) && found == world && reader.get(base, 0x758cf0, found) && found == game;
}
BOOL CALLBACK check_once(PINIT_ONCE, PVOID, PVOID*) {
    compatible_image = exact_private_image();
    return TRUE;
}
}

// Call on the game's owning thread after load. No process enumeration, remote
// attachment, input generation, memory patching, network, or inventory writes.
extern "C" __declspec(dllexport) std::uint32_t DsrMw2ReadSnapshot(dsr_mw2::Snapshot* out, std::uint32_t size) {
    if (!out || size != sizeof(*out)) return static_cast<std::uint32_t>(dsr_mw2::ReadStatus::invalid);
    *out = {};
    if (!InitOnceExecuteOnce(&compatibility_once, check_once, nullptr, nullptr) || !compatible_image)
        return static_cast<std::uint32_t>(dsr_mw2::ReadStatus::invalid);
    LocalReader reader;
    return static_cast<std::uint32_t>(dsr_mw2::observe(reader, reinterpret_cast<dsr_mw2::Address>(GetModuleHandleW(nullptr)), *out));
}

extern "C" __declspec(dllexport) std::uint32_t DsrMw2SnapshotSize() { return static_cast<std::uint32_t>(sizeof(dsr_mw2::Snapshot)); }

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) { return TRUE; }
