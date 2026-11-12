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


def run_steps_from_text(text: str) -> list[tuple[str, str]]:
    """Return (step name, run body) for every `run:` step in the workflow text.

    Accepts any `run:` scalar form: block scalars (`run: |`, `run: |-`, `run: |+`,
    `run: >`, `run: >-`, `run: >+`) and plain/quoted single-line scalars
    (`run: gh pr comment ...`, `run: "gh ..."`, `run: 'gh ...'`).

    Hand-rolled on purpose: PyYAML is not a dependency of this tap, and the
    other workflow tests already locate steps the same way (indentation and
    `- name:`), so a workflow this parser cannot read would already have
    broken them.
    """
    lines = text.split("\n")
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
        
        # Try block scalar form: `run: [|>][-+]?\s*\n`
        run = re.search(r"^\s+run: [|>][-+]?\s*\n(.*)", body, re.S | re.M)
        if run:
            steps.append((name, run.group(1)))
        else:
            # Try single-line form: `run: (?![|>])...` (not a block scalar marker)
            run = re.search(r"^\s+run: (?![|>])(.+)$", body, re.M)
            if run:
                # Strip surrounding quotes if present
                line_body = run.group(1).strip()
                if (line_body.startswith('"') and line_body.endswith('"')) or \
                   (line_body.startswith("'") and line_body.endswith("'")):
                    line_body = line_body[1:-1]
                steps.append((name, line_body))
    return steps


def run_steps(workflow: Path) -> list[tuple[str, str]]:
    """Return (step name, run body) for every `run:` step in the workflow.

    Wrapper around run_steps_from_text for file-based access.
    """
    return run_steps_from_text(workflow.read_text())


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
    def test_parser_reads_every_run_scalar_form(self):
        r"""Parser recognizes `run:` in all YAML scalar forms: block and single-line.

        The old regex `^\s+run: \|\n(.*)` only matched bare `run: |` followed by
        a newline. This test feeds a synthetic workflow with every form (bare block,
        block with chomping indicators, folded block, and single-line plain/quoted),
        each invoking `gh`, plus one non-gh step, and asserts:
          - run_steps_from_text returns all gh steps (not just the bare `|`).
          - each gh step body matches GH_INVOCATION.
          - the non-gh step body does not match GH_INVOCATION.
        This test fails with the old regex (finds only 1 of 7 steps).
        """
        synthetic_workflow = """
        - name: Run with bare block
          run: |
            gh pr comment 1 --body "bare block"
        - name: Run with block strip
          run: |-
            gh pr comment 1 --body "block strip"
        - name: Run with block keep
          run: |+
            gh pr comment 1 --body "block keep"
        - name: Run with folded block
          run: >
            gh pr comment 1 --body "folded block"
        - name: Run with folded strip
          run: >-
            gh pr comment 1 --body "folded strip"
        - name: Run with plain inline
          run: gh pr comment 1 --body "plain inline"
        - name: Run with double-quoted inline
          run: "gh pr comment 1 --body \"double-quoted inline\""
        - name: Run with single-quoted inline
          run: 'gh pr comment 1 --body "single-quoted inline"'
        - name: Non-gh step
          run: echo "not a gh step"
"""
        steps = run_steps_from_text(synthetic_workflow)
        
        # Should find all 9 steps.
        self.assertEqual(len(steps), 9)
        
        # Check each step name matches what we expect.
        expected_names = [
            "Run with bare block",
            "Run with block strip",
            "Run with block keep",
            "Run with folded block",
            "Run with folded strip",
            "Run with plain inline",
            "Run with double-quoted inline",
            "Run with single-quoted inline",
            "Non-gh step",
        ]
        actual_names = [name for name, _ in steps]
        self.assertEqual(actual_names, expected_names)
        
        # First 8 steps invoke gh (should match GH_INVOCATION).
        for i in range(8):
            name, body = steps[i]
            self.assertTrue(
                GH_INVOCATION.search(body),
                f"Step {i} ({name!r}) should invoke gh, but body is {body!r}"
            )
        
        # Last step does not invoke gh.
        name, body = steps[8]
        self.assertFalse(
            GH_INVOCATION.search(body),
            f"Step {name!r} should not invoke gh, but body is {body!r}"
        )

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
