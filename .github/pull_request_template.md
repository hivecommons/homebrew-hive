## Summary

<!-- What does this PR change, and why? Name the formula(e) it affects: `contribute` (generated) or a hand-maintained formula (`hotshot`, `crux`). -->

Fixes #<!-- issue number, if this PR resolves one -->

## Validation

<!-- Which checks did you run, and on which OS? If you could not run a macOS-only check, say so. -->

## Checklist

See [Contributing](https://github.com/hivecommons/homebrew-hive#contributing) and [`Formula/README.md`](https://github.com/hivecommons/homebrew-hive/blob/main/Formula/README.md) for the exact commands.

- [ ] `Formula/contribute*.rb` is not edited by hand; generated-formula changes go in `scripts/generate-formula.py`, `scripts/contribute-wrapper.sh.in` or `.github/workflows/convert.yml`
- [ ] Generator or wrapper changes pass `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
- [ ] Hand-maintained formula changes pass the `brew style`, `brew audit`, `brew install` and `brew test` steps of that formula's checklist in `Formula/README.md` (`hotshot` on macOS; `crux` on macOS or Linux)
- [ ] A new hand-maintained formula is added to the ownership table in `Formula/README.md`
- [ ] This PR does not push to the generated `generated/contribute*` branches
- [ ] Commits are signed off (`git commit -s`)
