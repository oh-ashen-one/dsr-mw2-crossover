---
name: dsr-mw2-crossover
description: Prepare authentic MW2 M9 weapons for native Dark Souls Remastered in an isolated offline profile.
---

# Agent setup handoff

Use this workflow when a user asks to set up this repository with their own games. Take responsibility for engineering and offline checks; do not make the owner manually troubleshoot code. Be candid about unsupported game revisions and remaining acceptance work.

1. Read the root instructions and [status matrix](docs/STATUS.md). Establish the current user's platform, installed games, requested scope and existing renderer coordination from available local evidence. Do not inherit the author's permissions.
2. Create a dedicated branch in a separate checkout. Run the Python tests with the pinned Pillow test dependency and the public-file audit. The [doctor](dsr_mw2/doctor.py) lists missing local prerequisites without launching anything.
3. Follow [SETUP](docs/SETUP.md) to configure local paths, source tools and a fresh private CrossOver profile. Maintain a read-only stock copy and a separate candidate. Verify physical save isolation before any launch or mutation.
4. Follow [BUILD](docs/BUILD.md) in order. Extract only from copies of owned fastfiles. Keep original model/material/animation names and provenance. Build from pinned, reviewed source; do not execute an arbitrary downloaded binary because this repository mentions it.
5. Rebuild all native binaries from this checkout. Run synthetic tests, exact-image static checks, source-asset round trips and package validation. Prepare empty/private save banks through the supplied save-bank code; do not import the author's character or invent progress.
6. If the user authorized offline setup and their own later play, enable only `allow_offline_conversion` and `allow_owner_test` in ignored local configuration. The configure CLI offers these explicit flags. `allow_agent_gameplay` remains false. Configuration is a record of the user's actual scope, never a way to grant yourself permission.
7. Run `python3 -B -m dsr_mw2.owner_test --prepare` only after all prerequisites exist. It temporarily installs and restores files in the private candidate, without starting a game. Record actual output and preserved save hashes locally. Resolve failures within your authorized scope rather than claiming readiness.
8. Leave the owner a working launcher and short controls. The default owner entry point is `Play DSR + MW2.command`; it handles the temporary package and restoration. Do not open the game or send input when the owner reserved testing for themselves.
9. Report exactly what passed, what remains unverified and any version/platform blocker. If the user later authorizes agent testing, use only the verified disposable bank, foreground/process ownership and shared renderer gate. Never operate an owner-marked session.

Do not upload retail files, private configuration, saves or diagnostic dumps to GitHub, issue trackers or third-party analysis services. Share sanitized source-only changes and metadata. Preserve upstream credits and licenses.

There is no universal one-command install claim. The source tools encode a specific DSR revision and measured MW2 layout. If the owned data differs, perform a separate compatibility investigation and keep unsupported execution blocked.
