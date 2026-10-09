# Working on PaperPi v2

These rules apply to every person and agent working in this repository.

## Communication
- Write plainly: no metaphors, figures of speech or jargon. Explain a technical term the first time it is used.
- When guiding the maintainer (txoof) through manual steps, give one short step at a time.

## The old code (v1)
- v1 lives on branch `v1` (tag `v1-final`). Read it to understand how something behaved.
- **Do not copy code from v1.** Write new code. Good ideas are carried over through the v1 inventory and design notes (milestone M1), not by copying.

## Related repositories
- `txoof/epdlib`: the display and layout library PaperPi uses. Developed alongside PaperPi. Changes to rendering or display drivers go there, not here.
- Until epdlib is on PyPI, `pyproject.toml` gets epdlib from GitHub at one fixed commit, so CI and every install use the same code. When PaperPi needs a newer epdlib, move that commit forward in the PR that needs it.
- To try out epdlib changes that are not on GitHub yet, install the local copy into your worktree (`uv pip install -e ~/src/epdlib`) and run commands with `uv run --no-sync ...` (for example `uv run --no-sync pytest`). A plain `uv run` puts the fixed commit back first. Never commit the local copy; `uv sync` undoes it.

## How work is tracked
- **GitHub Issues are the only to-do list.** Every change starts from an issue in a milestone (M0–M10).
- Exception: Dependabot (GitHub's bot for dependency updates) opens update PRs without an issue. Agents do not claim or change them; txoof reviews and merges them.
- Each issue has an **Area**: the folders it is allowed to change (see the area map below).
- **Do not start** an issue that is already claimed (has the `in-progress` label), or whose Area overlaps a claimed issue. Check with:
  ```bash
  gh issue list --label in-progress
  ```
- **One PR per task, unless the task is too big.** A task is one piece of work that may cover several issues (for example all design notes of a milestone, or a whole test round). Group them in one PR instead of opening one PR per issue: every PR costs txoof review time. A task that would be more than about 800 changed lines is split into several PRs that each work on their own (see "Size of a PR" below); list them in the task's issue. Open a PR as a draft while work continues and mark it ready when its part is done.
- **Claim the issues of a task before starting** (every issue the task covers):
  ```bash
  gh issue edit <n> --add-label in-progress
  gh issue comment <n> --body "claimed by PaperPi-<task-name>"
  ```
  Then move its card on the project board to **In Progress** (see "Project board" below).
- **Release a claim** when the PR is merged (GitHub closes the issue) or when you stop working on it:
  ```bash
  gh issue edit <n> --remove-label in-progress
  gh issue comment <n> --body "released: <reason>"
  ```
  If you stop without finishing, move its card back to **Todo**.
- Shared files (`pyproject.toml`, `uv.lock`, `.python-version`, `.github/`, the config schema) are used by everyone, so take care when changing them:
  - A PR may change `pyproject.toml`, `uv.lock` and the config schema (the settings the config file may contain: `src/paperpi/config.py`, and `PluginEntry` in `src/paperpi/plugin.py`) when its own work needs it (for example a new dependency or setting), so related changes stay together. First check that no other open PR changes them (the command lists every PR that changes one of these files; for `plugin.py`, look whether it changes `PluginEntry`):
    ```bash
    for n in $(gh pr list --json number --jq '.[].number'); do gh pr diff $n --name-only | grep -qxE 'pyproject.toml|uv.lock|src/paperpi/config.py|src/paperpi/plugin.py' && echo "PR $n"; done
    ```
    Once your own PR is open, it shows up in this list too.
  - The other shared files are changed only in their own small issue.

## Project board
All PaperPi and epdlib work is shown on one board, where each issue or PR is a card (one entry on the board) in a column: https://github.com/users/txoof/projects/4 (columns Todo, In Progress, In Review, Done).
- PaperPi issues and PRs are added to the board automatically. epdlib issues and PRs are not (GitHub's free plan allows automatic adding from one repo only); see epdlib's CLAUDE.md.
- GitHub moves cards to **Done** when an issue is closed or a PR is merged. Agents move cards at the other steps:

| When | Set the issue (and its PR) to |
|---|---|
| You create an issue | Todo (automatic for PaperPi) |
| You claim it | In Progress |
| You open its PR | In Review |
| You release a claim without finishing | Todo |

Add or move a card (adding a card that is already on the board just returns it, so the same commands do both):
```bash
item=$(gh project item-add 4 --owner txoof --url <issue-or-PR-URL> --format json --jq .id)
gh project item-edit --project-id PVT_kwHOANmg6c4BlqOG --id "$item" \
  --field-id PVTSSF_lAHOANmg6c4BlqOGzhkWLj8 --single-select-option-id <column-id>
```
Column IDs: Todo `f75ad846`, In Progress `47fc9ee4`, In Review `b470c173`, Done `98236657`.

## Area map
| Area | Folders |
|---|---|
| core | `src/paperpi/` (except the folders below) |
| web | `src/paperpi/web/` |
| plugins/<name> | `src/paperpi/plugins/<name>/` |
| install | `install/`, `Dockerfile` |
| docs | `docs/` |
| bench | `bench/` (test programs that are not part of the app, e.g. the M2 driver test round) |
| ci | `.github/`, `pyproject.toml`, `uv.lock`, `.python-version` |

This map grows as the code grows. Update it in the same PR that adds a new area.

## Worktrees and branches
A worktree is a separate folder with its own copy of the repo, so several agents can work at the same time without touching each other's files.
- One worktree per task, on branch `<task-name>` (for a task with a single issue: `<n>-<short-name>`):
  ```bash
  git -C ~/src/PaperPi fetch origin
  git -C ~/src/PaperPi worktree add -b <task-name> ~/src/wt/PaperPi-<task-name> origin/main
  ```
- Never work directly on `main`.
- After the PR is merged, remove the worktree:
  ```bash
  git -C ~/src/PaperPi worktree remove ~/src/wt/PaperPi-<task-name>
  ```

## Pull requests
1. Open one PR per task (or per part of a big task, see "Size of a PR") that links its issues (`Closes #<a>, closes #<b>`; a part that doesn't finish an issue says "Part of #<n>"). Fill in the PR template, including test results and before/after images for anything visual.
2. Review agents check the PR and post their findings as PR comments: code quality, unit tests, security, documentation.
3. Fix the findings, or explain in a reply why not.
4. **Only txoof approves and merges. Agents never merge, never approve, and never push to `main`.** GitHub branch protection enforces this.

### Size of a PR
Every PR costs txoof review time. Too many small PRs and too few huge ones both waste it.
- **Aim for 300–600 changed lines** (code, tests and docs together; images don't count). Above about 800 lines, split the work: 800 is a guideline and an upper bound, so a PR may go a little over it, but never much. Below that, keep a task in one PR (see "One PR per task" above).
- **Each PR does one thing that works on its own**, with its tests and docs. `main` is never left half-built.
- **No PR for one small change** (a typo, a one-line rule). Put it in the next related PR.
- **Every PR is based on `main`.** No stacked PRs (a PR based on another PR's branch): they cost extra merges and conflict fixes. Split a task into parts that each go straight to `main`, one after the other.
- **Plan the split before coding.** Show the planned PRs to txoof together with the design questions. One issue may need several PRs; list them in the issue. For example, the scheduler (+1925 lines in #206) could have been four PRs: the new plugins and settings; the scheduler core with its tests (which use a pretend clock); failures, the fallback plugins and config reload; the `paperpi run` command and README.
- **Review fixes:** small fixes go into the same PR. Fixes that add a new feature go into a follow-up PR, so the first one doesn't keep growing.
- See the size with `git diff --shortstat origin/main...HEAD`.

## Tools and commands
- Python 3.13 (the version in Raspberry Pi OS trixie). `uv` installs Python and all packages into `.venv`.
- `uv sync`: install. `uv run pytest`: tests. `uv run ruff check .` and `uv run ruff format .`: code style.
- `uv run pytest -n auto` runs the tests on every processor core at once (pytest-xdist; about half the time on the 4-core Pi). While working, run only the tests of the files you changed; run all of them once before the first push of a PR. GitHub runs all of them for every pull request and every merge to main.
- Plain `.py` files only. No Jupyter notebooks in the repo.
- Tests that need a real display are marked `@pytest.mark.hardware`. They are skipped by default; run them on the Pi with `uv run pytest -m hardware`.

## Agent identity (on the development Pi)
Agents run as the GitHub account `txoof-bot`. This is set in `~/src/.claude/settings.json`, which is not part of this repo, so **start Claude Code from `~/src`**, not from inside a repo folder.
