// Original, bounded controller diagnostic. No game, input synthesis, vibration,
// process attachment, registry writes or device configuration.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xinput.h>
#include <cstdio>
#include <cstring>

template<typename T> T procedure(HMODULE library, const char* name) {
    const auto address = GetProcAddress(library, name);
    T result{};
    static_assert(sizeof(result) == sizeof(address));
    std::memcpy(&result, &address, sizeof(result));
    return result;
}

int main(int argc, char** argv) {
    if (argc != 2 || (std::strcmp(argv[1], "game") && std::strcmp(argv[1], "system"))) return 64;
    const bool game = !std::strcmp(argv[1], "game");
    const auto module = LoadLibraryW(game ? L"C:\\Games\\DSR-MW2\\xinput1_3.dll"
                                         : L"C:\\windows\\system32\\xinput1_3.dll");
    if (!module) {
        std::printf("{\"error\":\"load_failed\",\"code\":%lu}\n", GetLastError());
        return 1;
    }
    const auto state = procedure<DWORD (WINAPI*)(DWORD, XINPUT_STATE*)>(module, "XInputGetState");
    const auto caps = procedure<DWORD (WINAPI*)(DWORD, DWORD, XINPUT_CAPABILITIES*)>(module, "XInputGetCapabilities");
    if (!state || !caps) return 2;
    // Allow the existing Wine device service to enumerate hardware. Ten samples,
    // five seconds maximum; no button identities or user input history logged.
    for (unsigned sample = 0; sample < 10; ++sample) {
        for (DWORD slot = 0; slot < XUSER_MAX_COUNT; ++slot) {
            XINPUT_STATE value{};
            XINPUT_CAPABILITIES capability{};
            const DWORD status = state(slot, &value);
            const DWORD cap_status = caps(slot, 0, &capability);
            std::printf("{\"route\":\"%s\",\"sample\":%u,\"slot\":%lu,\"state_status\":%lu,"
                        "\"caps_status\":%lu,\"type\":%u,\"subtype\":%u,\"packet\":%lu}\n",
                        argv[1], sample, slot, status, cap_status, unsigned(capability.Type),
                        unsigned(capability.SubType), value.dwPacketNumber);
        }
        std::fflush(stdout);
        Sleep(500);
    }
    FreeLibrary(module);
    return 0;
}
