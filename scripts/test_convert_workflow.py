"""Tests for the inline shell logic in .github/workflows/convert.yml.

The workflow cannot run locally, so these tests pull the exact jq filters out
of the workflow text, substitute the environment the shell would, and run them
through the real `jq` against fixture `gh pr list` output. They guard the
stale-PR sweep that once matched the candidate channel's long-lived branch
because `generated/contribute-candidate` starts with `generated/contribute-`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERT_YML = REPO_ROOT / ".github" / "workflows" / "convert.yml"

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


if __name__ == "__main__":
    unittest.main()
