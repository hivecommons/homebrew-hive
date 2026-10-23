# homebrew-hive — the Homebrew tap for Hive

This tap ships the **Hive contribute app** as a one-command install:

```sh
brew install hivecommons/hive/contribute
hive-contribute
```

It exists so that contributing to a Hive does not require cloning a repository
first. The formula wraps the published `ghcr.io/hivecommons/hive-contributor`
container image, converted to a self-contained [Apptainer](https://apptainer.org)
SIF for Linux, with documented Docker/Podman/Lima fallbacks for platforms where
Apptainer is not native.

## Decisions recorded 2026-09-24

The two open Phase 2 inputs from [`hivecommons/hive#6635`][i6635] are resolved
for this tap:

1. **Binary name:** formula `contribute` (`brew install hivecommons/hive/contribute`)
   installs **`hive-contribute`**. The ClankeR nickname is intentionally not part
   of the installed command.
2. **Channel policy:** `contribute` tracks the **`stable`** image channel,
   resolved to an immutable digest when the formula is generated. The conversion
   workflow can also generate `contribute-candidate`, installing
   `hive-contribute-candidate`, from the `candidate` channel; it is labelled as
   pre-release and is not the default install path.

## Ownership contract

This tap is the downstream half of a two-repo split ratified in
[`hivecommons/hive` → `docs/contribute-distribution-roadmap.md`][roadmap]:

| Repo | Owns |
|---|---|
| [`hivecommons/hive`][hive] | the contributor OCI image `ghcr.io/hivecommons/hive-contributor`, published multi-arch by digest with immutable short-SHA tags plus `stable`, `candidate`, and `latest` channels; its size and reproducibility; documentation of the install path |
| **this repo** | the Apptainer conversion, the generated formulae, and the release automation that publishes them |

Upstream's only contract to this tap is **a stable image reference and
tag/digest discipline**. That precondition is satisfied, so the tap workflow can
pin `stable` by digest and convert that exact image.

The practical consequence: **`Formula/` is generated output.** If a formula is
wrong, fix `scripts/generate-formula.py` or `.github/workflows/convert.yml`, not
the generated artifact.

## Platform reality

- **Linux:** Apptainer runs natively on Linux. Homebrew-on-Linux has an
  `apptainer` formula, and `Formula/contribute.rb` depends on it. The wrapper
  runs the generated SIF with `apptainer run --containall --writable-tmpfs`,
  binds a workspace plus Hive/CLI credential directories, and forwards Hive,
  GitHub, and backend provider environment variables.
- **macOS:** Apptainer is not native; it needs a Linux VM. Lima has an
  Apptainer template (`limactl create --name=apptainer --mount-writable
  template://apptainer`).
  The wrapper defaults to Docker or Podman if available and supports
  `HIVE_CONTRIBUTE_RUNTIME=lima` for operators who have created a Lima
  Apptainer VM. Caveat: the Lima path runs the pinned OCI image reference inside
  the VM rather than the local SIF asset unless the user shares the Homebrew
  Cellar into Lima. It forwards the same environment (including the HTTPS git
  credential helper) and honours the same `HIVE_CONTRIBUTE_MOUNT_*` opt-ins as
  the Linux Apptainer path. This requires Lima to share your home directory
  into the VM at the same path **writable**: Lima's default home share is
  read-only, so create the VM with `--mount-writable` (or set
  `mounts: - location: "~"` / `writable: true` in the instance config);
  otherwise the workspace and state binds are read-only inside the VM.
- **Windows:** use WSL2 and the Linux path (`brew` on Linux + Apptainer), or run
  Docker/Podman manually with the pinned image digest from the formula caveats.
- **KVM/gVisor:** the earlier roadmap wording overstated this. Apptainer's
  normal SIF runtime does not auto-detect KVM or switch to gVisor. gVisor is
  available only through an OCI runtime such as Docker/Podman configured with
  `runsc`; set `HIVE_CONTRIBUTE_RUNTIME=gvisor` to ask the wrapper to pass
  `--runtime=runsc`. Any KVM/platform choice is controlled by the host's gVisor
  configuration, not by this tap. The fallback is Apptainer on Linux, then
  Docker/Podman/Lima on macOS.

## Runtime inputs passed through

The wrapper forwards the inputs the contributor relay needs:

- Hive registration and routing: `HIVE_HUB`, `HIVE_REGISTRATION_TOKEN`,
  `HIVE_SESSION`, `HIVE_AGENT_ROLE`, and other `HIVE_*` variables.
- Backend choice: `AGENT_BACKEND`, `AGENT_MODEL`, `AGENT_REASONING_EFFORT`, and
  `CONTRIBUTOR_MODE`.
- GitHub auth: `GH_TOKEN` (or `GITHUB_TOKEN`, copied to `GH_TOKEN` when needed)
  and read-only `~/.gitconfig` when present. Git inside the container uses HTTPS
  with the forwarded token through an env-configured credential helper
  (`GIT_CONFIG_*`); without a token, authenticated clones and pushes fail and
  the wrapper warns on stderr. `~/.ssh` and `~/.config/gh` are **not** mounted
  by default; opt in with `HIVE_CONTRIBUTE_MOUNT_SSH=1` (read-only `~/.ssh`)
  and/or `HIVE_CONTRIBUTE_MOUNT_GH=1` (`~/.config/gh`). A `~/.gitconfig`
  `insteadOf` rule that rewrites `https://github.com/` to SSH bypasses the
  helper and needs `HIVE_CONTRIBUTE_MOUNT_SSH=1`.
- Backend credentials/config: Claude, Copilot, Codex, Goose, Muse, Bob, OMP, Pi,
  Kilo, Gemini/Google, OpenAI, Anthropic, Azure, AWS, LiteLLM, Ollama, Groq, and
  xAI environment variables matching the wrapper allow-list, plus the common
  credential directories under `$HOME`.
- Workspace: `${HIVE_WORKSPACE_DIR:-$PWD}` is bound read-write to
  `/home/dev/workspace` and exported as `HIVE_WORKSPACE_DIR` inside the
  container. Because that bind would carry every credential directory under
  `$HOME` into the container, the wrapper refuses to start (exit 2) when the
  workspace resolves to `$HOME`, an ancestor of it, or `/` — for example when
  run from your home directory, or via `.`, `..` or a symlink that lands
  there. Run it from a project directory or set
  `HIVE_WORKSPACE_DIR`; `HIVE_CONTRIBUTE_ALLOW_HOME_WORKSPACE=1` overrides.

## Persistent state and wrapper flags

The wrapper creates these host directories as needed and mounts them read-write
across container runs (Apptainer, Docker/Podman, and Lima):

| Host override | Default | Container path |
|---|---|---|
| `HIVE_CONTRIBUTOR_CONFIG_DIR` | `~/.config/hive` | `/home/dev/.config/hive` (re-exported as `HIVE_CONTRIBUTOR_CONFIG_DIR` inside the container) |
| `HIVE_CONTRIBUTE_STATE_DIR` | `~/.local/state/hive/contribute` | `home/` → `/home/dev/.local/state/hive`; `metrics/` → `/var/run/hive-metrics` |

For example, to keep a separate contributor profile:

```sh
HIVE_CONTRIBUTOR_CONFIG_DIR="$HOME/.config/hive-profile" \
HIVE_CONTRIBUTE_STATE_DIR="$HOME/.local/state/hive/profile" \
hive-contribute
```

For Lima, these paths must also be shared into the VM at the same path and be
writable. Lima temporarily stores a mode-0600 `lima-env.*` file containing the
forwarded environment in the state directory and removes it when `limactl` exits.

These diagnostic flags do not launch the relay; pass each as the first argument:

- `hive-contribute --wrapper-version` prints the wrapper version, channel, and
  pinned image reference, then exits. The version is
  `<YYYYMMDD>.<HHMMSS>.<digest12>`: the UTC time the formula was generated,
  then the first 12 hex characters of the image digest. The time prefix makes
  every regeneration sort above the previous one, so `brew upgrade` also picks
  up wrapper changes published under an unchanged image digest.
- `hive-contribute --wrapper-print-runtime` prints the selected runtime, or
  `none` with exit status 1 when none is found. This is a selection diagnostic,
  not a runtime health check: Linux's automatic selection reports `apptainer`
  without checking that it is installed. It exits before creating any of the
  directories above. An unrecognised `HIVE_CONTRIBUTE_RUNTIME` value is
  rejected with exit status 2, the same as a real run.
- `hive-contribute --help` (or `-h`) prints wrapper usage.

## Automation

`.github/workflows/convert.yml` runs every six hours, on manual dispatch, on
repository dispatch from upstream promotion automation, and on pushes to `main`
that change the generator inputs (`scripts/generate-formula.py`,
`scripts/contribute-wrapper.sh.in`, or the workflow itself), so formula changes
are regenerated without waiting for the cron. Push runs behave like `force`:
they rebuild and republish the current stable release. It:

1. resolves `ghcr.io/hivecommons/hive-contributor:<channel>` to an immutable
   digest;
2. exits when the release for that digest already exists;
3. builds `amd64` and `arm64` SIF assets on native GitHub runners;
4. refuses assets at or above GitHub's 2 GB release-asset limit;
5. publishes a `contribute-<digest>` release (or `contribute-candidate-<digest>`);
6. regenerates the formula with per-arch URLs and SHA-256 values;
7. validates the generated formula with the same commands as `Tap CI`
   (`brew style`, `brew audit --strict --new`, `brew install
   --build-from-source`, `brew test`) against the just-published release;
8. opens a PR for the generated formula.

The workflow pins third-party GitHub Actions by full commit SHA and grants
write scopes per job: `contents: write` / `pull-requests: write` to the publish
job, and `issues: write` to the failure-notification job that opens, updates
and closes the "Convert pipeline failing" tracking issue.

## Testing the generator

`scripts/test_generate_formula.py` renders the formula with fixed inputs and
runs the embedded `hive-contribute` wrapper against stub `apptainer`, `docker`,
`podman` and `limactl` binaries; a stub `uname` reporting Darwin drives the
macOS `auto` dispatch (docker → podman → Lima) on Linux. It needs only Python 3
(the `ruby -c` case is skipped when Ruby is absent):

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

## Contributing

- Do not edit `Formula/contribute.rb` by hand; it is generated. Change
  `scripts/generate-formula.py`, `scripts/contribute-wrapper.sh.in`, or
  `.github/workflows/convert.yml` instead, and run the generator tests (see
  [Testing the generator](#testing-the-generator)) before opening a PR.
- Sign off every commit (`git commit -s`) to satisfy the Developer Certificate
  of Origin check.
- Generated formula PRs (`generated/contribute-*` branches) are opened by the
  conversion workflow; review them, do not push to them.

## Rollback

If a generated formula installs a bad image, follow
[`runbooks/rollback.md`](runbooks/rollback.md). If new upstream images are not
reaching the tap, follow [`runbooks/convert-stalled.md`](runbooks/convert-stalled.md).
After either incident, record it with
[`runbooks/postmortem-template.md`](runbooks/postmortem-template.md).

## Installing before a generated release lands

Use the from-source flow documented in the [hive README][hive] (`just
contribute-hive`). It remains supported after this tap lands — the tap is an
additional on-ramp, not a replacement.

[roadmap]: https://github.com/hivecommons/hive/blob/v5/docs/contribute-distribution-roadmap.md
[hive]: https://github.com/hivecommons/hive
[i6635]: https://github.com/hivecommons/hive/issues/6635
