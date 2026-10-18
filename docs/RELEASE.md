# Release procedure

Tagging is the release trigger: `.github/workflows/release.yml` builds, verifies and
publishes both executables in one run. What remains manual is the version bump and the
verification record.

## Contract

Four things must agree, and each is enforced:

| Thing | Where | Checked by |
| --- | --- | --- |
| `monitor.__version__` | `monitor.py` | `tests/test_version_consistency.py` (CI) |
| The newest `## [vX.Y.Z] - YYYY-MM-DD` heading | `CHANGELOG.md` | same test (CI) |
| The tag `vX.Y.Z` | git / the release workflow | release workflow, before building |
| An empty `## [Unreleased]` section | `CHANGELOG.md` | release workflow, before building |
| The embedded Windows version resource `X.Y.Z.0` | the built executables | release workflow, after building |

`release_notes.py` prints (or writes with `--out`) the changelog section for a version, so
the published notes are the changelog text itself and there is no second copy of the
release notes to keep in sync. Locally: `python release_notes.py 0.6.4`.

`python release_notes.py --check-unreleased` is the other half of that contract: it exits
non-zero while entries are still under `## [Unreleased]`. The notes are cut from the version
section alone, so anything left above it never reaches the release. The workflow runs the
check before building, which turns a forgotten move into a failed run instead of a silent
omission.

## Prepare a release (PR to master)

1. Bump `monitor.__version__` in `monitor.py`.
2. Add the `## [vX.Y.Z] - YYYY-MM-DD` section to `CHANGELOG.md` (`Added` / `Changed` /
   `Fixed` / `CI` / `Docs` as applicable) plus its link definition. Move the entries that
   accumulated under `## [Unreleased]` into it; that heading stays at the top, empty again,
   and its link definition points at the new tag. Confirm the move with
   `python release_notes.py --check-unreleased`, which must report nothing pending — the
   workflow refuses a tag whose `## [Unreleased]` still has entries.
3. `python -m pytest tests -q` — the version contract must pass.
4. Merge the PR, then tag the merge commit and push the tag:

   ```powershell
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

## What the tag push does

The `Release` workflow runs on `windows-latest`:

1. **Resolve and check the tag** — requires `vX.Y.Z`, confirms the tagged commit is an
   ancestor of `master`, compares the tag with `monitor.__version__`, runs the version
   contract test, writes the changelog notes to `notes.md`, and fails if `## [Unreleased]`
   still has entries (those would be missing from the published notes).
2. **Run the full test suite** with the 70% coverage floor (`.coveragerc`) — this includes the
   browser extension's node tests, which `tests/test_browser_node_suite.py` drives through
   `node --test`.
3. **Build** both executables with `build.ps1` (icon + version resource from
   `windows_version.py`).
4. **Verify the executables** — each must exist and report version resource `X.Y.Z.0`; the
   SHA-256 of each is printed to the run log and the job summary.
5. **Run the packaged tests** (`TEST_PACKAGED_EXPORT=1`).
6. **Publish** the release with the changelog notes and both assets. If the release
   already exists — a previous attempt left a draft, or a partial upload — the assets are
   re-uploaded with `--clobber` and the release is un-drafted, so the run is retryable
   instead of needing manual repair.

## Reading a failed run

The test suite is the gate that stops a bad release, so a red run has to say *why*:

- Every test that launches a process goes through the `run_process` fixture
  (`tests/conftest.py`). On a non-zero exit or a timeout the failure message carries the
  command, the timeout, how long the call actually took, the exit code and the tail of
  both streams — enough to tell a hang from a slow cold start from a real crash. The
  default timeout is 120 s and can be raised for a slow runner with
  `USAGE_MONITOR_TEST_TIMEOUT` (seconds) without editing a test.
- `--durations=10` is always on (`pytest.ini`), so the log ends with the slowest tests.
  Those E2E launches normally take 0.1–1.2 s, so a two-minute entry is a hang rather than
  a slow machine.

Read the whole `Run tests` step output: the failing test is named in the short summary,
above the durations list.

## Dry run

Actions → Release → Run workflow with an existing tag and `publish` left unchecked. It
builds and verifies everything and uploads the exes as a workflow artifact without
touching any release. Use this after changing the workflow.

With `publish` checked it does exactly what a tag push does, for a tag that already
exists.

The dry run checks out the tag, so the tag must be one that already embeds a version
resource (`v0.6.3` or later) — earlier builds have no resource to verify. If the tag
predates a helper the workflow uses, that helper is taken from `master` for the run while
the release notes still come from the tag's own `CHANGELOG.md`. The `Unreleased` check is
always run that way — it is release policy rather than tag content — so a tag whose
changelog predates the heading passes it.

## After the release

1. Download the published assets and compare their SHA-256 with the values the run printed
   into the job summary:

   ```powershell
   gh release download vX.Y.Z --dir <tmpdir> --clobber
   ```

   The assets are built on the runner, so a local `build.ps1` build is **not** expected to
   be byte-identical (different PyInstaller and Python builds). Compare the version
   resource (`X.Y.Z.0`) locally, and the SHA-256 against the run.

2. Record the verification in `docs/ISSUE_VERIFICATION.md` (follow the existing release
   records): the run URL, the tag and commit, the SHA-256 of each published asset, and
   anything the run could not check.
3. If the release is wrong, see `docs/ROLLBACK.md`: land a fix and tag a new patch version.
   Tags are never moved.

## Deliberately not automated

- Reloading the unpacked browser extension at `chrome://extensions`: it needs the user's
  own Chrome session.
- The verification record in `docs/ISSUE_VERIFICATION.md`: it reports what was actually
  observed on the published assets, so it is written per release.
