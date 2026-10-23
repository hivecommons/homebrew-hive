# Postmortem template

Copy this file into an issue on this repository after any formula that reached
`main` and installed a broken, wrong, or unwanted image, and after any near
miss where `Tap CI` did not catch a bad generated formula. Keep it blameless:
describe what the system allowed, not who merged the change.

Do not paste tokens, registry credentials, or unreviewed workflow logs.

## Summary

One or two sentences: which formula (`contribute` or `contribute-candidate`)
was affected, and how long the bad digest was live on `main`.

## Impact

- Who was affected: users who ran `brew install` or `brew upgrade` while the
  bad formula was on `main`. Already-installed copies are unaffected until
  upgraded.
- Symptom, for example a failing `hive-contribute --help`, an unexpected
  `hive-contribute --wrapper-version` `image=` digest, or a SHA-256 mismatch.
- Bad digest and the previous known-good digest.

## Timeline

| When (UTC) | Event |
|---|---|
| | Upstream image promoted to the channel |
| | `convert.yml` generated the formula PR (the long-lived `generated/contribute` branch, title `contribute-<digest12>`) |
| | Formula PR merged to `main` |
| | First report or first red `Tap CI` run |
| | Cause identified |
| | Rollback merged ([rollback.md](rollback.md)) |

## Cause

What changed, and why `Tap CI` (`brew audit`, `brew install`,
`hive-contribute --help`, `brew test`) did not catch it.

## What went well / what did not

- Detection: was the failure found by CI, a user report, or an upstream notice?
- Recovery: did [rollback.md](rollback.md) work as written? Was Option A or
  Option B used, and was upstream `stable` fixed so the next six-hourly
  conversion did not re-introduce the digest?

## Follow-ups

Each item needs an owner and a linked issue. Prefer a CI or
`scripts/generate-formula.py` check over a documentation-only fix.

- [ ] Check added to `.github/workflows/ci.yml` or `scripts/generate-formula.py`
- [ ] Runbook updated where a step was missing or wrong
