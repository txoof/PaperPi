# Making a release

`install/paperpi-install` installs the newest release, so a change reaches users only when a release includes it. `--ref main` installs the newest code instead, for testing.

A release is a version tag on `main`: `v` and the version in `pyproject.toml`, written the way Python writes versions:

| Version | Tag | Kind |
|---|---|---|
| `2.0.0` | `v2.0.0` | a full release |
| `2.0.0a1`, `2.0.0b1`, `2.0.0rc1` | `v2.0.0a1`, … | a test release (alpha, beta, release candidate) |

The installer takes the newest full release. While there is none, it takes the newest test release, and while there is no release at all, `main`.

## Steps

1. A PR sets the new `version` in `pyproject.toml` and runs `uv lock` (the lock file holds the version too). It is reviewed and merged like any other PR.
2. Tag the merge commit and push the tag:
   ```bash
   git fetch origin
   git tag v2.0.0a1 origin/main
   git push origin v2.0.0a1
   ```
3. The workflow `.github/workflows/release.yml` checks that the tag matches the version in `pyproject.toml` and makes the GitHub release, with notes listing the PRs merged since the last release. A version with a letter becomes a "pre-release" on GitHub.

If the check fails, delete the tag (`git push origin :refs/tags/v2.0.0a1`, then `git tag -d v2.0.0a1`), fix the version and start again. Never move a tag that has a release: installs may already use it.

Between releases `main` keeps the version of the last release; the next release PR changes it.
