# DSR × MW2 — Claude handoff

Updated 2026-10-06. Branch: `codex/controller-aim-repair`. **Work in progress; controller and repeated Intervention firing are not accepted as fixed.**

## Claude update — 2026-10-06 night (owner sessions after the gun fixes)

Owner-confirmed working: R2/R1 fire while L2-aimed (native action 1 is held by the aim itself and is now excluded from fire intent), M9 and suppressed M9 shooting, Intervention aim/fire, L1 quick-fire routing (gun requests dispatched from native crossbow states 65/67/68), shot audio no longer distorted (3 voices at -6 dB, stock sound bank).

Open issues, with evidence:
- **Interaction (A/E: bonfire, doors, ladders) and unequipping die after the first L2 aim.** In two sessions everything worked before the first aim (bonfire purchase, unequipping the sword) and nothing worked after it, including with the sword equipped. Ruled out: the input-lookup guard (its new hit counter stayed 0), ActionButtonParam (GameParam diff: only EquipParamWeapon/Bullet/CharaInitParam/ShopLineupParam differ), the aim byte at player+0x2a6 (returns to 128), HUD masking (restored every frame), and the ESD idle state (the player is in m1 s0 when presses fail; ladder requests 43/47 are never raised). Next suspects: the third-person body hide in `view_visibility` (it ORs 0x200 into model dirty fields and never clears them itself), and the scoped camera redirect.
- **A diagnostic build broke the launch.** Adding `chr_dump` (read-only hex snapshots of player/model/control at load, aim release and each press) to `xinput_observer.cpp` made private Steam fail process creation: `LaunchApp failed with AppError_46 (0x2DB)`. That source was not committed; the shipped adapter is back to `2e103a99`. Find why before reintroducing it.
- **Leftover trial files.** When the launcher is killed or Steam fails, trial files can remain. `owner_test.recover_interrupted` restores them on the next start, but it refuses when the installed DLL differs from the current build. That case needed a manual retail-XInput restore (backend hash 756cad… verified first).
- **Controller:** XInput returns 1167 (not connected) for the first ~3 minutes of a session, then connects in game. The owner reports that a DualSense connected over Bluetooth before launch is required.
- **Ammo:** both guns use native Standard Bolts. The new character had 6 bolts, so the Intervention could not reload or fire at native total 0. Buy bolts at the MW2 armory.
- **Audio silence:** the Mac's default output device was Mac Studio Speakers (system output: the LG monitor). The game uses the default output at launch.
- **Zero-HP saves soft-lock (owner, 2026-10-06 night):** after the death bug leaves the character at 0 HP, choosing Continue loads a frozen character that cannot move or quit; only a New Game recovers. Unlimited ammo still needs one Standard Bolt in inventory (armory price 1 soul). Snapshot logging (`chr_dump`) loads fine (console probe) and is shipped; the earlier Steam AppError_46 was not the DLL.
- **Intervention aims before its first reload:** cosmetic per the owner.

Owner instruction: do not reopen Dark Souls until the owner says so.

## Claude update — 2026-10-06 evening

Owner session evidence (native logs, sliced at the last two `input_lookup_empty_guard` markers):

- **Death never triggers.** In the session before last, four boss hits took HP 594→491→273→89→0. No death animation played and the character froze. The game then saved at HP 0: the latest session loaded with HP 0 on every sample. Because the custom gun layer only installs when the snapshot reads HP > 0 (`xinput_observer.cpp` frame gate), it never installed in that session.
- **Repeat fire looks fixed natively, but is unverified with the gun layer active.** With the action-priority repair installed, native ammo went 54→45 (eight Intervention decrements, one M9). All of that was at HP 0 with the gun layer absent. The earlier failure (fire requests yielding hold animation 465500 with no decrement) happened while alive.
- **Controller inputs reach DSR while focused:** Cross, D-pad Right weapon swaps (9200000↔9100000), both sticks and both triggers. Full native action response is still owner-unconfirmed.
- **Aim (precision hold) was not held at any of the four hits**, so the forced precision mode is not the cause.

Player ESD structure (`chr/c0000.esd.dcx`):
- Machine 0 is the passive/master machine. Its state 0 enters with `SwitchActiveActionState(1)`, and it alone holds the HP/death checks (`GetHP() < 0`, `GetStateChangeType(117/136)`) and every damage dispatch.
- Machine 1 is the action machine; it has no HP checks. Gun states 9000–9003 exist only in machine 1.
- Machine 0 lacks death checks in states 1, 16, 57–95, 97–103, 105–109, 111–112, 114–215 and 219–224. The zombie state requires machine 0 to have been somewhere without a death check when HP reached 0. Which state is not yet known.
- The builder comment "Native damage/evade interrupt handling remains available during reload" is wrong: `states[70].conditions[:1]` is the chain-attack request group.

New diagnostic (this push):
- `native/include/esd_state_probe.hpp` is a read-only, budgeted (256 reads per XInput call) breadth-first search from the player instance. It finds live EzState records by signature (id plus condition/enter/exit/ongoing counts; all 506 machine/state signatures are unique) and re-reads each holder path.
- Owner sessions log `esd_holder`, `esd_probe`, `esd_state` (every change, with live HP) and `esd_heartbeat` lines to `native-input-v1.jsonl`.
- Windows reads are region-checked with `VirtualQuery`, which skips guard/no-access pages.
- `tools/build_esd_state_table.py` generates `native/include/esd_state_table.hpp` from your installed ESD; that header is git-ignored in the public export. `tools/check_esd_state_probe.py` runs the synthetic-memory tests under ASan/UBSan.
- The launcher's renderer gate no longer treats the Unity CLI/MCP bridge (`~/.unity/bin/unity`) as a renderer; Unity editors still block launch.

Next: after the owner's new-game session, read the `esd_state` trace around the first HP drop and around HP 0. Find the machine-0 state that lacks a death check, then fix the gun-state interaction that strands it there. Do not script HP or deaths.

## Goal and boundaries

Native Dark Souls Remastered, its enemies and bosses, with authentic MW2 (2009) guns, aiming, reloads and custom loadouts. No PTDE substitution, lookalikes, alternate engine or scripted HP damage. The owner rejected the earlier low-quality handgun/crossbow presentation. Current first-person M9 and Intervention assets are authentic local conversions; full MW2 parity is unfinished.

The owner plays. Do not send gameplay input, restart an active session, edit saves, grant ammunition, or change unrelated processes. Work on M3 Ultra, not the laptop or M5. Respect the local AGENTS.md, shared renderer gate, physical private profile and offline launch. Existing approvals do not authorize new unknown executable execution or account/security changes. Owner explicitly approved pushing this source branch and handing off to Claude.

## Repository and live workspace

Public repository: https://github.com/oh-ashen-one/dsr-mw2-crossover, branch `codex/controller-aim-repair`. This is a sanitized source export, with portable runtime configuration and its own Git history. Do not overwrite those portability changes with private files wholesale.

On the existing Studio, the prepared runtime work is in `$HOME/Documents/Codex/2026-10-01/task-2`, private branch `codex/dsr-mw2-native`; source checkpoint `384af68`. It has no Git remote. Private profile: `$HOME/Library/Application Support/DSR-MW2/task-2/profiles/dsr-mw2`. The sibling `dsr-mw2-crossover-public` checkout is older; this push was prepared in the private workspace's ignored `tooling-local/public-handoff` clone. Do not reset any of these checkouts.

Use the existing Studio workspace for runtime debugging; do not build a second profile or copy account state. Its local HANDOFF.md retains detailed history and evidence paths. Public clones require their own owned games, extracted assets and generated receipts; source alone is not an immediately playable package.

## Current failures and latest changes

1. **Controller:** owner repeatedly reports only L2 working; PS button opens Steam. Native logs received real face-button/stick values with foreground true, but normal DSR actions were absent. The custom gun code reads triggers directly, so L2 working does not establish native controls. Earlier renamed retail XInput backend was replaced by installed CrossOver system32/xinput1_4 forwarding. Private WineBus DisableHidraw remains enabled. Private Steam excludes observed DualSense 054c:0ce6 at the verified root `InstallConfigStore/controller_blacklist`; runtime logs confirm exclusion. Overlay/Guide-focus booleans alone did not solve it. A second shared Steam client also received Guide presses; owner approved closing it and then closed everything themselves. Do not repeat ineffective nested Steam setting paths or call this resolved.
2. **Intervention fires once:** last failing session consumed native ammo 55→54 and left virtual magazine4. Subsequent request37 pulses produced aim465500, no further decrement. Not an empty magazine. Found a concrete ESD priority defect: idle checked persistent aim before transient fire/reload. Now checks fire9000, reload9001, emptyReload9002, then hold9003. Full decoded ESD equality after undoing only the permutation proves unrelated action data unchanged. `tools/repair_action_priority.py` repairs the existing local package; both builders preserve the correction. This candidate has not yet been accepted by the owner. Do not assume an unverified chamber/reload explanation or fake ammo decrements.
3. **Crashes/freezes:** earlier DXVK sessions logged swapchain recreation and GPU allocation failures. Candidate uses installed D3DMetal per launch. Separate native null-read RVA54c4c9 persisted after changing renderer. Original guard at54c4c4 only bypasses a fully zero three-pointer lookup vector via existing54c618 completion; other paths retain original instructions/flags. Exact signatures and standalone execution fixture pass, and installation was logged in-game. Guard effectiveness against every crash is unproven; the initiating empty lookup cause remains unknown. Diagnostic handler records the first native access violation and continues exception search.
4. **Window:** original helper adds resize borders, startup fit and foreground-only Ctrl+Option+1/2/3 size presets; Ctrl+Option+M minimizes. Owner previously reported capture/resize problems. Actual border dragging remains unaccepted. WindowMode semantics have conflicting historical notes; do not assume the INI value itself fixes loading.

## Last runtime checkpoint

At publication preparation, DSR PID4752/window6241 and owner launcherPID1313 were still active. Recheck live ownership; PIDs are historical, not permission to control a process. Last launch receipt: `tooling-local/launch/latest-owner-request.json`. Log: `tooling-local/launch/action-priority-repair-20261006T225621Z.log`, plus `owner-test.log` and appended `m9-test.log`.

The controller console probe passed before startup; the first native slot0 poll also succeeded. Shared Steam was closed. Last captured view was a native loading screen. No latest-package gameplay acceptance was obtained. Original M9/stock bank hashes remained unchanged; active bank was `validation`, containing the owner's current test progress. Normal launcher exit restores temporary DLL/assets/audio and save-bank selection. Never rebuild installed source receipts or overwrite trial files during an active session.

Native logs live under the private bottle's `drive_c/Tools/DSR-MW2`: `native-input-v1.jsonl`, `native-gun-trial-v1.jsonl`, `native-crash-v1.jsonl` and viewmodel logs. Verify filenames locally. Logs append across host boots: **do not filter by a global minimum uptime**. Slice from the last `frame_hook_installed` / `input_lookup_empty_guard` session marker, then correlate requests, animations and authoritative ammo receipts.

## Verification and limitations

This export passes 219 Python tests without retail data, strict native adapter compilation/import checks, and the 281-file publication audit. No compiled binary was executed during export. Private preparation passed reversible installation/restore and 213 tests. Original native adapter compilation and fixture evidence are described in the local history; never substitute compilation for owner gameplay confirmation.

Intervention weapon9200000/model1407 has a five-round magazine, .916s minimum shot cycle, .4s ADS-in and authored reload timing. Native DSR damage is explicitly adapted to350. It is sold for one soul at the first Asylum bonfire MW2 armory. M9 remains available. Equip in the right hand; one weapon held with both hands is supported intent, not two guns equipped. Native collision/ammo remain authoritative. Third-person crossbow behavior, simplified materials, reload/bolt foley, complete loadouts and repeatable boss/death/reset/performance acceptance remain unfinished.

## Next steps

1. Read local instructions and inspect current owner session/receipts before touching runtime files. Let the owner finish; no agent gameplay.
2. Obtain owner result for latest aim-priority repair and controller-connected startup. Inspect only that session's logs. Repeated real ammo decrements and native firing animation must confirm shots; request37 alone is insufficient.
3. If native controls still fail despite XInput buttons, investigate DSR binding/initialization and controller ownership downstream of XInput; do not repeat pairing advice, guessed Steam keys or unsupported remapping.
4. If firing still fails, trace ESD action transitions/acknowledgement and native ammo events. Keep native hit/miss/terrain/boss damage, interrupted reload and death invariants.
5. Update this handoff and test evidence, then fast-forward this same public branch with source-only changes. Do not publish private history or local assets.

## Source checks and entry points

```sh
python3 -B -m unittest discover -s tests
python3 tools/check_public_release.py
git diff --check
```

Read `docs/SETUP.md`, `docs/BUILD.md`, `SKILL.md` before fresh setup. Existing Studio launcher is `Play DSR + MW2.command`; `python3 -B -m dsr_mw2.owner_test --prepare` is offline install/check/restore and requires the private profile closed. Do not launch from an unrelated CrossOver shortcut: it selects different data/save paths.

Retail files, converted models/animations/audio, binaries, build receipts, captures, logs, saves and account state intentionally stay local. No new secrets are needed for this handoff. Credits/licenses remain in CREDITS.md and NOTICE.

## Resume prompt

Continue native DSR × MW2 on the existing M3 Studio in `$HOME/Documents/Codex/2026-10-01/task-2`, branch `codex/dsr-mw2-native`. Read its AGENTS.md and HANDOFF.md plus the current public HANDOFF.md on `oh-ashen-one/dsr-mw2-crossover`, branch `codex/controller-aim-repair`. Fix the remaining PS5 input and Intervention repeat-fire failures. Preserve the active owner session, saves and local assets; the owner performs gameplay. Keep the portable public export separate and push source-only updates to that same GitHub branch.
