# Owned-asset build map

Run from the repository root after [SETUP](SETUP.md). This documents the current dependency chain and retained authoring tools, not a claim that every MW2 retail layout is supported. Commands execute conversion code; review it under your current local authorization first. Use `PYTHONPATH=.` and `.venv/bin/python -B` for Python conversions, with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1` for Havok work.

## Extractor and exact input layout

Clone [OpenAssetTools v0.33.0](https://github.com/Laupetin/OpenAssetTools/tree/7d027e8f89118196713e955b0e11f8404149c54d), including its pinned submodules, into `tooling-local/sources/OpenAssetTools-v0.33.0`. Checkout commit `7d027e8f89118196713e955b0e11f8404149c54d`. Apply **only** `tools/oat-mw2-native64.patch`, using `git apply --unidiff-zero` from that source checkout. This patch already includes the earlier macOS changes.

Patch SHA-256: `fbc898d1320f418e8d9191f0b6a5a14118691bc32882eced466b6985e84ec241`. Build using a reviewed local Premake/Apple compiler toolchain and the upstream make targets, generating ZoneCode headers after applying the patch. The original build used the `debug_x64` configuration with native 64-bit host pointers. Upstream `generate.sh` can download a Linux Premake binary; **do not run that automatic download path on macOS**. Generate with your local Premake and adapt generated host flags to your native macOS compiler, not to a 32-bit IW4 reader. Keep build logs and tool versions local.

Place the resulting native **source-built** `Unlinker` at `tooling-local/OpenAssetTools-v0.33.0-mw2-native64/Unlinker`, then register its source/binary identity:

```sh
PYTHONPATH=. python3 -B tools/register_extractor_build.py \
  --source tooling-local/sources/OpenAssetTools-v0.33.0
```

This never executes the binary. It requires the exact upstream commit and exact tracked patch diff; it allows compiler-specific output hashes while preserving provenance. It is not a way to approve an arbitrary downloaded executable.

Copy owned `zone/english/common_mp.ff` (and `common.ff` when needed) into `profiles/dsr-mw2/drive_c/Assets/mw2-2009/zone/english/`. The measured layout is version **276**, `IWffu100`, zlib from offset 21, eight-byte native pointers with legacy32 offsets/alignment. The animation pipeline pins `common_mp.ff` SHA-256 `e0ef62d050d43b84df99b460106631351f9932b744e77ac3ab5f30db00f0f26f`. A different container can still contain identical assets, but must be investigated and documented separately; do not simply replace the constant.

The native64 patch is bounded to the measured M9/common-zone path. `af_caves.ff` map collision remains unsupported. It is not a universal MW2 fastfile reader.

## Extraction layout

Unlinker supports `--include-assets`, `--output-folder` and `--model-format`. `DSR_MW2_EXTRACT_MODEL` filters an exact model asset name. For example, after source review and execution authorization, run the local binary with `--include-assets xmodel --model-format OBJ --output-folder converted/mw2-2009/unlinked/m9-native64` and the copied `common_mp.ff`, with `DSR_MW2_EXTRACT_MODEL=weapon_beretta`. Repeat with `XMODEL_EXPORT` for its rig. Consult the pinned CLI source for exact asset-type parsing rather than assuming options from a newer release.

Required local exports (keep original names):

| Folder below `converted/mw2-2009/unlinked/` | Required outputs |
| --- | --- |
| `m9-native64/model_export/` | `weapon_beretta_lod0.obj`, `.xmodel_export`, `weapon_beretta.mtl`; retain original LODs |
| `m9-handling-models/model_export/` | `viewmodel_beretta_lod0.xmodel_export`, `viewmodel_base_viewhands_lod0.xmodel_export` |
| `m9-handling-animation/xanim/` | Original `viewmodel_beretta_` clips: idle, fire, fire_ads, lastfire, reload, reload_empty2, ads_up, ads_down, pullout, putaway; keep exporter filenames without adding an extension |
| `m9-reference-weapon/weapons/` | `beretta_mp` original weapon fields |
| `m9-handling-sound/sound/` | Original M9 shot and three reload Foley exports identified in `tools/prepare_m9_audio.py` |

Export models with `xmodel`, animations with `xanim`, weapon fields with `weapon`, and embedded audio with the pinned reader's applicable sound asset type. The source model filter applies only to models. Restrict output folders and inspect warnings/errors; do not treat a partially parsed zone as a successful extraction. Source IWI images are read from the owned `main/iw_02.iwd`, `iw_03.iwd` and `iw_05.iwd` archives; those archives stay unchanged.

## Base native model and loadout packages

1. `python -m dsr_mw2.asset_provenance --obj converted/mw2-2009/unlinked/m9-native64/model_export/weapon_beretta_lod0.obj --fastfile common_mp.ff` binds the export to the copied fastfile, source-built extractor, original materials and rig.
2. `python -m dsr_mw2.weapon_textures /path/to/owned/MW2/main` prepares native texture candidates. Run `python -m dsr_mw2.roundtrip_template` for the original DSR weapon container round trip.
3. `python -m dsr_mw2.model_bridge --obj <the-OBJ-above> --provenance <its-weapon_beretta-provenance.json>` builds `converted/dsr/m9-model-candidate`. Repeat with `--include-suppressor --output converted/dsr/m9-suppressed-model-candidate`.
4. Run `python -m dsr_mw2.build_weapon_text --model <candidate-folder>` for each candidate, then `python -m dsr_mw2.package_loadout --loadout loadouts/m9-sidearm.json --model <candidate-folder> --output converted/packages/<preset>`. Repeat for `m9-low-damage.json` and both model choices. Preset names: `m9-sidearm`, `m9-low-damage`, `m9-sidearm-suppressed`, `m9-low-damage-suppressed`.
5. Run `tools/review_m9_attachment.py`, then `tools/orient_m9_attachment_study.py`, `tools/package_upright_m9.py` and `tools/correct_m9_winding.py`. The final base packages are under `converted/packages/winding-v2/`.
6. Run `tools/verify_m9_candidates.py` and `tools/verify_native_gameplay_data.py`. Use `python -m dsr_mw2.install_private --help` for the explicit closed-profile installer; select the `winding-v2` revision and desired preset. Do not install the older backwards-facing candidate.

These base packages alone are still a crossbow-derived world-model prototype. The current owner package additionally needs the native action, armory, audio, adapter and first-person steps below.

## Player/weapon action authoring chain

Extract the native player skeleton from the private stock DSR character binders with the pinned Soulstruct reader into `tooling-local/handling-review/dsr-player-skeleton.hkx`. Select the actual skeleton entry, not an animation. Expected SHA-256: `6439d12659afa550ef2c296116d457dcabf0f5bf9760cbdf099d4a6db38a8917`. The Havok trial verifies its 61-bone `Master` identity and round trip before any subsequent conversion.

Run these offline tools in order; each writes local reports consumed by later stages:

```text
verify_m9_animation_exports.py
prepare_m9_pose_samples.py
havok_offline_trial.py
build_m9_handling_studies.py --attachment-report converted/dsr/m9-upright-review/report.json
build_m9_weapon_motion_study.py
build_m9_weighted_weapon_study.py
align_m9_weighted_muzzle.py
prepare_player_reference_motion.py
preserve_native_havok_types.py
prepare_native_bound_player.py
prepare_native_bound_player.py --aligned
prepare_native_bound_player.py --aligned --continuous
prepare_native_bound_weapon.py
prepare_m9_ready_weapon.py
prepare_m9_raised_anchor.py
prepare_m9_contact_pose.py
prepare_m9_contact_pose.py --landmarks
prepare_m9_sight_textures.py
prepare_m9_weighted_sights.py
build_m9_action_trial.py --variant landmark-sights
build_m9_armory.py
```

All names above are under `tools/`. Do not rerun armory over its already extended manifest; rebuild the base `landmark-sights` action package first if changing it. The resulting armory manifest covers nine native overrides. Earlier integrated/reference/type-table-only variants have known startup failures and their sanitized fingerprints remain blocked. Other studies are retained for research, not alternate ready packages.

The optional `review_equipped_gauntlet.py` expects a locally generated read-only armor diagnostic; it is not a required setup step and no author's character diagnostic is included. CPU geometry/contact results do not qualify in-game appearance.

## Audio, first-person packet and native binaries

```sh
PYTHONPATH=. .venv/bin/python -B tools/prepare_m9_audio.py
PYTHONPATH=. .venv/bin/python -B tools/build_native_m9_mpeg.py
PYTHONPATH=. .venv/bin/python -B tools/build_m9_viewmodel.py
PYTHONPATH=. python3 -B tools/build_native_observer.py
PYTHONPATH=. python3 -B tools/build_window_controls.py
PYTHONPATH=. python3 -B tools/build_m9_handling.py
PYTHONPATH=. python3 -B tools/native_input_trial.py build
PYTHONPATH=. python3 -B tools/prepare_native_research.py
PYTHONPATH=. python3 -B tools/check_viewmodel_offline.py
```

`build_native_m9_mpeg.py` uses a trusted local FFmpeg executable for file encoding only. Keep original source shot audio and stock FSB/FEV banks. Do not install the retained earlier PCM bank from `build_native_m9_audio.py`: that experiment crashed FMOD and is explicitly rejected.

The first-person packet is `converted/mw2-2009/viewmodel-v1/m9.dsrvm` plus a local manifest. It contains retail geometry, textures and animation and **must never be committed**. The shader-only `--console` check and `entry_observer_trial.py` require the guarded private CrossOver profile and execution scope; neither starts a game, but they are not source-only compilation.

Keep every generated evidence/build receipt local. Finish with the offline owner preparation from [SETUP](SETUP.md), then let the owner perform the actual acceptance sequence. Full native first-person integration remains unverified in this source release.
