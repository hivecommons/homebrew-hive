"""Tests for the inline shell logic in .github/workflows/convert.yml.

The workflow cannot run locally, so these tests pull the exact jq filters out
of the workflow text, substitute the environment the shell would, and run them
through the real `jq` against fixture `gh pr list` output. They guard the
stale-PR sweep that once matched the candidate channel's long-lived branch
because `generated/contribute-candidate` starts with `generated/contribute-`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERT_YML = REPO_ROOT / ".github" / "workflows" / "convert.yml"
GENERATOR = REPO_ROOT / "scripts" / "generate-formula.py"

CHANNEL_BRANCHES = ("generated/contribute", "generated/contribute-candidate")


def stale_sweep_filter() -> str:
    """Return the --jq filter of the stale-PR sweep, still holding ${FORMULA}."""
    text = CONVERT_YML.read_text()
    match = re.search(
        r'gh pr list --state open --json number,headRefName \\\n\s*--jq "(.*?)" \|\n',
        text,
    )
    if not match:
        raise AssertionError("stale-PR sweep `gh pr list --jq` not found in convert.yml")
    # The filter sits inside a double-quoted shell string: undo the escaping
    # the shell removes before jq sees it.
    return match.group(1).replace('\\"', '"')


def render_filter(formula: str) -> str:
    rendered = stale_sweep_filter().replace("${FORMULA}", formula)
    if "${" in rendered:
        raise AssertionError(f"unexpanded shell variable left in jq filter: {rendered}")
    return rendered


def run_jq(jq_filter: str, prs: list[dict]) -> list[int]:
    proc = subprocess.run(
        ["jq", "-r", jq_filter],
        input=json.dumps(prs),
        capture_output=True,
        text=True,
        check=True,
    )
    return [int(line) for line in proc.stdout.split()]


def pr_list(*heads: str) -> list[dict]:
    return [{"number": i + 1, "headRefName": head} for i, head in enumerate(heads)]


@unittest.skipUnless(shutil.which("jq"), "jq not installed")
class StaleSweepFilterTests(unittest.TestCase):
    def test_matches_only_legacy_per_tag_branches(self):
        prs = pr_list(
            "generated/contribute-8d0610f72958",
            "generated/contribute-0123456789ab",
            "generated/contribute",
            "generated/contribute-candidate",
            "generated/contribute-candidate-8d0610f72958",
            "generated/contribute-8d0610f7295",      # 11 hex
            "generated/contribute-8d0610f729580",    # 13 hex
            "generated/contribute-8D0610F72958",     # upper case
            "generated/contribute-8d0610f72958-wip",
            "feature/contribute-8d0610f72958",
            "generated/crux-8d0610f72958",
        )
        self.assertEqual(run_jq(render_filter("contribute"), prs), [1, 2])

    def test_stable_sweep_never_closes_a_channel_branch(self):
        prs = pr_list(*CHANNEL_BRANCHES)
        self.assertEqual(run_jq(render_filter("contribute"), prs), [])

    def test_candidate_sweep_leaves_stable_per_tag_branches_alone(self):
        prs = pr_list(
            "generated/contribute-8d0610f72958",
            "generated/contribute-candidate-8d0610f72958",
            "generated/contribute-candidate",
            "generated/contribute",
        )
        self.assertEqual(run_jq(render_filter("contribute-candidate"), prs), [2])

    def test_no_open_prs_yields_nothing(self):
        self.assertEqual(run_jq(render_filter("contribute"), []), [])

    def test_filter_is_anchored(self):
        jq_filter = stale_sweep_filter()
        self.assertIn('test("^generated/${FORMULA}-', jq_filter)
        self.assertIn('$")', jq_filter)
        self.assertNotIn("startswith", jq_filter)


def prune_step() -> str:
    """Return the YAML text of the 'Prune old generated releases' step."""
    text = CONVERT_YML.read_text()
    match = re.search(r"- name: Prune old generated releases\n(.*?)\n      - name: ", text, re.S)
    if not match:
        raise AssertionError("'Prune old generated releases' step not found in convert.yml")
    return match.group(1)


def prune_step_script() -> str:
    match = re.search(r"\n        run: \|\n(.*)\Z", prune_step(), re.S)
    if not match:
        raise AssertionError("prune step has no `run: |` block")
    return textwrap.dedent(match.group(1))


def run_prune_step(**env: str) -> list[str]:
    """Run the step's shell with ./scripts/prune-releases.py stubbed; return the argv it received."""
    with tempfile.TemporaryDirectory() as tmp:
        scripts = Path(tmp) / "scripts"
        scripts.mkdir()
        stub = scripts / "prune-releases.py"
        stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        stub.chmod(0o755)
        proc = subprocess.run(
            ["bash", "-c", prune_step_script()],
            cwd=tmp,
            env={**os.environ, "GITHUB_REPOSITORY": "o/r", "KEEP": "30", "MIN_AGE_DAYS": "14",
                 "TAG": "contribute-0123456789ab", "PRUNE": "", **env},
            capture_output=True,
            text=True,
            check=True,
        )
    return proc.stdout.splitlines()


class PruneStepTests(unittest.TestCase):
    """The prune step is the only place the workflow can delete releases."""

    def test_step_never_blocks_publication(self):
        self.assertIn("continue-on-error: true", prune_step())

    def test_delete_requires_variable_to_be_exactly_true(self):
        for value in ("", "false", "True", "TRUE", "yes", "1", " true"):
            with self.subTest(PRUNE=repr(value)):
                self.assertNotIn("--delete", run_prune_step(PRUNE=value))
        self.assertIn("--delete", run_prune_step(PRUNE="true"))

    def test_current_tag_is_always_protected(self):
        for value in ("", "true"):
            args = run_prune_step(PRUNE=value, TAG="contribute-feedfacecafe")
            self.assertIn("--protect-tag", args)
            self.assertEqual(args[args.index("--protect-tag") + 1], "contribute-feedfacecafe")

    def test_repo_and_retention_knobs_are_forwarded(self):
        args = run_prune_step(KEEP="5", MIN_AGE_DAYS="3")
        self.assertEqual(args[:6], ["--repo", "o/r", "--keep", "5", "--min-age-days", "3"])

    def test_retention_variables_default_when_unset(self):
        step = prune_step()
        self.assertIn("KEEP: ${{ vars.CONTRIBUTE_RELEASE_KEEP || '30' }}", step)
        self.assertIn("MIN_AGE_DAYS: ${{ vars.CONTRIBUTE_RELEASE_MIN_AGE_DAYS || '14' }}", step)
        self.assertIn("PRUNE: ${{ vars.CONTRIBUTE_RELEASE_PRUNE }}", step)


def step_script(name: str) -> str:
    """Return the dedented `run: |` shell of the named step in convert.yml."""
    text = CONVERT_YML.read_text()
    match = re.search(rf"- name: {re.escape(name)}\n(.*?)\n        run: \|\n(.*?)(?=\n      - name: |\n  \w)", text, re.S)
    if not match:
        raise AssertionError(f"step {name!r} with a `run: |` block not found in convert.yml")
    return textwrap.dedent(match.group(2))


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_formula", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SifManifestContractTests(unittest.TestCase):
    """The formula's top-level `url`/`sha256` point at the `<asset>.sha256`
    file the build job writes, and `generate-formula.py` predicts that file's
    digest from the SIF digest alone. Both halves must agree byte for byte or
    every `brew install` fails checksum verification, so run the workflow's
    real shell against a fixture SIF and compare it with the generator."""

    def write_manifest_like_workflow(self, tmp: Path, arch: str, payload: bytes) -> tuple[str, str]:
        """Run the build step's manifest line and the publish step's digest
        extraction exactly as convert.yml spells them; return (manifest, digest)."""
        build = step_script("Build SIF from pinned image digest")
        manifest_lines = [line for line in build.splitlines() if "sha256sum" in line]
        self.assertEqual(len(manifest_lines), 1, build)
        (manifest_line,) = manifest_lines
        asset_line = next(line for line in build.splitlines() if line.startswith("asset="))

        (tmp / f"hive-contributor-{arch}.sif").write_bytes(payload)
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", asset_line + "\n" + manifest_line],
            cwd=tmp,
            env={**os.environ, "ARCH": arch},
            check=True,
            capture_output=True,
        )

        publish = step_script("Generate formula")
        cut_line = next(line for line in publish.splitlines() if line.startswith(f"{arch[:3]}_sha="))
        # The publish step reads from dist/, where the artifact download lands.
        (tmp / "dist").mkdir(exist_ok=True)
        manifest_name = f"hive-contributor-{arch}.sif.sha256"
        shutil.copy(tmp / manifest_name, tmp / "dist" / manifest_name)
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", cut_line + f"\nprintf '%s' \"${arch[:3]}_sha\""],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=True,
        )
        return (tmp / manifest_name).read_text(), proc.stdout

    def test_generator_predicts_the_manifest_the_workflow_uploads(self):
        gen = load_generator()
        for arch, payload in (("amd64", b"amd64 sif bytes\n"), ("arm64", b"\x00arm64\xff")):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as tmp:
                manifest, digest = self.write_manifest_like_workflow(Path(tmp), arch, payload)
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
                url = f"https://github.com/o/r/releases/download/contribute-0123456789ab/hive-contributor-{arch}.sif"
                self.assertEqual(
                    gen.sha256_file_digest(digest, url),
                    hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
                    f"generate-formula.py predicts a different .sha256 file than convert.yml writes: {manifest!r}",
                )

    def test_manifest_url_names_the_uploaded_release_asset(self):
        publish = step_script("Generate formula")
        build = step_script("Build SIF from pinned image digest")
        text = CONVERT_YML.read_text()
        for arch in ("amd64", "arm64"):
            with self.subTest(arch=arch):
                # --<arch>-url must end in the SIF asset name so the formula's
                # `url "<sif-url>.sha256"` is exactly the manifest uploaded below.
                self.assertIn(f'--{arch}-url "https://github.com/${{GITHUB_REPOSITORY}}/releases/download/${{TAG}}/hive-contributor-{arch}.sif"', publish)
                self.assertIn(f"hive-contributor-${{{{ matrix.arch }}}}.sif.sha256", text)
        self.assertIn('asset="hive-contributor-${ARCH}.sif"', build)
        self.assertIn("gh release upload \"$TAG\" dist/*.sif dist/*.sha256", text)


if __name__ == "__main__":
    unittest.main()
