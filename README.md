# DSR × MW2 Crossover

**Modern Warfare 2 (2009) M9 weapons inside native Dark Souls Remastered.**

An unofficial, offline crossover built around DSR's own world, enemies, bosses, movement and projectile damage. Includes authentic-asset conversion recipes, native magazine/reload handling, recoil, shot audio, a bonfire armory and an original D3D11 first-person weapon renderer.

**This is the complete source release of the current experimental M9 build, not a bundled game or a universal installer.** You need your own PC copies of **Dark Souls Remastered** and **Call of Duty: Modern Warfare 2 (2009)**. Extracted models, textures, animations, audio, game executables and saves are intentionally absent. An agent must build local assets and prepare an isolated profile before the launcher can run.

## Give it to your agent

Copy this request into your coding agent:

> Set up https://github.com/oh-ashen-one/dsr-mw2-crossover using my own installed copies of Dark Souls Remastered and Modern Warfare 2 (2009). Read AGENTS.md, SKILL.md and docs/SETUP.md first. Work in a separate checkout and private game profile, preserve my installed games and saves, build the authentic M9 package locally, and run the offline checks. Tell me any version or platform blocker precisely. Leave launching and gameplay testing to me. Do not upload game assets or bypass a failed compatibility check.

Start with [the agent handoff](SKILL.md), [setup runbook](docs/SETUP.md), [build map](docs/BUILD.md) and [verified status](docs/STATUS.md).

## What is included

| Component | Current scope |
| --- | --- |
| Native host | Dark Souls **Remastered**, exact supported PC executable; no substitute engine |
| Weapons | Authentic MW2 M9 and original suppressor model; two damage presets |
| Combat | DSR-native projectile and ammo path; virtual 15-round magazine, reload and confirmed-shot recoil |
| Equipment | Native Asylum bonfire armory, purchases, right-hand slots and save persistence |
| First person | Original MW2 hands, gun meshes, textures and clips rendered by an original D3D11 adapter |
| Input | Keyboard/mouse and XInput mapping; physical DualSense acceptance still required |
| Isolation | Private stock/candidate copies, separate save banks, offline launch and reversible overrides |

Some native handling, moving-fire/reload, recoil, audio and armory behavior was observed in earlier disposable tests. **The latest first-person renderer is compiled and checked offline; its in-game integration, physical PS5 input, boss encounter, death/reset and performance are not yet qualified.** The suppressor currently changes appearance only. This release does not include the full MW2 weapon roster or a complete custom-loadout editor. See the [status matrix](docs/STATUS.md) before calling it ready.

## Platform and quick source checks

The implemented launcher targets **Apple M3 Ultra, macOS and CrossOver**. CrossOver 26.2 was used for the private development environment. Other Macs and native Windows need separate compatibility work; 32 GB RAM alone does not establish support. English DSR data and the measured native64 IW4 fastfile layout are required. Exact hashes are checked before installing or hooking anything.

```sh
git clone https://github.com/oh-ashen-one/dsr-mw2-crossover.git
cd dsr-mw2-crossover
python3 -m pip install --only-binary=:all: -r requirements-tests.txt
python3 -B -m unittest discover -s tests -v
python3 -B -m dsr_mw2.doctor
```

The doctor intentionally exits with code **2** on a fresh source checkout because private assets and a profile have not been prepared. It does not launch anything. After completing setup, the owner uses **Play DSR + MW2.command**. `python3 -B -m dsr_mw2.owner_test --prepare` is the offline install/restore check, not a substitute for gameplay acceptance.

Controls in the owner candidate: **L2 / right mouse** to aim, **R2 or R1 / left mouse** to fire, **Square while aiming / R** to reload. Square outside aim keeps native item use. Use D-pad Right to switch equipped right-hand weapons. The first Asylum bonfire contains the armory. Your new private character must reach it through ordinary gameplay; no author save is distributed.

## Source and credits

The repository preserves the original Python pipeline, C++/assembly adapter and renderer, synthetic tests, authoring studies and OAT compatibility patches. Private conversation history, account information, machine operations, retail data and build outputs are excluded. Older research variants remain for reproducibility; follow the current build map rather than installing them at random.

Original project source is licensed **GPL-3.0-only**, with the specifically identified IW4L-derived recoil component under Apache-2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [CREDITS.md](CREDITS.md) for upstream authors, exact revisions and separate terms. These licenses do not cover either game's assets or trademarks. Unofficial; not affiliated with or endorsed by the game publishers.
