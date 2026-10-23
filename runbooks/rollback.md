# Runbook: roll back a formula

Use this when a merged `Formula/contribute.rb` (or `contribute-candidate.rb`)
installs a broken, wrong, or unwanted `hive-contributor` image.

## Impact

Users running `brew install` / `brew upgrade hivecommons/hive/contribute` get
the SIF pinned in the formula on `main`. Already-installed copies keep working
until upgraded; only new installs and upgrades are affected.

## Detect

- The `Tap CI` workflow fails on `main` (`brew audit`, `brew install`,
  `hive-contribute --help`, `brew test`).
- `hive-contribute --wrapper-version` prints an unexpected `image=` digest.
- Upstream (`hivecommons/hive`) reports the promoted image is bad.

## Why a plain upstream rollback is not enough

`convert.yml` resolves `ghcr.io/hivecommons/hive-contributor:<channel>` to a
digest and exits early when a release `contribute-<digest12>` already exists.
If upstream re-points `stable` to a previous digest whose release still exists,
the workflow does nothing and the formula keeps the bad digest. Roll back the
formula explicitly using one of the options below.

## Option A: revert the generated formula (fastest)

Reverting restores the earlier formula's UTC generation timestamp, so its
`<YYYYMMDD>.<HHMMSS>.<digest12>` version is lower than the bad formula's.
Homebrew only upgrades to a greater version: `brew upgrade` will not roll back
users who already installed the bad version. Those users must run
`brew reinstall` as shown in [Verify](#verify) after the revert merges.
New installs use the restored formula.

1. Find the merge commit of the bad generated-formula PR on `main`.
2. Revert it and open a PR against `main`:

   ```sh
   git switch -c revert-contribute-<bad-digest12> origin/main
   git revert --no-edit <bad-merge-commit>
   git commit --amend -s --no-edit
   git push origin HEAD
   ```

3. Wait for `Tap CI` to pass, then merge (needs a maintainer).
4. Release assets of earlier digests (`contribute-<digest12>`) are retained, so
   the reverted formula's URLs and SHA-256 values remain valid. Confirm with:

   ```sh
   gh release view contribute-<previous-digest12> --repo hivecommons/homebrew-hive
   ```

## Option B: regenerate from a known-good channel state

1. Make sure upstream `stable` (or `candidate`) points at the known-good digest:

   ```sh
   docker buildx imagetools inspect ghcr.io/hivecommons/hive-contributor:stable
   ```

2. Run the conversion with `force` so the existing release is not skipped:

   ```sh
   gh workflow run convert.yml --repo hivecommons/homebrew-hive \
     -f channel=stable -f force=true
   ```

3. Review and merge the generated PR (`generated/contribute-<digest12>`).

Use Option A when the bad image is still `stable` upstream and you need the tap
fixed first; fix upstream afterwards so the next six-hourly run does not
re-introduce the bad digest.

## Prevent re-introduction

If upstream `stable` still points at the bad digest, any later conversion for
that digest (for example after a release is deleted, or with `force=true`) will
regenerate the bad formula. Fix the channel upstream first, and do not delete
release assets of a digest that upstream still serves.

## Verify

For Option A, use `brew reinstall`, not `brew upgrade`, to replace an already
installed bad version despite the restored formula's lower version number.

```sh
brew update
brew reinstall hivecommons/hive/contribute
hive-contribute --wrapper-version
```

The printed `image=` digest must match the intended known-good digest.

## Follow-up

- Record the bad digest, the window it was live on `main`, and the cause in an
  issue on this repository, using [postmortem-template.md](postmortem-template.md).
- If the cause was missing validation, extend `.github/workflows/ci.yml` or
  `scripts/generate-formula.py` so it is caught before merge.

## Rolling back `hotshot` (hand-maintained)

`Formula/hotshot.rb` is not generated, so Options A and B above do not apply:
there is no channel to re-point and `convert.yml` never touches it. A bad
`hotshot` is a bad `url`/`sha256` bump (or a build break) merged to `main`.

Impact: new installs and upgrades build the bad tag from source. Installed
copies keep working until upgraded.

1. Detect: the `hotshot` workflow (macOS build and `brew test`) or `Tap CI`
   fails on `main`, or users report the installed binary misbehaves.
2. Revert the bump commit and open a PR against `main`:

   ```sh
   git switch -c revert-hotshot-<bad-tag> origin/main
   git revert --no-edit <bad-merge-commit>
   git commit --amend -s --no-edit
   git push origin HEAD
   ```

3. Wait for `Tap CI` and the `hotshot` workflow to pass, then merge (needs a
   maintainer). The restored `url` points at an earlier upstream tag, which
   stays downloadable as long as upstream does not delete it; confirm with
   `curl -sIL <restored-url>` returning 200.
4. Users who already installed the bad version have a higher version than the
   restored formula, so `brew upgrade` will not downgrade them:

   ```sh
   brew update
   brew reinstall hivecommons/hive/hotshot
   ```

If the bad tag is upstream's fault, fix or re-tag upstream and bump forward
using the checklist in [`Formula/README.md`](../Formula/README.md#hand-maintained-formulae-hotshotrb).
Record the incident with [postmortem-template.md](postmortem-template.md).
