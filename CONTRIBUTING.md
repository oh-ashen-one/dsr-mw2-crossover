# Contributing

Read `AGENTS.md` and the status matrix. Work on a separate branch. Keep changes narrowly scoped, preserve version/ownership checks, and distinguish runtime evidence from offline tests.

Before a pull request, run:

```sh
python3 -m pip install --only-binary=:all: -r requirements-tests.txt
python3 -B -m unittest discover -s tests -v
python3 tools/check_public_release.py
git diff --check
```

Add meaningful tests for parser boundaries, native state transitions and preservation failures. Never add retail fixtures, images, extracted data, executable dumps, saves, profiles or account details. Synthetic fixtures are welcome. Preserve third-party notices and identify any newly adapted code and its license.

Describe the concrete behavior change, supported executable/data revision, tests run and unresolved acceptance gates. Do not claim a successful native playtest from compilation or a CPU render. An issue report should include sanitized version/hash metadata and the failed step, not raw game/process memory or credentials.

Contributions to original project code are under GPL-3.0-only, subject to explicitly retained third-party component licenses. No contributor is asked to grant rights to either game's assets.
