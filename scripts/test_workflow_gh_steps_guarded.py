"""Gate: every workflow step that writes to GitHub through `gh` has a test.

The inline shell in this tap's workflows is where its GitHub side effects
live: approving held runs, opening and closing tracking issues, publishing
release assets, committing generated formulae. Four times now a branch of one
of those steps was found untested only after it misbehaved (the stale-PR
sweep fixed in #179, the SIF manifest contract in #278, the ok-to-test trust
chain in #309, the tracking-issue steps in test_tracking_issue_steps.py), so
this test makes the rule mechanical: a `run: |` step that invokes `gh` must be
exercised by a test under scripts/ that extracts it from the workflow, which
the test shows by naming both the workflow file and the step.

Steps that predate the gate and have no test yet are listed in BASELINE.
That list may only shrink: add the test, delete the entry. A new `gh` step
added without a test fails here with the names it needs to appear under.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
TESTS = REPO_ROOT / "scripts"
THIS_FILE = Path(__file__).resolve()

# (workflow file, step name) pairs known to be unguarded when the gate landed.
# Shrink only. Each entry is a step whose shell has never run outside GitHub.
BASELINE = {
    ("convert.yml", "Check for existing release"),
    ("convert.yml", "Publish release assets"),
    ("convert.yml", "Commit generated formula"),
    ("convert.yml", "Release held Tap CI run on the generated PR"),
}

GH_INVOCATION = re.compile(r"(^|[\s(`$;|&])gh\s", re.M)


def run_steps(workflow: Path) -> list[tuple[str, str]]:
    """Return (step name, run body) for every `run: |` step in the workflow.

    Hand-rolled on purpose: PyYAML is not a dependency of this tap, and the
    other workflow tests already locate steps the same way (indentation and
    `- name:`), so a workflow this parser cannot read would already have
    broken them.
    """
    lines = workflow.read_text().split("\n")
    starts = [i for i, line in enumerate(lines) if re.match(r"\s+- name: ", line)]
    steps = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        indent = len(lines[start]) - len(lines[start].lstrip())
        for j in range(start + 1, end):
            line = lines[j]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                end = j
                break
        name = lines[start].split("- name: ", 1)[1].strip()
        body = "\n".join(lines[start + 1 : end])
        run = re.search(r"^\s+run: \|\n(.*)", body, re.S | re.M)
        if run:
            steps.append((name, run.group(1)))
    return steps


def gh_steps() -> set[tuple[str, str]]:
    found = set()
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for name, body in run_steps(workflow):
            if GH_INVOCATION.search(body):
                found.add((workflow.name, name))
    return found


def guarded_steps() -> set[tuple[str, str]]:
    """Steps some test names together with their workflow file."""
    candidates = gh_steps()
    guarded = set()
    for test in TESTS.glob("test_*.py"):
        if test.resolve() == THIS_FILE:
            continue
        text = test.read_text()
        for workflow, name in candidates:
            if workflow in text and name in text:
                guarded.add((workflow, name))
    return guarded


class WorkflowGhStepsGuardedTests(unittest.TestCase):
    def test_parser_sees_the_steps_the_other_tests_rely_on(self):
        """If this parser silently found nothing, the gate would pass vacuously."""
        steps = gh_steps()
        self.assertIn(("hive-ok-to-test.yml", "Approve held trusted same-repo workflow runs"), steps)
        self.assertIn(("convert-freshness.yml", "Open or update the tracking issue when stale, close it when fresh"), steps)
        self.assertGreaterEqual(len(steps), 9)

    def test_every_gh_step_is_guarded_or_in_the_baseline(self):
        unguarded = gh_steps() - guarded_steps() - BASELINE
        self.assertEqual(
            unguarded,
            set(),
            "\n".join(
                [
                    "workflow steps invoke `gh` but no scripts/test_*.py names both the workflow",
                    "file and the step (extract the step's shell and test it, as",
                    "test_ok_to_test_workflow.py and test_tracking_issue_steps.py do):",
                ]
                + [f"  {workflow}: {name}" for workflow, name in sorted(unguarded)]
            ),
        )

    def test_baseline_only_shrinks(self):
        """An entry that gained a test, or whose step is gone, must be removed."""
        stale = {entry for entry in BASELINE if entry not in gh_steps() or entry in guarded_steps()}
        self.assertEqual(stale, set(), f"remove from BASELINE (now tested or no longer a gh step): {sorted(stale)}")


if __name__ == "__main__":
    unittest.main()
