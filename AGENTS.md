# Agent boundaries

This is a public source handoff, not authorization to operate someone else's machine. The current user's instructions define your scope; no historical permissions or credentials are included.

- Read `SKILL.md`, `docs/STATUS.md`, `docs/SETUP.md` and `docs/BUILD.md` before preparing a runtime.
- Use your own branch and a physical private profile at `profiles/dsr-mw2`. Do not edit shared checkouts, original installed games or existing saves.
- Keep retail/converted files, profiles, account state, diagnostics and captures out of Git. Run `python3 tools/check_public_release.py` before publishing.
- Never copy Steam credentials, login caches, cookies, cloud/account settings or another person's saves. Let the owner handle authentication privately if it is needed. A cloned CrossOver bottle may still link Windows Documents to the host home; check physical destinations and registry selectors.
- Preserve all version, ownership, save-path and hash gates. A mismatch is a blocker to investigate, not permission to remove the check or forge a receipt.
- Ordinary setup does not authorize game input. Default `allow_agent_gameplay` is false. Owner sessions always refuse agent input. Only a new, explicit user instruction may authorize bounded play in a verified disposable save.
- Honor the machine's actual renderer coordinator. Never clear its pause marker, take over another process or launch competing games. The fallback lock coordinates only clients that use it.
- All modified gameplay remains offline. No multiplayer, anti-cheat/account/security changes, purchases or unfamiliar executable execution without the current user's applicable authorization. Do not auto-accept prompts.
- Do not use HP/save/inventory writes to fake projectile damage, equipment or progress. Preserve authentic source names and provenance. No lookalike models or replacement engine.
- Distinguish source checks, earlier runtime observations and latest-package acceptance. A successful compile or CPU preview is not proof of playable integration.

No sub-agent delegation is required. No game launch is needed to review, test or publish the source.
