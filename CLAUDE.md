# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**ha-lumo** – Home Assistant custom integration (domain `lumo`) for the self-hosted
[Lumo](https://github.com/StefanRiese/lumo) server (client for Schulportal Hessen). It reads the
server's REST API (`docs/API.md` in the Lumo repository, local checkout `~/github/lumo`) and its
event stream; it never talks to the Schulportal. Installed with HACS (custom repository) or by
copying `custom_components/lumo`. License GPL-3.0.

## Layout

```
custom_components/lumo/   api.py (client + SSE), coordinator.py (data, live updates, lumo_new_item),
                          changes.py (what is new), timetable.py, config_flow.py, entity.py,
                          one module per platform (sensor, binary_sensor, calendar, todo, button),
                          translations/ (en, de)
tests/                    pytest against tests/fake_server.py (invented data, no real server)
scripts/version.sh        set/check the manifest version against a release tag
hacs.json                 HACS metadata
.github/workflows/        ci.yml (ruff, ShellCheck, pytest on the minimum and the latest Home Assistant),
                          validate.yml (hassfest + HACS action), release.yml; dependabot.yml
```

## Commands

Python 3.13 is needed (the system Python may be older: `uv venv --python 3.13`).

```sh
pip install -r requirements_test.txt -r requirements_lint.txt
ruff check . && ruff format --check .    # CI requires both
pytest -q
```

## Rules

- The integration only reads the server's cache (never `?refresh=1`).
- **Grades and marking homework as done are opt-in options, off by default** – keep them that
  way. Marking homework writes to the real Schulportal.
- Large lists in entity attributes go into `_unrecorded_attributes` (recorder).
- Portal HTML is converted with `html_to_text()`; never pass markup on.
- Tests use the fake server; do not point tests or experiments at a real Lumo server, and do not
  print grades, homework or other personal data from a real server.
- When entities or options change, update `README.md` and `CHANGELOG.md` and both
  `translations/*.json` (same keys). UI texts: English and German; code, comments and docs:
  English.
- API changes in the Lumo server (`docs/API.md` there) may affect `api.py` and the coordinator.
- Never mention Claude in commits or PRs.

## Workflow

- Workflow actions are pinned to commit SHAs (Dependabot updates them); keep `permissions` minimal
  and `persist-credentials: false`. The oldest supported Home Assistant is `hacs.json`
  (`homeassistant`) and the `minimum` entry of the test matrix in `ci.yml`: change both together.

- Solo repository: work on `main` or a branch; commit only when the user asks.
- Release: move *Unreleased* in `CHANGELOG.md` to a new version, `bash scripts/version.sh set
  vX.Y.Z`, commit and push, then tag `vX.Y.Z` and push the tag. HACS installs at the tag; the
  release workflow fails if `manifest.json` has another version.
