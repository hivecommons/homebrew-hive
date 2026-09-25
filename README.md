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
  Apptainer template (`limactl create --name=apptainer template://apptainer`).
  The wrapper defaults to Docker or Podman if available and supports
  `HIVE_CONTRIBUTE_RUNTIME=lima` for operators who have created a Lima
  Apptainer VM. Caveat: the Lima path runs the pinned OCI image reference inside
  the VM rather than the local SIF asset unless the user shares the Homebrew
  Cellar into Lima.
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
- GitHub auth: `GH_TOKEN` (or `GITHUB_TOKEN`, copied to `GH_TOKEN` when needed),
  plus `~/.config/gh`, `~/.gitconfig`, and read-only `~/.ssh` when present.
- Backend credentials/config: Claude, Copilot, Codex, Goose, Muse, Bob, OMP, Pi,
  Kilo, Gemini/Google, OpenAI, Anthropic, Azure, AWS, LiteLLM, Ollama, Groq, and
  xAI environment variables matching the wrapper allow-list, plus the common
  credential directories under `$HOME`.
- Workspace: `${HIVE_WORKSPACE_DIR:-$PWD}` is bound to `/home/dev/workspace` and
  exported as `HIVE_WORKSPACE_DIR` inside the container.

## Automation

`.github/workflows/convert.yml` runs every six hours, on manual dispatch, and on
repository dispatch from upstream promotion automation. It:

1. resolves `ghcr.io/hivecommons/hive-contributor:<channel>` to an immutable
   digest;
2. exits when the release for that digest already exists;
3. builds `amd64` and `arm64` SIF assets on native GitHub runners;
4. refuses assets at or above GitHub's 2 GB release-asset limit;
5. publishes a `contribute-<digest>` release (or `contribute-candidate-<digest>`);
6. regenerates the formula with per-arch URLs and SHA-256 values;
7. opens a PR for the generated formula.

The workflow pins third-party GitHub Actions by full commit SHA and uses only
`contents: write` / `pull-requests: write` permissions.

## Installing before a generated release lands

Use the from-source flow documented in the [hive README][hive] (`just
contribute-hive`). It remains supported after this tap lands — the tap is an
additional on-ramp, not a replacement.

[roadmap]: https://github.com/hivecommons/hive/blob/v5/docs/contribute-distribution-roadmap.md
[hive]: https://github.com/hivecommons/hive
[i6635]: https://github.com/hivecommons/hive/issues/6635
