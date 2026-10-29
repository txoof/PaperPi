# Making a release

A **release** is a version of PaperPi that people install. The install script and `paperpi-install update` install the newest release, so a change reaches users only once it is in a release. (To try the newest code before that: `sudo paperpi-install update --ref main`.)

## Version numbers

The version is in `pyproject.toml`, written the way Python writes versions. Its release on GitHub has a **tag** (a fixed name for one commit): `v` and the version.

| Version | Tag | Kind |
|---|---|---|
| `2.0.0` | `v2.0.0` | a full release |
| `2.0.0a1`, `2.0.0b1`, `2.0.0rc1` | `v2.0.0a1`, … | a test release: alpha, beta, release candidate |

The installer takes the newest full release. While there is none, it takes the newest test release.

Between releases, `main` keeps the version of the last release; the next release changes it.

## Steps

1. **Set the new version** in a pull request: change `version` in `pyproject.toml` and run `uv lock` (the lock file holds the version too). It is reviewed and merged like any other pull request.
2. **Tag the merge commit** and send the tag to GitHub:

    ```bash
    git fetch origin
    git tag v2.0.0 origin/main
    git push origin v2.0.0
    ```

3. **GitHub makes the release.** The workflow `.github/workflows/release.yml` checks that the tag is on `main` and matches the version in `pyproject.toml`, then makes the release on GitHub, with notes that list the pull requests merged since the last release. A version with a letter becomes a "pre-release". The manual's [What's new](changelog.md) page links to these notes.

## If the check fails

Delete the tag, fix the version and start again:

```bash
git push origin :refs/tags/v2.0.0
git tag -d v2.0.0
```

Never move a tag that already has a release: people may have installed it.

## Changes to the install script

The one-line install command always downloads the install script from `main`, but the script installs the code of the newest release. So a change to the script must keep working with the code of the last release. When the script needs something new from PaperPi (such as a new option of `paperpi example-config`), make a release with that first.
