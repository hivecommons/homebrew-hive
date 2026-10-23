# Formula/ — who owns which file

Homebrew reads exactly one formula directory per tap (`Formula/` when it
exists; `HomebrewFormula/` and the repository root are ignored once `Formula/`
is present), so every formula served as `brew install hivecommons/hive/<name>`
must live here. Ownership is therefore split **per file**, not per directory:

| File | Owner | How it changes |
|---|---|---|
| `contribute.rb` | generator | Rewritten by `.github/workflows/convert.yml` via `scripts/generate-formula.py` from the `stable` `ghcr.io/hivecommons/hive-contributor` digest. **Do not hand-edit.** |
| `contribute-candidate.rb` (when generated) | generator | Same pipeline, `candidate` channel, installs `hive-contribute-candidate`. **Do not hand-edit.** |
| `hotshot.rb` | hand-maintained | Edited by pull request. Builds [hivecommons/hotshot](https://github.com/hivecommons/hotshot) from its tagged source tarball. |
| `README.md` | hand-maintained | This file. |

The generator writes only `Formula/<formula>.rb` for the channel it is
converting, stages only that file, and `convert.yml` fails its run if anything
else under `Formula/` is modified ("Guard hand-maintained formulae" step).
Add new hand-maintained formulae to the table above.

## Generated formulae (`contribute*.rb`)

The formula `version` is `<YYYYMMDD>.<HHMMSS>.<digest12>` (UTC generation
time, then the image digest prefix). Homebrew only upgrades when the version
compares greater than the installed one, and digest strings do not sort in
promotion order, so the time prefix is what makes `brew upgrade` deliver both
new images and wrapper fixes regenerated under the same digest. Never emit a
bare digest or reuse a version for changed content.

If a generated formula is wrong, fix `scripts/generate-formula.py` or
`.github/workflows/convert.yml`; the next conversion run overwrites manual
edits to `contribute*.rb`.

## Hand-maintained formulae (`hotshot.rb`)

To bump `hotshot` to a new upstream tag `vX.Y.Z`:

1. Confirm the tag and GitHub Release exist upstream.
2. Compute the tarball checksum:
   `curl -sL https://github.com/hivecommons/hotshot/archive/refs/tags/vX.Y.Z.tar.gz | shasum -a 256`
3. Update `url` and `sha256` in `Formula/hotshot.rb`; adjust `depends_on`
   if `Package.swift` raised its tools version or platform floor.
4. Run `brew style --fix Formula/hotshot.rb`, then on macOS
   `brew tap hivecommons/hive "$PWD" && brew audit --strict --new hivecommons/hive/hotshot && brew install --build-from-source hivecommons/hive/hotshot && brew test hivecommons/hive/hotshot`.
5. Open a PR. `.github/workflows/hotshot.yml` repeats step 4 on a macOS
   runner; `Tap CI` styles and audits it on Linux.
