# DSR × MW2 — Claude handoff

Updated 2026-10-06. Branch: `codex/controller-aim-repair`. **Work in progress; controller and repeated Intervention firing are not accepted as fixed.**

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
