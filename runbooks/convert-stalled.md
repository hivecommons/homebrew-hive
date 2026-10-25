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
- A scheduled failure opens a `Convert pipeline failing` issue.
- The daily `convert freshness` workflow opens a `Convert pipeline stale`
  issue when no scheduled run started in the last ~12 hours (see
  [Automated detection](#automated-detection)).
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
   | `publish` / Validate generated formula like Tap CI (`brew is not on the runner image`, `brew tap`, or `brew install` download) | Runner image dropped Homebrew (the step never bootstraps it from a remote script because this job holds a write token), or a network/GitHub outage while tapping or fetching the just-published SIF | Re-run with `force=true` (below). The release already exists, so "Re-run all jobs" and the next cron run skip it as "exists", while "Re-run failed jobs" reuses the stale `exists=false` and fails at "Publish release assets" with "refusing to clobber". |
   | `publish` / Validate generated formula like Tap CI (`brew style`, `brew audit --strict --new`, `brew install --build-from-source`, `<binary> --help`, `brew test`) | Generated formula or wrapper regression that `ruby -c` did not catch | Reproduce locally: `brew tap hivecommons/hive <checkout>`, then `brew style`, `brew audit --strict --new hivecommons/hive/contribute`, `brew install --build-from-source hivecommons/hive/contribute`, `brew test hivecommons/hive/contribute`. Fix `scripts/generate-formula.py` or `scripts/contribute-wrapper.sh.in` on a branch; the push to `main` reruns with `force` semantics. |
   | `resolve`, `build`, `publish`, or `notify-failure` / "The job running on runner ... has exceeded the maximum execution time of N minutes" | The job exceeded its `timeout-minutes` and was cancelled (`resolve` and `notify-failure` 10m, `build` 45m, `publish` 30m) | `build`: re-run the failed jobs; transient runner slowness often resolves. `publish`: re-run with `force=true` (below), because the release assets are usually already uploaded and "Re-run failed jobs" would fail with "refusing to clobber". If a job consistently exceeds the limit, raise its `timeout-minutes` in `convert.yml`. |
   | Commit step / `gh pr` | Token permissions or branch protection | Check the repository's Actions permissions; a maintainer must adjust them. |
   | `publish` / Release held Tap CI run (`::warning::no action_required run appeared`) or the generated PR shows `Tap CI` as "action required" | GitHub held the PR's `Tap CI` run because the author is `github-actions[bot]`, and neither the self-release step nor `hive-ok-to-test.yml` approved it | See [Held Tap CI on generated PRs](#held-tap-ci-on-generated-prs). |

3. If the schedule is silently disabled, re-enable it in the Actions tab (or
   any push or manual dispatch to `convert.yml` resets the 60-day timer).

## Recover

Re-run the failed run first. If the release for the digest already exists but
no PR was produced (including when the formula validation step failed after
the release was published), or assets are incomplete, force a rebuild:

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
  digest, the "Validate generated formula like Tap CI" step of the Convert
  run that pushed it is green, and the PR's own `Tap CI` check is green (not
  "action required"; see [Held Tap CI on generated PRs](#held-tap-ci-on-generated-prs)).
- After merge: `brew update && brew upgrade hivecommons/hive/contribute &&
  hive-contribute --wrapper-version` prints the expected `image=` digest.

## Held Tap CI on generated PRs

GitHub creates the `pull_request` `Tap CI` run for every PR that `convert.yml`
opens, but holds it in `action_required` because the PR author is
`github-actions[bot]` (the workflow pushes and opens the PR with
`github.token`). Prow's `tide` will not merge without the check, and on this
repository `/ok-to-test` belongs to Prow, which only honours it from trusted
users and rejects Hive's `hivecommons-hive[bot]`; Hive then stops with
`<!-- hive-ok-to-test-rejected -->` and asks for a human. #110 and #144 stalled
on this.

Two mechanisms now release the held run without a human:

1. **`convert.yml` self-release.** After the `publish` job pushes the branch
   and opens or updates the PR, its "Release held Tap CI run on the generated
   PR" step (job permission `actions: write`) polls for up to two minutes for
   `status=action_required` runs on exactly the head SHA it pushed and
   `POST /actions/runs/{id}/approve`s them. This is safe because the same job
   already ran `brew style`, `brew audit --strict --new`, `brew install
   --build-from-source` and `brew test` on that formula.
2. **`.github/workflows/hive-ok-to-test.yml`** (fallback). Hive's
   self-contained ok-to-test workflow, rendered from `hivectl
   ok-to-test-template`. When `hivecommons-hive[bot]` (or anyone with write)
   comments exactly `/ok-to-test` on a same-repository PR, the repository
   `GITHUB_TOKEN` approves that head's held runs. Besides the template's
   default trusted authors (`dependabot[bot]`, `renovate[bot]`, the Hive App),
   it trusts `github-actions[bot]` **only when the head branch starts with
   `generated/`**; it never approves fork heads or PRs labelled
   `sentinel-alert`. Prow will still post its own rejection comment for Hive's
   `/ok-to-test`; that is noise, the workflow run is what matters. Re-render
   from the hive template when it changes, keeping the `GENERATED_AUTHORS` /
   `GENERATED_BRANCH_PREFIX` addition.

GitHub creates no `pull_request` run at all (held or otherwise) for a PR that
conflicts with `main` (`needs-rebase`); the self-release step reports this
case separately. It only happens when `Formula/contribute.rb` was changed on
`main` outside the pipeline, or when `convert.yml` was dispatched from a stale
branch: the next run from `main` recreates `generated/contribute` from
`main`'s HEAD and clears it. Always dispatch `convert.yml` from `main`; a
dispatch from a feature branch that touches `.github/workflows/` also makes
the publish push fail with `refusing to allow a GitHub App to create or
update workflow ... without workflows permission` until the next run from
`main` recreates the branch.

If a generated PR still shows `Tap CI` as "action required":

```sh
gh run list --repo hivecommons/homebrew-hive --branch generated/contribute --limit 3
gh api -X POST repos/hivecommons/homebrew-hive/actions/runs/<run-id>/approve
```

then check why the self-release step warned (run log of the Convert run that
pushed the head) and whether `hive-ok-to-test.yml` ran on Hive's comment
(`gh run list --workflow hive-ok-to-test.yml`). The repository setting
`actions/permissions/fork-pr-contributor-approval` is already the least strict
(`first_time_contributors_new_to_github`); the hold is GitHub's policy for
PRs authored by `github-actions[bot]`, not the fork policy. Opening the PR
with a Hive App token (author `hivecommons-hive[bot]`) would avoid the hold
entirely, but this repository has no App credentials configured.

## Follow-up

If the pipeline was down for more than a day, record the window and cause in an
issue using [postmortem-template.md](postmortem-template.md).

## Automated detection

The `convert freshness` workflow (`.github/workflows/convert-freshness.yml`)
checks daily that a scheduled `convert.yml` run started within the last 12
hours (twice its 6-hour period). If not, it opens or updates an issue titled
`Convert pipeline stale`, and closes it at the next daily check that finds a
fresh scheduled run (so up to ~24 hours after recovery).

Limitation: the freshness workflow is itself schedule-triggered, so GitHub's
60-day inactivity disable turns it off together with `convert.yml` and no
issue is filed in that case. It does catch dropped or delayed runs, a manual
disable of `convert.yml`, and early-stage failures. The manual staleness check
in [Detect](#detect) remains the fallback for the inactivity case.
