# homebrew-hive — the Homebrew tap for Hive

This tap ships the **Hive contribute app** as a one-command install:

```sh
brew install hivecommons/hive/contribute
```

It exists so that contributing to a Hive does not require cloning a repository
first. The formula wraps the published `hive-contributor` container image,
converted to a self-contained [Apptainer](https://apptainer.org) (the
LF-donated successor to Singularity) binary, so a contributor gets a working
relay from a single command on macOS and Linux.

> **Status: scaffolding. The formula is not yet published.**
> Phase 2 of the roadmap is deliberately blocked on Phase 0 — see
> [What this is waiting on](#what-this-is-waiting-on).

## Ownership contract

This tap is the downstream half of a two-repo split ratified in
[`hivecommons/hive` → `docs/contribute-distribution-roadmap.md`][roadmap]:

| Repo | Owns |
|---|---|
| [`hivecommons/hive`][hive] | the contributor OCI image `ghcr.io/hivecommons/hive-contributor`, published multi-arch by digest with immutable short-SHA tags plus a `candidate` channel; its size and reproducibility; documentation of the install path |
| **this repo** | the Apptainer conversion, the generated formula, and the release automation that publishes it |

Upstream's only contract to this tap is **a stable image reference and
tag/digest discipline**. That precondition is already satisfied, so no upstream
publishing changes are required for this tap to do its job.

The practical consequence: **the formula is generated, never hand-edited.**
`Formula/` is an output directory. A PR that edits a formula by hand is almost
certainly fixing the wrong thing — fix the generator instead.

## What this is waiting on

Distribution amplifies whatever first-run experience already exists, so the
roadmap gates publication on a first-run reliability gate. Publishing the
`brew` one-liner while the documented first command fails would widen a funnel
onto a broken first impression.

| Gate | Where | Blocks |
|---|---|---|
| Phase 0 — first-run reliability ([hive#6656][i6656]) | upstream | everything here |
| Phase 1 — distroless contributor image ([hive#6641][i6641]) | upstream | the digest this tap consumes |
| Phase 2 — this tap | here | the `brew` one-liner |

Two open questions must be answered upstream in [hive#6635][i6635] before the
first formula can be generated:

1. **Binary name** — `contribute`, `hive-contribute`, or `clanker`? It fixes
   the formula path and is not cheap to change once people have installed it.
2. **Channel policy** — does the formula track the `candidate` channel, or
   only tagged releases?

Question 3 from that list, *tap repo location and ownership*, is answered by
this repository existing: **`hivecommons`, not `kubestellar`.**

## Layout

```
Formula/          generated formulae (output — do not hand-edit)
```

Release automation lives in `.github/workflows/` once added; see
[hive#6635][i6635] for the conversion action's current status.

## Installing before the formula ships

There is nothing to install from this tap yet. Until it ships, use the
from-source flow documented in the [hive README][hive] (`just contribute-hive`),
which stays supported after the tap lands — the tap is an additional on-ramp,
not a replacement.

[roadmap]: https://github.com/hivecommons/hive/blob/v4/docs/contribute-distribution-roadmap.md
[hive]: https://github.com/hivecommons/hive
[i6635]: https://github.com/hivecommons/hive/issues/6635
[i6641]: https://github.com/hivecommons/hive/issues/6641
[i6656]: https://github.com/hivecommons/hive/issues/6656
