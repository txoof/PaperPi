# Working on PaperPi v2

These rules apply to every person and agent working in this repository.

## Communication
- Write plainly: no metaphors, figures of speech or jargon. Explain a technical term the first time it is used.
- When guiding the maintainer (txoof) through manual steps, give one short step at a time.

## The old code (v1)
- v1 lives on branch `v1` (tag `v1-final`). Read it to understand how something behaved.
- **Do not copy code from v1.** Write new code. Good ideas are carried over through the v1 inventory and design notes (milestone M1), not by copying.

## Related repositories
- `txoof/epdlib` — the display and layout library PaperPi uses. Developed alongside PaperPi; during development PaperPi uses the local checkout at `../epdlib`. Changes to rendering or drivers go there, not here.

## How work is tracked
- **GitHub Issues are the only to-do list.** Every change starts from an issue in a milestone (M0–M10).
- Each issue has an **Area**: the folders it is allowed to change (see the area map below).
- **Claim before starting:** add the label `in-progress` and a comment `claimed by <worktree name>`.
- **Do not start** an issue that is already claimed, or whose Area overlaps a claimed issue.
- Shared files (`pyproject.toml`, `uv.lock`, CI files, the config schema) are changed only in their own small issue.

## Area map
| Area | Folders |
|---|---|
| core | `src/paperpi/` (except the folders below) |
| web | `src/paperpi/web/` |
| plugins/<name> | `src/paperpi/plugins/<name>/` |
| install | `install/`, `Dockerfile` |
| docs | `docs/` |
| ci | `.github/`, `pyproject.toml`, `uv.lock` |

This map grows as the code grows. Update it in the same PR that adds a new area.

## Worktrees and branches
- One git worktree per issue, at `~/src/wt/PaperPi-<issue#>-<short-name>`, on branch `<issue#>-<short-name>`.
- Never work directly on `main`.
- Delete the worktree after the PR is merged.

## Pull requests
1. Open a PR that links the issue (`Closes #<n>`). Fill in the PR template, including test results and before/after images for anything visual.
2. Review agents check the PR and post their findings as PR comments: code quality, unit tests, security, documentation.
3. Fix the findings or explain in a reply why not.
4. **Only txoof approves and merges. Agents never merge, never approve, and never push to `main`.** GitHub branch protection enforces this.

## Tools and commands
- Python 3.13 (Raspberry Pi OS trixie). `uv` manages the environment.
- `uv sync` — install. `uv run pytest` — tests. `uv run ruff check .` and `uv run ruff format .` — style.
- Plain `.py` files only. No Jupyter notebooks in the repo.
- Tests that need real hardware are marked `@pytest.mark.hardware` and run only on the Pi.

## Agent identity (on the development Pi)
Agents run as the GitHub account `txoof-bot`. This is set in `~/src/.claude/settings.json`, which is not part of this repo, so **start Claude Code from `~/src`**, not from inside a repo folder.
