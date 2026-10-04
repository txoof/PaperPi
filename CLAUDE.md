# Working on PaperPi v2

These rules apply to every person and agent working in this repository.

## Communication
- Write plainly: no metaphors, figures of speech or jargon. Explain a technical term the first time it is used.
- When guiding the maintainer (txoof) through manual steps, give one short step at a time.

## The old code (v1)
- v1 lives on branch `v1` (tag `v1-final`). Read it to understand how something behaved.
- **Do not copy code from v1.** Write new code. Good ideas are carried over through the v1 inventory and design notes (milestone M1), not by copying.

## Related repositories
- `txoof/epdlib`: the display and layout library PaperPi uses. Developed alongside PaperPi. During development PaperPi uses the local copy at `~/src/epdlib`. Changes to rendering or display drivers go there, not here.

## How work is tracked
- **GitHub Issues are the only to-do list.** Every change starts from an issue in a milestone (M0–M10).
- Exception: Dependabot (GitHub's bot for dependency updates) opens update PRs without an issue. Agents do not claim or change them; txoof reviews and merges them.
- Each issue has an **Area**: the folders it is allowed to change (see the area map below).
- **Do not start** an issue that is already claimed (has the `in-progress` label), or whose Area overlaps a claimed issue. Check with:
  ```bash
  gh issue list --label in-progress
  ```
- **Claim an issue before starting:**
  ```bash
  gh issue edit <n> --add-label in-progress
  gh issue comment <n> --body "claimed by PaperPi-<n>-<short-name>"
  ```
- **Release a claim** when the PR is merged (GitHub closes the issue) or when you stop working on it:
  ```bash
  gh issue edit <n> --remove-label in-progress
  gh issue comment <n> --body "released: <reason>"
  ```
- Shared files (`pyproject.toml`, `uv.lock`, `.python-version`, `.github/`, the config schema) are changed only in their own small issue.

## Area map
| Area | Folders |
|---|---|
| core | `src/paperpi/` (except the folders below) |
| web | `src/paperpi/web/` |
| plugins/<name> | `src/paperpi/plugins/<name>/` |
| install | `install/`, `Dockerfile` |
| docs | `docs/` |
| ci | `.github/`, `pyproject.toml`, `uv.lock`, `.python-version` |

This map grows as the code grows. Update it in the same PR that adds a new area.

## Worktrees and branches
A worktree is a separate folder with its own copy of the repo, so several agents can work at the same time without touching each other's files.
- One worktree per issue, on branch `<n>-<short-name>`:
  ```bash
  git -C ~/src/PaperPi fetch origin
  git -C ~/src/PaperPi worktree add -b <n>-<short-name> ~/src/wt/PaperPi-<n>-<short-name> origin/main
  ```
- Never work directly on `main`.
- After the PR is merged, remove the worktree:
  ```bash
  git -C ~/src/PaperPi worktree remove ~/src/wt/PaperPi-<n>-<short-name>
  ```

## Pull requests
1. Open a PR that links the issue (`Closes #<n>`). Fill in the PR template, including test results and before/after images for anything visual.
2. Review agents check the PR and post their findings as PR comments: code quality, unit tests, security, documentation.
3. Fix the findings, or explain in a reply why not.
4. **Only txoof approves and merges. Agents never merge, never approve, and never push to `main`.** GitHub branch protection enforces this.

## Tools and commands
- Python 3.13 (the version in Raspberry Pi OS trixie). `uv` installs Python and all packages into `.venv`.
- `uv sync`: install. `uv run pytest`: tests. `uv run ruff check .` and `uv run ruff format .`: code style.
- Plain `.py` files only. No Jupyter notebooks in the repo.
- Tests that need a real display are marked `@pytest.mark.hardware`. They are skipped by default; run them on the Pi with `uv run pytest -m hardware`.

## Agent identity (on the development Pi)
Agents run as the GitHub account `txoof-bot`. This is set in `~/src/.claude/settings.json`, which is not part of this repo, so **start Claude Code from `~/src`**, not from inside a repo folder.
