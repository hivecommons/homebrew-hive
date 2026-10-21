# Runbook: the conversion pipeline has stalled

Use this when the tap is not picking up new `hive-contributor` images: no new
`generated/contribute` PR or `contribute-<digest12>` release appears after
upstream promoted a new `stable` image, or `Convert Hive contributor image`
runs are failing.

## Impact

Users keep receiving the last merged formula. Nothing breaks for them, but
fixes promoted upstream do not reach `brew install` / `brew upgrade` until the
pipeline recovers. Staleness grows silently because the workflow is the only
producer of formula updates.

## Detect

- The latest `Convert Hive contributor image` run on `main` is red, or the
  latest scheduled run is older than ~12 hours (cron is `17 */6 * * *`).
- `hive-contribute --wrapper-version` on a fresh install prints an `image=`
  digest that differs from the current upstream `stable` digest:

  ```sh
  docker buildx imagetools inspect ghcr.io/hivecommons/hive-contributor:stable
  ```

- GitHub disables scheduled workflows in repositories with no activity for 60
  days; a missing run history then means the schedule is off, not failing.

## Triage

1. List recent runs and open the newest failure:

   ```sh
   gh run list --repo hivecommons/homebrew-hive --workflow convert.yml --limit 10
   gh run view <run-id> --repo hivecommons/homebrew-hive --log-failed
   ```

2. Match the failing job:

   | Failing job / step | Likely cause | Action |
   |---|---|---|
   | `resolve` / "could not resolve digest" | `stable` or `candidate` tag missing or GHCR unavailable | Check the tag upstream; re-run once GHCR recovers. Fix the channel upstream if it was removed. |
   | `build` / Install Apptainer | PPA or apt mirror outage | Re-run the failed jobs. |
   | `build` / Build SIF | Image cannot be pulled or converted (one arch missing) | Confirm the upstream manifest lists both `linux/amd64` and `linux/arm64`. |
   | `publish` / release assets | A partial release exists for this digest | Re-run with `force=true` (below). |
   | Generate / smoke formula | `scripts/generate-formula.py` or wrapper template regression | Reproduce locally with `python3 scripts/test_generate_formula.py`, then fix on a branch. |
   | Commit step / `gh pr` | Token permissions or branch protection | Check the repository's Actions permissions; a maintainer must adjust them. |

3. If the schedule is silently disabled, re-enable it in the Actions tab (or
   any push or manual dispatch to `convert.yml` resets the 60-day timer).

## Recover

Re-run the failed run first. If the release for the digest already exists but
no PR was produced, or assets are incomplete, force a rebuild:

```sh
gh workflow run convert.yml --repo hivecommons/homebrew-hive \
  -f channel=stable -f force=true
```

Do not use `force=true` while upstream `stable` points at a known-bad digest;
follow [rollback.md](rollback.md) first.

The workflow keeps one long-lived branch per channel
(`generated/contribute`, `generated/contribute-candidate`) and force-pushes it,
so a re-run updates the existing PR rather than opening a new one. Review and
merge the PR as usual (needs a maintainer).

## Verify

- The newest `Convert Hive contributor image` run is green.
- The `generated/contribute` PR references the current upstream `stable`
  digest and `Tap CI` passes on it.
- After merge: `brew update && brew upgrade hivecommons/hive/contribute &&
  hive-contribute --wrapper-version` prints the expected `image=` digest.

## Follow-up

If the pipeline was down for more than a day, record the window and cause in an
issue using [postmortem-template.md](postmortem-template.md).
