"""Tests for the inline shell logic in .github/workflows/hive-ok-to-test.yml.

The workflow approves held Actions runs on bot pull requests, so every branch
of its authorization chain is a security decision: who may issue the command,
which PR heads count as same-repo, and which authors are trusted. The body is
rendered from `hivectl ok-to-test-template` with one local addition, trusting
github-actions[bot] only on `generated/*` heads (the convert.yml formula PRs),
which no upstream test covers. These tests pull the step's exact shell out of
the workflow, stub `gh` with fixture-backed responses that still run the real
`--jq` filters, and check the decision each event produces.
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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "hive-ok-to-test.yml"

REPO = "o/r"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
MARKER = f"<!-- hive-ok-to-test:{HEAD_SHA} -->"

# Every `gh` call is `gh api`; the stub maps the request to a fixture file in
# $GH_STUB_DIR, applies the workflow's own --jq filter with the real jq, and
# logs the argv so tests can assert what was (not) approved.
GH_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
# One record per call: the approval comment body spans two lines.
call="$*"; printf '%s\n' "${call//$'\n'/\\n}" >>"$GH_STUB_DIR/calls.log"
[[ "${1:-}" == api ]] || { echo "stub gh: unexpected subcommand: $*" >&2; exit 97; }
shift
method=GET path="" filter=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -X) method="$2"; shift 2 ;;
    --jq) filter="$2"; shift 2 ;;
    -f) shift 2 ;;
    --paginate) shift ;;
    *) path="$1"; shift ;;
  esac
done
case "$method $path" in
  "GET repos/"*"/collaborators/"*"/permission") fixture=permission.json ;;
  "GET repos/"*"/pulls/"*) fixture=pr.json ;;
  "GET repos/"*"/issues/"*"/comments?"*) fixture=comments.json ;;
  "GET repos/"*"/issues/"*) fixture=issue.json ;;
  "GET repos/"*"/actions/runs?"*) fixture=runs.json ;;
  "POST repos/"*"/reactions") exit 0 ;;
  "POST repos/"*"/comments") exit 0 ;;
  "POST repos/"*"/actions/runs/"*"/approve")
    [[ ! -e "$GH_STUB_DIR/approve-fails" ]] || exit 1
    exit 0 ;;
  *) echo "stub gh: unexpected request: $method $path" >&2; exit 98 ;;
esac
file="$GH_STUB_DIR/$fixture"
[[ -e "$file" ]] || { echo "stub gh: no fixture for $path" >&2; exit 99; }
if [[ -n "$filter" ]]; then jq -r "$filter" "$file"; else cat "$file"; fi
"""


def approve_step() -> str:
    match = re.search(r"- name: Approve held trusted same-repo workflow runs\n(.*)\Z", WORKFLOW.read_text(), re.S)
    if not match:
        raise AssertionError("approve step not found in hive-ok-to-test.yml")
    return match.group(1)


def step_script() -> str:
    match = re.search(r"^        run: \|\n(.*)\Z", approve_step(), re.S | re.M)
    if not match:
        raise AssertionError("approve step has no `run: |` block")
    return textwrap.dedent(match.group(1))


def step_env() -> dict[str, str]:
    """Return the step's literal `env:` values (the trust configuration)."""
    match = re.search(r"^        env:\n(.*?)^        run: \|", approve_step(), re.S | re.M)
    if not match:
        raise AssertionError("approve step has no `env:` block")
    env = {}
    for line in match.group(1).splitlines():
        kv = re.match(r'\s+([A-Z_]+): "(.*)"$', line)
        if kv:
            env[kv.group(1)] = kv.group(2)
    return env


def event(*, body: str = "/ok-to-test", commenter: str = "hivecommons-hive[bot]", pull_request: bool = True) -> dict:
    issue: dict = {"number": 5}
    if pull_request:
        issue["pull_request"] = {"url": f"https://api.github.com/repos/{REPO}/pulls/5"}
    return {"issue": issue, "comment": {"id": 77, "body": body, "user": {"login": commenter}}}


def pr(*, author: str = "dependabot[bot]", ref: str = "dependabot/npm/x", head_repo: str = REPO, sha: str = HEAD_SHA) -> dict:
    return {
        "head": {"repo": {"full_name": head_repo}, "sha": sha, "ref": ref},
        "base": {"repo": {"full_name": REPO}},
        "user": {"login": author},
    }


def runs(*heads: tuple[int, str]) -> dict:
    return {"workflow_runs": [{"id": run_id, "head_repository": {"full_name": repo}} for run_id, repo in heads]}


@unittest.skipUnless(shutil.which("jq"), "jq not installed")
class OkToTestStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ok-to-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stub_dir = self.tmp / "stub"
        self.stub_dir.mkdir()
        gh = self.tmp / "bin" / "gh"
        gh.parent.mkdir()
        gh.write_text(GH_STUB)
        gh.chmod(0o755)
        self.bin = gh.parent
        self.fixture("pr.json", pr())
        self.fixture("issue.json", {"labels": [{"name": "dependencies"}]})
        self.fixture("comments.json", [{"body": "unrelated comment"}])
        self.fixture("runs.json", runs((101, REPO)))

    def fixture(self, name: str, payload) -> None:
        (self.stub_dir / name).write_text(json.dumps(payload))

    def permission(self, level: str) -> None:
        self.fixture("permission.json", {"permission": level})

    def run_step(self, event_payload: dict | None = None, **env_overrides: str) -> subprocess.CompletedProcess:
        event_path = self.tmp / "event.json"
        event_path.write_text(json.dumps(event_payload if event_payload is not None else event()))
        env = {
            **os.environ,
            **step_env(),
            **env_overrides,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GH_STUB_DIR": str(self.stub_dir),
            "GH_TOKEN": "stub",
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_EVENT_PATH": str(event_path),
        }
        return subprocess.run(["bash", "-c", step_script()], env=env, capture_output=True, text=True)

    def calls(self) -> list[str]:
        log = self.stub_dir / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def approved(self) -> list[str]:
        return [re.search(r"actions/runs/(\d+)/approve", c).group(1) for c in self.calls() if "/approve" in c]

    def posted_comments(self) -> list[str]:
        return [c for c in self.calls() if re.match(r"api -X POST repos/o/r/issues/\d+/comments ", c)]

    def reactions(self) -> list[str]:
        return [re.search(r"content=(\S+)", c).group(1) for c in self.calls() if "/reactions" in c]

    def assert_ignored(self, proc: subprocess.CompletedProcess, reason: str) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(reason, proc.stdout + proc.stderr)
        self.assertEqual(self.approved(), [], "no run may be approved on this path")
        self.assertEqual(self.posted_comments(), [], "no approval marker may be posted on this path")

    # -- the local addition: github-actions[bot] on generated/* heads ----------

    def test_env_pins_the_generated_branch_trust_addition(self):
        env = step_env()
        self.assertEqual(env["HIVE_APP_LOGINS"], "hivecommons-hive[bot]")
        self.assertEqual(env["GENERATED_AUTHORS"], "github-actions[bot]")
        self.assertEqual(env["GENERATED_BRANCH_PREFIX"], "generated/")
        self.assertEqual(env["COMMAND"], "/ok-to-test")
        self.assertNotIn("github-actions[bot]", env["TRUSTED_AUTHORS"],
                         "github-actions[bot] must only be trusted via the generated/* branch rule")

    def test_github_actions_bot_is_approved_only_on_generated_heads(self):
        self.fixture("pr.json", pr(author="github-actions[bot]", ref="generated/contribute"))
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("trusted for generated head branch generated/contribute", proc.stdout)
        self.assertEqual(self.approved(), ["101"])

        for ref in ("main", "generated", "feature/generated/x", "Generated/contribute"):
            with self.subTest(ref=ref):
                self.setUp()
                self.fixture("pr.json", pr(author="github-actions[bot]", ref=ref))
                self.assert_ignored(self.run_step(), "is not in trusted-authors")

    def test_empty_generated_prefix_disables_the_generated_rule(self):
        self.fixture("pr.json", pr(author="github-actions[bot]", ref="generated/contribute"))
        self.assert_ignored(self.run_step(GENERATED_BRANCH_PREFIX=""), "is not in trusted-authors")

    def test_generated_branch_does_not_trust_other_authors(self):
        self.fixture("pr.json", pr(author="someone", ref="generated/contribute"))
        self.assert_ignored(self.run_step(), "is not in trusted-authors")

    # -- the upstream template's gates, in the order the shell applies them ----

    def test_comment_on_a_plain_issue_is_ignored_before_any_api_call(self):
        self.assert_ignored(self.run_step(event(pull_request=False)), "not on a pull request")
        self.assertEqual(self.calls(), [])

    def test_command_must_be_a_whole_line(self):
        for body in ("/ok-to-test please", "please /ok-to-test", "/ok-to-tests", ""):
            with self.subTest(body=body):
                self.setUp()
                self.assert_ignored(self.run_step(event(body=body)), "command not present")
                self.assertEqual(self.calls(), [])
        for body in ("/ok-to-test", "LGTM\r\n/ok-to-test\r\n", "/ok-to-test\nthanks"):
            with self.subTest(body=body):
                self.setUp()
                proc = self.run_step(event(body=body))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self.approved(), ["101"])

    def test_commenter_must_be_the_app_or_hold_write(self):
        for level in ("read", "triage", "none", ""):
            with self.subTest(permission=level):
                self.setUp()
                self.permission(level)
                proc = self.run_step(event(commenter="drive-by"))
                self.assert_ignored(proc, "is not an allowed Hive App login and lacks write/maintain/admin")
                self.assertFalse(any("/pulls/" in c for c in self.calls()), "PR must not be fetched for an untrusted commenter")
        for level in ("write", "maintain", "admin"):
            with self.subTest(permission=level):
                self.setUp()
                self.permission(level)
                proc = self.run_step(event(commenter="maintainer"))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self.approved(), ["101"])

    def test_permission_lookup_failure_denies(self):
        # No permission.json: the stub exits non-zero, as gh does for a 404.
        self.assert_ignored(self.run_step(event(commenter="ghost")), "is not an allowed Hive App login")

    def test_app_login_match_is_case_insensitive_and_skips_permission_lookup(self):
        proc = self.run_step(event(commenter="HiveCommons-Hive[bot]"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.approved(), ["101"])
        self.assertFalse(any("/permission" in c for c in self.calls()))

    def test_fork_heads_are_never_approved(self):
        self.fixture("pr.json", pr(head_repo="fork/r"))
        self.assert_ignored(self.run_step(), "not a same-repository head")

    def test_pr_without_head_sha_is_ignored(self):
        self.fixture("pr.json", pr(sha=""))
        self.assert_ignored(self.run_step(), "not a same-repository head")

    def test_trusted_authors_list_is_case_insensitive_and_includes_the_app(self):
        for author in ("Dependabot[bot]", "renovate[bot]", "hivecommons-hive[bot]"):
            with self.subTest(author=author):
                self.setUp()
                self.fixture("pr.json", pr(author=author, ref="main"))
                proc = self.run_step()
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self.approved(), ["101"])

    def test_sentinel_alert_label_refuses_even_for_trusted_authors(self):
        for label in ("sentinel-alert", "Sentinel-Alert"):
            with self.subTest(label=label):
                self.setUp()
                self.fixture("issue.json", {"labels": [{"name": "dependencies"}, {"name": label}]})
                self.assert_ignored(self.run_step(), "sentinel-alert is present")

    def test_already_approved_sha_is_acknowledged_once(self):
        self.fixture("comments.json", [{"body": "first"}, {"body": f"{MARKER}\nHive ok-to-test approved 1 held workflow run(s)"}])
        proc = self.run_step()
        self.assert_ignored(proc, "already approved by this workflow")
        self.assertEqual(self.reactions(), ["+1"])
        self.assertFalse(any("/actions/runs?" in c for c in self.calls()), "held runs must not be listed again")

    def test_marker_for_another_sha_does_not_block_approval(self):
        self.fixture("comments.json", [{"body": "<!-- hive-ok-to-test:feedfacefeedfacefeedfacefeedfacefeedface -->"}])
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.approved(), ["101"])

    def test_no_held_runs_acknowledges_without_a_marker(self):
        self.fixture("runs.json", runs())
        proc = self.run_step()
        self.assert_ignored(proc, "no action_required workflow runs")
        self.assertEqual(self.reactions(), ["+1"])

    def test_only_same_repo_held_runs_are_approved_and_the_marker_is_posted(self):
        self.fixture("runs.json", runs((7, REPO), (8, "fork/r"), (9, REPO)))
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.approved(), ["7", "9"])
        self.assertTrue(any("actions/runs?head_sha=" + HEAD_SHA in c and "status=action_required" in c for c in self.calls()))
        posted = self.posted_comments()
        self.assertEqual(len(posted), 1, self.calls())
        self.assertIn(f"-f body={MARKER}\\n", posted[0])
        self.assertTrue(posted[0].endswith(f"approved 2 held workflow run(s) for trusted same-repo PR head {HEAD_SHA}."), posted[0])

    def test_approve_failure_fails_the_job_without_posting_a_marker(self):
        (self.stub_dir / "approve-fails").touch()
        proc = self.run_step()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("::error::ok-to-test: could not approve workflow run 101", proc.stdout)
        self.assertEqual(self.reactions(), ["confused"])
        self.assertFalse(any(MARKER in c for c in self.calls()))


class WorkflowShapeTests(unittest.TestCase):
    def test_runs_only_for_new_comments_on_pull_requests(self):
        text = WORKFLOW.read_text()
        self.assertIn("  issue_comment:\n    types: [created]", text)
        self.assertIn("if: ${{ github.event.issue.pull_request }}", text)

    def test_job_holds_exactly_the_permissions_the_approve_call_needs(self):
        match = re.search(r"    permissions:\n((?:      .*\n)+)", WORKFLOW.read_text())
        self.assertIsNotNone(match)
        perms = dict(line.strip().split(": ") for line in match.group(1).splitlines())
        self.assertEqual(perms, {"actions": "write", "contents": "read", "issues": "write", "pull-requests": "read"})


if __name__ == "__main__":
    unittest.main()
