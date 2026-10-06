# Release status: 0.1.0 source preview

This release preserves the current M9 source build. It is not a claim of a completed full-MW2 conversion or reproducibility on every retail revision. The public export was prepared without launching either game. New users must regenerate all private assets and receipts.

| Gate | Evidence / remaining work |
| --- | --- |
| Authentic MW2 assets | Local extraction and source identity checks covered M9 world/view models, hands, original materials, animation clips and shot audio. No retail outputs are included here. |
| Native DSR baseline | Earlier private baseline/gameplay operated on M3 Ultra through CrossOver; exact game image is pinned. Other machines remain unqualified. |
| Save/profile isolation | Private physical Documents, separate stock/M9/disposable banks, hash checks, process ownership and reversible file installation implemented. A new profile must independently pass these checks. |
| Projectile/ammo route | Genuine native shot/ammo receipts observed; collision/damage delegated to DSR. Full hit/miss/terrain/boss acceptance has not been completed. No scripted HP decrement is used. |
| Magazine and reload | Earlier disposable native tests observed loaded-ammo progression, empty reload, native action completion and moving fire/reload. Virtual magazine uses real native bolt totals. |
| Aim/recoil/audio | Native precision-aim ownership, confirmed-shot recoil and original M9 shot audio observed in earlier tests. These are bounded findings, not full MW2 behavior parity. |
| Armory | Earlier native test purchased the suppressor variant, equipped it in either right-hand slot and confirmed native save persistence. Appearance only: no distinct suppressed audio/range. |
| New first-person renderer | Original D3D11 source compiles. Source-asset packet, static hook contracts and HLSL stages were checked offline. Actual rendering/state restoration in DSR remains unverified. |
| Physical PS5 controller | Private WineBus correction and XInput mapping prepared; physical button response remains unverified. |
| Window management | Original external helper enables resize borders and foreground-only size/minimize shortcuts. A hidden-window CrossOver fixture passed without opening DSR. Actual DSR resizing and shortcuts remain unverified. |
| Boss/death/reset/performance | Full repeatable boss encounter, death/restart/defeat, long-session behavior and performance remain unverified. |

The earlier world-model prototype was rejected for crossbow-like handling and poor presentation. Later native handling work and the new first-person candidate address parts of that feedback; this release does not erase the remaining acceptance gates.

The first-person packet contains 76 bones, 6,820 triangles and seven clips in the measured source layout. Rendering uses a simplified diffuse/lighting path, not the complete IW4 material renderer. Native third-person representation remains outside owned aim. Shared native crossbow animation/bullet/audio routes still warrant further isolation. Other crossbows should not be assumed unaffected.

The explicit owner-test handling lifetime is two hours. It is a bounded development session, not a forced two-hour game timer. Quit normally and let the launcher finish restoration before starting another session. Interrupted sessions preserve receipts and require task-local recovery rather than blindly overwriting files.

Public checks and their exact results are recorded in [SOURCE-VALIDATION.json](SOURCE-VALIDATION.json). Private captures, account identifiers and save fingerprints are excluded. No screenshot or video is presented as evidence for the untested first-person integration.
