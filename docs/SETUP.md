# Local setup runbook

This is an agent-operated source pipeline for a specific native DSR build. It has not been independently reproduced from a fresh public clone with different retail files. Preserve the checks and report a concrete incompatibility if you encounter one. Do not promise a one-click cross-platform install.

## 1. Source environment

Use a separate checkout/branch. The game launcher targets Apple M3 Ultra macOS with CrossOver; the Python source tests do not need either game. The native launcher deliberately keeps its M3 Ultra gate. Porting other machines is separate work, not a memory-capacity setting.

Required existing tools: Python 3.13+ (development used 3.14), Git, Apple clang++, MinGW-w64 `x86_64-w64-mingw32-g++` and `objdump`, a locally reviewed Premake 5 for building OAT, and FFmpeg for audio. Current native build scripts use `/usr/bin/clang++` and `/opt/homebrew/bin/` compiler/FFmpeg paths. Review and configure those source paths if your trusted installation differs. Do not run downloaded installers automatically.

```sh
python3 -m pip install --only-binary=:all: -r requirements-tests.txt
python3 -B -m unittest discover -s tests -v
python3 tools/check_public_release.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-offline-tools.txt
```

Dependency installation executes upstream packaging code. Review the pinned sources and apply the current user's execution scope first. The requirements capture the development versions, not an unbounded upgrade request. If a pinned dependency is unavailable, stop and report it; do not silently substitute a latest version.

Clone the pinned Soulstruct source to `tooling-local/sources/soulstruct`, checkout `12b69189a2ccebbc623a1b6565be89a18d6c9958`, then run:

```sh
PYTHONPATH=. .venv/bin/python -B tools/prepare_soulstruct.py --source tooling-local/sources/soulstruct
```

This installs the supplied local-data-path adapter in this checkout's `.venv`, preserving its receipt under `tooling-local/`. It prevents Soulstruct from using the host's default application-data folder. Use `.venv/bin/python` with `PYTHONPATH=.` for asset conversions.

Clone [Soulstruct-Havok](https://github.com/Grimrukh/soulstruct-havok) at `bf2d41fc83de4a43bd3ed3df8605741f143cad2c` into `tooling-local/sources/soulstruct-havok-review`. Keep tracked source unmodified. Install SciPy **1.18.0** into `tooling-local/havok-python-deps` with the `.venv` interpreter and `pip --target`; preserve its dependency records. `tools/havok_offline_trial.py` adds the namespace source directly and never invokes bundled Havok helper executables. Do not run `CompressAnim.exe`.

## 2. Local configuration

Discover the actual installed game and CrossOver paths read-only. Supply the user's own MW2 directory, containing `main/` and `zone/english/common_mp.ff`:

```sh
python3 tools/configure_public.py \
  --mw2-root '/path/to/owned/Call of Duty Modern Warfare 2' \
  --crossover-app '/Applications/CrossOver.app' \
  --allow-offline-conversion --allow-owner-test
```

Use those permission flags only when they match the user's request. They create local records, not a new authorization. `allow_agent_gameplay` stays false. The resulting `local-config.json` is ignored and must not be shared.

If your machine already has a shared renderer coordinator, supply `--gpu-dir /path/to/coordinator`. It must implement `bin/gpu_slot.py perf --label NAME --timeout SECONDS -- COMMAND` and `locks/perf.lock`; it must retain the lock throughout child lifetime and honor `PAUSED`. Do not create a second competing lock. Without that option, setup installs the original fallback helper inside `tooling-local/gpu`; this coordinates only cooperating launches and the launcher additionally refuses known active game/renderer processes.

Configuration does not create a bottle, sign in, extract assets or open a game.

## 3. Fresh, isolated CrossOver profile

Use the installed CrossOver's supported local tools to create a **new physical 64-bit profile named `dsr-mw2` at `profiles/dsr-mw2`**. Do not clone an account-bearing Steam bottle. The wrapper selects its parent through `CX_BOTTLE_PATH`. Paths must resolve physically to this checkout and must not be hardlinked to another game installation.

Install/initialize Steam only in this new profile if needed. Let the owner authenticate privately; never copy `loginusers.vdf`, `userdata`, cookies, `ssfn` files, account registry state or saved credentials. Never ask the owner to send a password/code into chat. Existing sign-in in a different bottle is not proof of private-profile sign-in.

Before gameplay, inspect and isolate Windows paths:

- All `drive_c/users/crossover/{Documents,Desktop,Downloads,Pictures,Music,Videos,AppData}` must be physical directories within this bottle.
- `user.reg` must select `C:\users\crossover\Documents` for the Shell Folders `Personal` value and `%USERPROFILE%\Documents` for User Shell Folders. Preserve unrelated registry values.
- `dosdevices/c:` must point to this bottle's `drive_c`. Remove external drive mappings **from this new private bottle only**. Reserve every other drive letter as a regular `letter::` file containing `DSR-MW2: reserved; no host device\n`, exactly as `profile.RESERVATION` defines; no external symlinks remain.
- The private `dosdevices` and `drive_c/users/crossover` parent folders require macOS `UF_IMMUTABLE` protection. Apply protection only after their correct contents exist. Do not lock shared or host directories.
- Physically resolve `Documents/NBGI`, inspect for redirects, and perform a disposable Windows Documents write/read/delete test in the private profile. This confirms where Wine actually writes. Never use an existing save as the test file.
- Run `dsr_mw2.profile.guard(bottle_path())`; all reported blockers must be resolved without weakening it. Runtime console checks require applicable local execution authorization.

Changes above affect only a newly owned bottle. If a path leads outside it, preserve the existing target and correct the local link; do not modify the target. CrossOver can recreate host mappings during initialization, so recheck after every startup.

## 4. Private game copies and Steam routing

Create physical copies of the owned DSR install under:

```text
profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/  # preserved baseline
profiles/dsr-mw2/drive_c/Games/DSR-MW2/                # mutable candidate
```

Keep original installs and saves read-only. No hardlinks. Keep both copies' unmodified `xinput1_3.dll` and other retail runtimes; no external ModEngine2, shader overhaul or Greyhound executable is needed. The current adapter is built from this repository.

Required executable SHA-256:

```text
a45aaa36dd2f6cc151670a639ea5547043cf38ea79ff4178b963c6ed71f98d7b
```

`install_private.STOCK_HASHES`, `native_runtime.RUNTIME_HASHES` and `install_audio.STOCK` pin additional files. Reject a mismatch before patching. Make a private Steam `steamapps/common/DARK SOULS REMASTERED` alias to the private baseline. Use `steam_manifest.installed_dsr_manifest` to derive an account-free installation manifest from owned app 570940 metadata. `steam_mode.configure` controls only the private alias and manifest for subsequent launches. Do not change the source Steam library/downloads.

The hash-checked stock route and private Steam sign-in can require an entitlement check. This is distinct from modified gameplay, which always uses `tools/dsr-offline.sb` to deny IP networking. Never allow modified saves online or disable account/security controls to get past an error. No source-only publication step needs a game launch.

## 5. Owned assets, builds and separate saves

Follow [BUILD.md](BUILD.md). All converted files stay under ignored `converted/`, `tooling-local/` and the private bottle. Do not substitute a downloaded asset pack or copy this project's author's outputs.

After the guarded profile is closed, initialize private save banks using `save_banks.select(bottle_path(), 'm9')`; this preserves the initial private stock bank and creates an empty M9 bank. Then `validation_session.prepare(bottle_path())` creates a separate disposable bank. These functions preserve save bytes; no equipment/progress edits are supported. A fresh bank starts a fresh character. Do not fabricate the first-bonfire progress described in historical observations.

Use the supplied modules rather than manually renaming folders. They acquire the private session lock, refuse active processes and journal swaps. Interrupted operations preserve their journal and require explicit task-local recovery.

## 6. Offline preparation and owner handoff

After every required output exists and the native source is rebuilt:

```sh
python3 -B -m dsr_mw2.doctor
python3 -B -m dsr_mw2.owner_test --prepare
```

The second command stages the local viewmodel/probe, applies the private WineBus correction, temporarily installs the action/armory/audio/XInput package, checks it, restores the baseline and verifies saved-bank fingerprints. It does not start DSR. Other active renderers may prevent later launching; never close them or clear their coordinator pause.

Leave `Play DSR + MW2.command` for the owner to open. It installs the prepared temporary trial, launches the private offline game under the renderer gate, marks the session owner-only and restores files after all private processes exit. Quit normally and allow restoration to finish. If interrupted, preserve receipts and use their matching restore routines after verifying process ownership; never blindly delete a receipt to bypass a guard.

Report latest first-person rendering and physical controller input as unverified until actual results exist. The acceptance sequence is: input, correct gun/hands, aim/fire/ammo/reload, native miss/terrain/enemy/boss collision, equipment changes, player death, boss defeat, restart and performance. Tests and shader compilation alone do not prove these.
