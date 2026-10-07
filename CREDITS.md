# Credits and licenses

Project design, integration, original source and release: **[oh-ashen-one](https://github.com/oh-ashen-one)** and contributors, with AI-assisted engineering. Original source is GPL-3.0-only unless specifically identified below. Full texts are included; do not replace them with a generic MIT license.

## Included third-party material

| Work | Author and source | Use and terms |
| --- | --- | --- |
| OpenAssetTools compatibility patches | [Laupetin and contributors](https://github.com/Laupetin/OpenAssetTools), v0.33.0 / `7d027e8f89118196713e955b0e11f8404149c54d` | Original local fixes plus upstream patch context; GPL-3.0. [License](tools/OAT-LICENSE-GPL-3.0.txt). Patches cover macOS compilation and the measured native64 IW4 layout. |
| IW4L recoil adaptation | [vladtrc / IW4L](https://github.com/vladtrc/iw4L), inspected through [this fork](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/f608f85e407ff1b7689d54a9aafdd16e95711ac4) | `crates/weapon_iw4/src/kick.rs` adapted to bounded M9-only C++ in `native/src/iw4_view_kick.cpp`. Apache-2.0. [Notice and modifications](native/third_party/IW4L-NOTICE.txt), [full license](native/third_party/IW4L-LICENSE-2.0.txt). No other fork components are included. |

## External build dependencies

These are fetched separately into local tool environments, not redistributed as binaries or vendored source in this release.

| Dependency | Pinned revision / version | Credit and license |
| --- | --- | --- |
| [Soulstruct](https://github.com/Grimrukh/soulstruct) | `12b69189a2ccebbc623a1b6565be89a18d6c9958` (2.6.0) | Scott Mooney / Grimrukh and contributors; GPL-3.0-or-later. FLVER, binders, params, TPF, ESD and other DSR formats. `dsr_mw2/esd_links.py` adapts Soulstruct's `ESD.to_writer` so condition links stay within each state machine (fixes cross-machine links when machines share state IDs). |
| [Soulstruct-Havok](https://github.com/Grimrukh/soulstruct-havok) | `bf2d41fc83de4a43bd3ed3df8605741f143cad2c` (1.5.0) | Scott Mooney / Grimrukh and contributors; GPL-3.0-or-later. Havok parsing and original Python spline conversion path. |
| [SciPy](https://scipy.org/) | 1.18.0 | SciPy developers; BSD-3-Clause and bundled notices. |
| [NumPy](https://numpy.org/) | See requirements file | NumPy developers; BSD-3-Clause. |
| [Pillow](https://python-pillow.org/) | 12.3.0 | Jeffrey 'Alex' Clark and Pillow contributors; Fredrik Lundh and PIL contributors. MIT-CMU and included notices. Local texture decoding and CPU previews. |
| [Constrata](https://github.com/Grimrukh/constrata) and Python support packages | See requirements file | Respective authors and package licenses. Installed separately; retain their notices in any redistributed environment. |
| [LLVM](https://llvm.org/), [MinGW-w64](https://www.mingw-w64.org/), [Premake](https://premake.github.io/) | Locally reviewed toolchains | Their respective authors/licenses. Source builds and Windows cross-compilation. |
| [FFmpeg](https://ffmpeg.org/) | Trusted local installation | FFmpeg contributors; license depends on the selected build/configuration. Used for local shot-audio encoding, not bundled. |

OpenAssetTools' own dependencies retain their upstream licenses. The project does not distribute their compiled output, Microsoft runtime libraries, Havok SDK tooling, CompressAnim, CrossOver or Steam.

## Research and interface references

These projects informed investigation or architecture. They are **not bundled adapters** and their availability is not proof that this crossover works. No implementation from the following references is copied into this release:

- [JKAnderson/DSR-Gadget](https://github.com/JKAnderson/DSR-Gadget): player structure layout (ChrMapData / ChrPosData) reviewed for read-only position qualification; no code copied.
- [Grimrukh/Firelink](https://github.com/Grimrukh/Firelink), revision `54c00cdbfe875af4f4270f013f714f45e2e9a284`: native interface research.
- [metal-crow/Dark-Souls-1-Overhaul](https://github.com/metal-crow/Dark-Souls-1-Overhaul), revision `2a3d8cbe2acee663bef03c7be4f968dbb68f951f`: interface behavior reference; AGPL code was not copied.
- [lud-berthe/Dark-Souls-Remastered-Gyro-aim-mod](https://github.com/lud-berthe/Dark-Souls-Remastered-Gyro-aim-mod), revision `d451f3f6403fa4ee24b9fc0868280893fd2e17df`: camera/visibility investigation, independently checked against the supported image.
- [Meowmaritus/DSAnimStudio](https://github.com/Meowmaritus/DSAnimStudio), revision `f1bff06cd422de991b0a0fa8a2da81db43417318`: bone mapping, inverse-bind and attachment convention references.
- [rehan-remade/universal-modder](https://github.com/rehan-remade/universal-modder): evidence-driven workflow and separate first-person presentation architectural lead.
- [trevaintdead/ai-game-modding-guides](https://github.com/trevaintdead/ai-game-modding-guides): modding and handoff methodology.
- [morluto/rea](https://github.com/morluto/rea), [bethington/ghidra-mcp](https://github.com/bethington/ghidra-mcp), [HexRaysSA/ida-mcp](https://github.com/HexRaysSA/ida-mcp): reviewed static-analysis options, not required or executed by this package.
- [icsharpcode/ILSpy](https://github.com/icsharpcode/ILSpy), [SamboyCoding/Cpp2IL](https://github.com/SamboyCoding/Cpp2IL), [boykopovar/AnyPS5](https://github.com/boykopovar/AnyPS5), [yuriolive/PortPS5](https://github.com/yuriolive/PortPS5): reviewed user-supplied resources; their managed/Unity/PS5 targets do not supply a native DSR PC integration or DualSense fix.
- [Scobalula/Greyhound](https://github.com/Scobalula/Greyhound), [AltimorTASDK/ModEngine2](https://github.com/AltimorTASDK/ModEngine2): investigated alternatives. Neither is needed for the current source-built native file/XInput route.

## Games and platform

**Dark Souls Remastered:** FromSoftware, QLOC and Bandai Namco Entertainment. **Call of Duty: Modern Warfare 2 (2009):** Infinity Ward and Activision. Authentic local assets remain the property of their rights holders and are excluded from Git and releases.

**CrossOver:** CodeWeavers. **Steam:** Valve. **DualSense / PlayStation:** Sony Interactive Entertainment. Names identify compatibility targets and ownership; they do not imply affiliation, endorsement or redistributed licenses.
