# Native adapter and renderer

Original C++17/assembly source targeting the supported x64 DSR executable. The cross-compiled Windows binaries remain local. The host continues to own AI, movement, collision, damage and saves.

- `dsr_snapshot.cpp`, `read_only_probe.cpp`: bounded external read-only equipment/ammo diagnostics; no input, injection or memory-write interface.
- `xinput_observer.cpp`: scoped controller/keyboard intent, native hook lifecycle, real shot receipts, magazine/action coordination and explicit trial gates.
- `m9_handling.cpp`, `m9_input.cpp`, `m9_magazine.hpp`: handling and reload state; real native ammo remains authoritative.
- `iw4_view_kick.cpp`: Apache-2.0 IW4L adaptation; see `third_party/` for original credit, changes and full terms.
- `entry_observer.cpp`, `entry_observer.S`: exact-entry hook shim with synthetic argument/register/state/restoration probes.
- `viewmodel_packet.hpp`, `packet_buffer.hpp`: bounded parser for locally converted original MW2 meshes, textures and animation samples.
- `viewmodel_renderer.cpp`: original D3D11 deferred first-person draw; native presentation/visibility contracts are version-specific. Actual latest-package integration remains unqualified.
- `data/*.esp.py`: source definitions compiled into private DSR actions and Asylum bonfire armory.

Build and synthetic validation: `tools/build_native_observer.py`, `tools/build_m9_handling.py`, `tools/native_input_trial.py build`. `tools/check_viewmodel_offline.py` additionally needs the local source-asset packet and static executable snapshot. Its `--console` option runs a shader-only program in the private CrossOver profile and needs applicable execution scope. It creates no game/window/device.

`tools/entry_observer_trial.py` is an original Windows toy under CrossOver, not a source-only test; do not run it as part of a no-execution audit. Owner runtime is orchestrated by `dsr_mw2.owner_test`, with reversible overrides and a marker that blocks agent input. See the root setup and status documents.
