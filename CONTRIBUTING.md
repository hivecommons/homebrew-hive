# Contributing to homebrew-hive

This is the Homebrew tap for Hive Commons. Open pull requests against
**`main`**, the default branch. Do not push to the `generated/contribute*`
branches; the conversion workflow force-pushes them. The `v4`/`v5` branch rules
in the org-wide
[Hive Commons contributing guide](https://github.com/hivecommons/.github/blob/main/CONTRIBUTING.md)
were written for `hivecommons/hive` and do not apply to this tap.

## What to change, and where

- `Formula/contribute*.rb` is **generated**. Do not edit it by hand. Change
  `scripts/generate-formula.py`, `scripts/contribute-wrapper.sh.in` or
  `.github/workflows/convert.yml` instead.
- `Formula/hotshot.rb` and `Formula/crux.rb` are hand-maintained and edited
  by pull request.

The full rules are in the README's [Contributing](README.md#contributing)
section and [`Formula/README.md`](Formula/README.md), which has the `brew`
checklist for each hand-maintained formula. Generator and wrapper changes
must pass the same tests CI runs:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

Sign off every commit (`git commit -s`) for the Developer Certificate of
Origin check.

## Finding something to work on

- [`good first issue`](https://github.com/hivecommons/homebrew-hive/labels/good%20first%20issue)
  and [`help wanted`](https://github.com/hivecommons/homebrew-hive/labels/help%20wanted)
  issues are ready to pick up. Comment on the issue before you start.
- Found a broken install or a stale formula? Use the
  [bug form](https://github.com/hivecommons/homebrew-hive/issues/new?template=bug_report.yml)
  or the [feature form](https://github.com/hivecommons/homebrew-hive/issues/new?template=feature_request.yml).
  Problems with the programs themselves go upstream; the
  [issue chooser](https://github.com/hivecommons/homebrew-hive/issues/new/choose)
  links each project.

## Questions

Ask on [Discord](https://hivecommons.dev/discord) or bring it to the biweekly
[Hive Commons community meeting](https://docs.hivecommons.dev/docs/community/meetings).

For review, governance and the AI-agent contribution policy, see the org-wide
[contributing guide](https://github.com/hivecommons/.github/blob/main/CONTRIBUTING.md).
