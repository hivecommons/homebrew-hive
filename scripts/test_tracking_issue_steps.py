"""Tests for the "tracking issue" steps shared by four workflows.

convert.yml, crux.yml and hotshot.yml each end in a notify-failure job that
keeps exactly one issue open while scheduled runs are red and closes it when
a later scheduled run is green; convert-freshness.yml does the same for the
convert.yml schedule itself going quiet. Each step is a hand-copied shell
block with the same five-way decision (create / comment / close / leave
alone / leave alone), and a copy that drifts fails silently: nobody is
watching a scheduled run's log. These tests pull each step's exact shell out
of its workflow, stub `gh` with fixture-backed responses that still run the
workflow's own --jq filters, and check which GitHub write each outcome makes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

REPO = "o/r"
RUN_URL = "https://github.com/o/r/actions/runs/4242"
NOTIFY_STEP = "Open or update the tracking issue on failure, close it on success"
FRESHNESS_STEP = "Open or update the tracking issue when stale, close it when fresh"

# Every write goes through the gh CLI; the stub answers the two reads from
# fixtures in $GH_STUB_DIR (applying the --jq filter with the real jq), accepts
# the three writes, and logs each argv so tests can assert what happened.
GH_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
# One record per call; issue bodies span lines, so newlines are escaped.
record=""
for arg in "$@"; do record+="${arg//$'\n'/\\n}"$'\x1f'; done
printf '%s\n' "$record" >>"$GH_STUB_DIR/calls.log"
case "${1:-} ${2:-}" in
  "issue list"|"run list")
    [[ "$1" == issue ]] && fixture=issues.json || fixture=runs.json
    filter=""
    shift 2
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --jq) filter="$2"; shift 2 ;;
        --search|--state|--json|--workflow|--event|--limit) shift 2 ;;
        *) echo "stub gh: unexpected list flag: $1" >&2; exit 97 ;;
      esac
    done
    file="$GH_STUB_DIR/$fixture"
    [[ -e "$file" ]] || { echo "stub gh: no fixture $fixture" >&2; exit 99; }
    jq -r "$filter" "$file" ;;
  "issue comment"|"issue create"|"issue close") exit 0 ;;
  *) echo "stub gh: unexpected subcommand: $*" >&2; exit 98 ;;
esac
"""


def step_script(workflow: str, name: str) -> str:
    text = (WORKFLOWS / workflow).read_text()
    match = re.search(
        rf"- name: {re.escape(name)}\n(.*?)        run: \|\n(.*?)(?=\n      - name: |\n  \w|\Z)",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"step {name!r} with a `run: |` block not found in {workflow}")
    return textwrap.dedent(match.group(2))


def step_literal_env(workflow: str, name: str) -> dict[str, str]:
    """Return the step's literal (non-expression) `env:` values."""
    text = (WORKFLOWS / workflow).read_text()
    match = re.search(rf"- name: {re.escape(name)}\n\s+env:\n(.*?)\n\s+run: \|", text, re.S)
    if not match:
        raise AssertionError(f"step {name!r} has no `env:` block in {workflow}")
    env = {}
    for line in match.group(1).splitlines():
        kv = re.match(r'\s+([A-Z_]+): "(.*)"$', line)
        if kv:
            env[kv.group(1)] = kv.group(2)
    return env


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


class Call:
    """One logged gh invocation, split back into argv."""

    def __init__(self, record: str):
        self.argv = record.rstrip("\x1f").split("\x1f")

    @property
    def action(self) -> str:
        return " ".join(self.argv[:2])

    def flag(self, name: str) -> str:
        return self.argv[self.argv.index(name) + 1]


@unittest.skipUnless(shutil.which("jq"), "jq not installed")
class TrackingIssueStepBase(unittest.TestCase):
    workflow = ""
    step = ""
    title = ""

    def setUp(self):
        if not self.workflow:
            self.skipTest("abstract base")
        self.tmp = Path(tempfile.mkdtemp(prefix="tracking-issue-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stub_dir = self.tmp / "stub"
        self.stub_dir.mkdir()
        gh = self.tmp / "bin" / "gh"
        gh.parent.mkdir()
        gh.write_text(GH_STUB)
        gh.chmod(0o755)
        self.bin = gh.parent
        self.fixture("issues.json", [])
        self.fixture("runs.json", [])

    def fixture(self, name: str, payload) -> None:
        (self.stub_dir / name).write_text(json.dumps(payload))

    def existing_issue(self, number: int = 31, title: str | None = None) -> None:
        self.fixture("issues.json", [{"number": number, "title": title or self.title}])

    def run_step(self, event: str = "schedule", **env_overrides: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            **step_literal_env(self.workflow, self.step),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GH_STUB_DIR": str(self.stub_dir),
            "GH_TOKEN": "stub",
            "GH_REPO": REPO,
            "RUN_URL": RUN_URL,
            "GITHUB_WORKFLOW": self.workflow,
            "GITHUB_EVENT_NAME": event,
            **env_overrides,
        }
        proc = subprocess.run(["bash", "-c", step_script(self.workflow, self.step)], env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def calls(self) -> list[Call]:
        log = self.stub_dir / "calls.log"
        return [Call(r) for r in log.read_text().splitlines()] if log.exists() else []

    def writes(self) -> list[Call]:
        return [c for c in self.calls() if c.action in ("issue create", "issue comment", "issue close")]

    def assert_only_write(self, action: str) -> Call:
        writes = self.writes()
        self.assertEqual([w.action for w in writes], [action])
        return writes[0]

    def assert_no_write(self) -> None:
        self.assertEqual([w.action for w in self.writes()], [])

    # -- shared contract -----------------------------------------------------

    def test_lookup_matches_the_title_exactly(self):
        """The --jq filter must not pick up an issue that merely contains the title."""
        self.fixture("issues.json", [{"number": 8, "title": f"{self.title} (old)"}, {"number": 9, "title": self.title}])
        self.failing()
        self.assertEqual(self.assert_only_write("issue comment").argv[2], "9")

    def test_failure_without_an_issue_creates_one_pointing_at_the_run(self):
        self.failing()
        call = self.assert_only_write("issue create")
        self.assertEqual(call.flag("--title"), self.title)
        self.assertIn(RUN_URL, call.flag("--body"))
        self.assertIn("runbooks/", call.flag("--body"), "the issue must point at its runbook")

    def test_failure_with_an_open_issue_comments_instead_of_duplicating(self):
        self.existing_issue(31)
        self.failing()
        call = self.assert_only_write("issue comment")
        self.assertEqual(call.argv[2], "31")
        self.assertIn(RUN_URL, call.flag("--body"))

    def test_scheduled_success_closes_the_open_issue(self):
        self.existing_issue(31)
        self.succeeding(event="schedule")
        call = self.assert_only_write("issue close")
        self.assertEqual(call.argv[2], "31")
        self.assertIn(RUN_URL, call.flag("--comment"))

    def test_success_without_an_issue_writes_nothing(self):
        self.succeeding(event="schedule")
        self.assert_no_write()

    def failing(self, event: str = "schedule") -> None:
        raise NotImplementedError

    def succeeding(self, event: str = "schedule") -> None:
        raise NotImplementedError


class NotifyFailureBase(TrackingIssueStepBase):
    """convert.yml / crux.yml / hotshot.yml: outcome comes from needs.*.result."""

    step = NOTIFY_STEP
    result_var = "RESULT"
    success_value = "success"
    failure_value = "failure"

    def failing(self, event: str = "schedule") -> None:
        self.run_step(event, **{self.result_var: self.failure_value})

    def succeeding(self, event: str = "schedule") -> None:
        self.run_step(event, **{self.result_var: self.success_value})

    def test_manual_dispatch_success_never_closes_the_issue(self):
        """One green `workflow_dispatch` is not evidence the schedule recovered."""
        self.existing_issue(31)
        self.succeeding(event="workflow_dispatch")
        self.assert_no_write()

    def test_manual_dispatch_failure_still_reports(self):
        self.failing(event="workflow_dispatch")
        self.assert_only_write("issue create")

    def test_skipped_or_cancelled_result_writes_nothing(self):
        self.existing_issue(31)
        for result in ("cancelled", "skipped"):
            with self.subTest(result=result):
                self.setUp()
                self.existing_issue(31)
                self.run_step("schedule", **{self.result_var: result})
                self.assert_no_write()


class CruxNotifyFailureTests(NotifyFailureBase):
    workflow = "crux.yml"
    title = "crux formula failing"


class HotshotNotifyFailureTests(NotifyFailureBase):
    workflow = "hotshot.yml"
    title = "hotshot formula failing"


class ConvertNotifyFailureTests(NotifyFailureBase):
    workflow = "convert.yml"
    title = "Convert pipeline failing"
    result_var = "RESULTS"
    success_value = "success success success"
    failure_value = "success failure skipped"

    def test_skipped_or_cancelled_result_writes_nothing(self):
        self.existing_issue(31)
        self.run_step("schedule", RESULTS="success cancelled skipped")
        self.assert_no_write()

    def test_any_failed_job_in_the_chain_reports(self):
        for results in ("failure skipped skipped", "success failure skipped", "success success failure"):
            with self.subTest(results=results):
                self.setUp()
                self.run_step("schedule", RESULTS=results)
                self.assert_only_write("issue create")

    def test_skipped_publish_on_an_unchanged_digest_still_counts_as_success(self):
        """A no-op schedule run (resolve/build ok, publish skipped) must close a stale issue."""
        self.existing_issue(31)
        self.run_step("schedule", RESULTS="success skipped skipped")
        self.assert_only_write("issue close")


class ConvertFreshnessTests(TrackingIssueStepBase):
    workflow = "convert-freshness.yml"
    step = FRESHNESS_STEP
    title = "Convert pipeline stale"

    def latest_run(self, age: timedelta) -> None:
        self.fixture("runs.json", [{"createdAt": iso(age), "conclusion": "success"}])

    def failing(self, event: str = "schedule") -> None:
        self.latest_run(timedelta(hours=13))
        self.run_step(event)

    def succeeding(self, event: str = "schedule") -> None:
        self.latest_run(timedelta(hours=1))
        self.run_step(event)

    def test_max_age_is_twice_the_convert_schedule_period(self):
        self.assertEqual(step_literal_env(self.workflow, self.step)["MAX_AGE_SECONDS"], "43200")

    def test_run_just_inside_the_window_is_fresh(self):
        self.existing_issue(31)
        self.latest_run(timedelta(hours=11, minutes=50))
        self.run_step()
        self.assert_only_write("issue close")

    def test_no_scheduled_run_at_all_is_stale(self):
        """A schedule GitHub silently disabled leaves no run to be old."""
        self.fixture("runs.json", [])
        self.run_step()
        call = self.assert_only_write("issue create")
        self.assertIn("No scheduled", call.flag("--body"))

    def test_stale_body_names_the_run_and_the_threshold(self):
        self.failing()
        body = self.assert_only_write("issue create").flag("--body")
        self.assertIn("12 hours", body)
        self.assertIn(RUN_URL, body)

    def test_manual_dispatch_with_fresh_run_closes_too(self):
        """Freshness is about convert.yml's schedule, not this workflow's trigger."""
        self.existing_issue(31)
        self.succeeding(event="workflow_dispatch")
        self.assert_only_write("issue close")


del TrackingIssueStepBase, NotifyFailureBase


if __name__ == "__main__":
    unittest.main()
