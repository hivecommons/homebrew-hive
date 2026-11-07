#!/usr/bin/env python3
"""Unit tests for scripts/prune-releases.py (dry-run retention planning)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "prune-releases.py"
spec = importlib.util.spec_from_file_location("prune_releases", SCRIPT)
prune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune)

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def stamp(age_days: float) -> str:
    return (NOW - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(tag: str, age_days: int, created_age_days: float | None = None) -> dict:
    # created_at is the target commit's date on GitHub and normally predates published_at.
    return {"tag_name": tag, "published_at": stamp(age_days), "created_at": stamp(created_age_days or age_days + 0.5)}


def stable(n: int, age_days: int) -> dict:
    return rel(f"contribute-{n:012x}", age_days)


def candidate(n: int, age_days: int) -> dict:
    return rel(f"contribute-candidate-{n:012x}", age_days)


class PlanTests(unittest.TestCase):
    def test_keeps_newest_n_and_young_releases(self):
        releases = [stable(i, 20 + i) for i in range(5)] + [stable(100, 1)]
        result = prune.plan(releases, set(), keep=2, min_age_days=14, now=NOW)["stable"]
        # The young release is the newest, so it occupies the first --keep slot.
        self.assertEqual(result["kept"], ["contribute-000000000064", "contribute-000000000000"])
        self.assertEqual(set(result["candidates"]), {f"contribute-{i:012x}" for i in (1, 2, 3, 4)})

    def test_young_releases_survive_even_beyond_count(self):
        releases = [stable(i, 1) for i in range(5)]
        result = prune.plan(releases, set(), keep=1, min_age_days=14, now=NOW)["stable"]
        self.assertEqual(result["candidates"], [])

    def test_protected_tags_are_kept(self):
        releases = [stable(i, 30 + i) for i in range(3)]
        protected = {"contribute-000000000002"}
        result = prune.plan(releases, protected, keep=0, min_age_days=14, now=NOW)["stable"]
        self.assertNotIn("contribute-000000000002", result["candidates"])
        self.assertEqual(len(result["candidates"]), 2)

    def test_channels_are_separate_and_hand_maintained_ignored(self):
        releases = [stable(1, 40), candidate(1, 40), candidate(2, 41), rel("crux-v1", 90), rel("hotshot-1", 90),
                    rel("contribute-ABCDEF123456", 90), rel("contribute-candidate-1234", 90)]
        result = prune.plan(releases, set(), keep=1, min_age_days=14, now=NOW)
        self.assertEqual(result["stable"]["candidates"], [])
        self.assertEqual(result["candidate"]["candidates"], ["contribute-candidate-000000000002"])

    def test_age_and_order_use_published_at_not_created_at(self):
        # Published 13 days ago but created (target commit) 20 days ago: still young, so kept.
        young = rel("contribute-00000000aaaa", 13, created_age_days=20)
        # Published 15 days ago but created yesterday: old on the publication clock, so prunable.
        old = rel("contribute-00000000bbbb", 15, created_age_days=1)
        result = prune.plan([old, young], set(), keep=0, min_age_days=14, now=NOW)["stable"]
        self.assertEqual(result["kept"], ["contribute-00000000aaaa"])
        self.assertEqual(result["candidates"], ["contribute-00000000bbbb"])
        # --keep ordering follows publication order even when created_at disagrees.
        result = prune.plan([old, young], set(), keep=1, min_age_days=0, now=NOW)["stable"]
        self.assertEqual(result["kept"], ["contribute-00000000aaaa"])

    def test_draft_without_published_at_falls_back_to_created_at(self):
        draft = {"tag_name": "contribute-00000000cccc", "published_at": None, "created_at": stamp(40)}
        result = prune.plan([draft], set(), keep=0, min_age_days=14, now=NOW)["stable"]
        self.assertEqual(result["candidates"], ["contribute-00000000cccc"])

    def test_channel_of(self):
        self.assertEqual(prune.channel_of("contribute-0123456789ab"), "stable")
        self.assertEqual(prune.channel_of("contribute-candidate-0123456789ab"), "candidate")
        self.assertIsNone(prune.channel_of("contribute-candidate"))
        self.assertIsNone(prune.channel_of("crux-0123456789ab"))


class ApiTests(unittest.TestCase):
    def test_pagination_flattens_pages(self):
        pages = [[stable(1, 1), stable(2, 2)], [stable(3, 3)]]
        with mock.patch.object(prune, "gh_api", return_value=json.dumps(pages)):
            self.assertEqual(len(prune.fetch_releases("o/r")), 3)

    def test_formula_tags_extracted(self):
        text = 'url "https://github.com/o/r/releases/download/contribute-0123456789ab/x.sif"'
        with mock.patch.object(prune, "gh_api", return_value=text):
            self.assertEqual(prune.fetch_formula_tags("o/r", "main", "contribute"), {"contribute-0123456789ab"})

    def test_missing_branch_is_empty_but_other_errors_propagate(self):
        with mock.patch.object(prune, "gh_api", side_effect=prune.ApiError("HTTP 404: Not Found")):
            self.assertEqual(prune.fetch_formula_tags("o/r", "generated/x", "x"), set())
        with mock.patch.object(prune, "gh_api", side_effect=prune.ApiError("HTTP 500")):
            with self.assertRaises(prune.ApiError):
                prune.fetch_formula_tags("o/r", "main", "x")

    def test_required_formula_404_aborts(self):
        with mock.patch.object(prune, "gh_api", side_effect=prune.ApiError("HTTP 404: Not Found")):
            with self.assertRaises(prune.ApiError):
                prune.fetch_formula_tags("o/r", "main", "contribute", required=True)

    def test_protected_tags_consult_main_generated_and_legacy_branches(self):
        def fake_api(path, *extra):
            if path.startswith("o/r/branches") or "/branches?" in path:
                return json.dumps([[{"name": "main"}, {"name": "generated/contribute-d08dd5046158"},
                                    {"name": "generated/contribute"}, {"name": "feature/x"}]])
            if "/pulls?" in path:
                return json.dumps([{"number": 1}] if "generated/contribute-d08dd5046158" in path else [])
            if "ref=main" in path and "contribute.rb" in path:
                return 'url ".../releases/download/contribute-000000000001/x.sif"'
            if "ref=generated/contribute-d08dd5046158" in path:
                return 'url ".../releases/download/contribute-d08dd5046158/x.sif"'
            raise prune.ApiError("HTTP 404: Not Found")

        with mock.patch.object(prune, "gh_api", side_effect=fake_api) as api:
            tags = prune.protected_tags("o/r", ["contribute-00000000ffff"])
        self.assertEqual(tags, {"contribute-000000000001", "contribute-d08dd5046158", "contribute-00000000ffff"})
        refs = [c.args[0] for c in api.call_args_list]
        self.assertTrue(any("ref=generated/contribute-d08dd5046158" in r for r in refs))
        self.assertFalse(any("ref=feature/x" in r for r in refs))

    def test_orphaned_legacy_branch_does_not_protect_its_release(self):
        def fake_api(path, *extra):
            if "/branches?" in path:
                return json.dumps([[{"name": "generated/contribute-d08dd5046158"}]])
            if "/pulls?" in path:
                return json.dumps([])
            if "ref=main" in path and "contribute.rb" in path:
                return 'url ".../releases/download/contribute-000000000001/x.sif"'
            raise prune.ApiError("HTTP 404: Not Found")

        with mock.patch.object(prune, "gh_api", side_effect=fake_api) as api, mock.patch("builtins.print"):
            tags = prune.protected_tags("o/r", [])
        self.assertEqual(tags, {"contribute-000000000001"})
        self.assertFalse(any("ref=generated/contribute-d08dd5046158" in c.args[0] for c in api.call_args_list))

    def test_malformed_timestamp_exits_with_error(self):
        bad = [{"tag_name": "contribute-000000000001", "published_at": "not-a-date", "created_at": "nope"}]
        with mock.patch.object(prune, "fetch_releases", return_value=bad), \
                mock.patch.object(prune, "protected_tags", return_value=set()), \
                mock.patch("sys.argv", ["prune", "--repo", "o/r"]), \
                mock.patch("builtins.print") as out:
            self.assertEqual(prune.main(), 1)
            self.assertNotIn("would delete", " ".join(str(c) for c in out.call_args_list))

    def test_api_failure_exits_nonzero_without_report(self):
        with mock.patch.object(prune, "gh_api", side_effect=prune.ApiError("boom")), \
                mock.patch("sys.argv", ["prune", "--repo", "o/r"]), \
                mock.patch("builtins.print") as out:
            self.assertEqual(prune.main(), 1)
            self.assertNotIn("would delete", " ".join(str(c) for c in out.call_args_list))


class GhSubprocessTests(unittest.TestCase):
    """The two gh wrappers are the only code that touches the network or deletes anything."""

    def completed(self, code: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)

    def test_gh_api_passes_extra_flags_before_path_and_returns_stdout(self):
        with mock.patch.object(prune.subprocess, "run", return_value=self.completed(0, stdout="[]")) as run:
            self.assertEqual(prune.gh_api("repos/o/r/releases", "--paginate", "--slurp"), "[]")
        self.assertEqual(run.call_args.args[0], ["gh", "api", "--paginate", "--slurp", "repos/o/r/releases"])
        self.assertTrue(run.call_args.kwargs.get("capture_output"))

    def test_gh_api_failure_raises_with_stderr(self):
        with mock.patch.object(prune.subprocess, "run", return_value=self.completed(1, stderr="HTTP 404: Not Found\n")):
            with self.assertRaises(prune.ApiError) as ctx:
                prune.gh_api("repos/o/r/contents/x")
        self.assertIn("repos/o/r/contents/x", str(ctx.exception))
        # fetch_formula_tags keys its 404 tolerance off this text, so it must survive the wrap.
        self.assertIn("404", str(ctx.exception))

    def test_delete_release_removes_tag_too_and_never_prompts(self):
        with mock.patch.object(prune.subprocess, "run", return_value=self.completed(0)) as run:
            prune.delete_release("o/r", "contribute-aaaaaaaaaaaa")
        self.assertEqual(
            run.call_args.args[0],
            ["gh", "release", "delete", "contribute-aaaaaaaaaaaa", "--repo", "o/r", "--yes", "--cleanup-tag"],
        )

    def test_delete_release_failure_raises_with_tag_and_stderr(self):
        with mock.patch.object(prune.subprocess, "run", return_value=self.completed(1, stderr="release not found")):
            with self.assertRaises(prune.ApiError) as ctx:
                prune.delete_release("o/r", "contribute-aaaaaaaaaaaa")
        self.assertIn("contribute-aaaaaaaaaaaa", str(ctx.exception))
        self.assertIn("release not found", str(ctx.exception))


class DeleteTests(unittest.TestCase):
    def run_main(self, releases, *flags):
        argv = ["prune", "--repo", "o/r", "--keep", "1", "--min-age-days", "14", *flags]
        with mock.patch.object(prune, "fetch_releases", return_value=releases), \
                mock.patch.object(prune, "protected_tags", return_value={"contribute-eeeeeeeeeeee"}), \
                mock.patch.object(prune, "delete_release") as delete, \
                mock.patch("sys.argv", argv), \
                mock.patch("builtins.print"):
            code = prune.main()
        return code, [c.args[1] for c in delete.call_args_list]

    def test_dry_run_deletes_nothing(self):
        releases = [rel("contribute-aaaaaaaaaaaa", 40), rel("contribute-bbbbbbbbbbbb", 50)]
        self.assertEqual(self.run_main(releases), (0, []))

    def test_delete_removes_only_candidates(self):
        releases = [
            rel("contribute-aaaaaaaaaaaa", 40),
            rel("contribute-bbbbbbbbbbbb", 50),
            rel("contribute-eeeeeeeeeeee", 60),
            rel("contribute-candidate-cccccccccccc", 40),
            rel("crux-dddddddddddd", 90),
        ]
        self.assertEqual(self.run_main(releases, "--delete"), (0, ["contribute-bbbbbbbbbbbb"]))

    def test_delete_failure_exits_nonzero(self):
        releases = [rel("contribute-aaaaaaaaaaaa", 40), rel("contribute-bbbbbbbbbbbb", 50)]
        with mock.patch.object(prune, "fetch_releases", return_value=releases), \
                mock.patch.object(prune, "protected_tags", return_value=set()), \
                mock.patch.object(prune, "delete_release", side_effect=prune.ApiError("boom")), \
                mock.patch("sys.argv", ["prune", "--repo", "o/r", "--keep", "1", "--delete"]), \
                mock.patch("builtins.print"):
            self.assertEqual(prune.main(), 1)


if __name__ == "__main__":
    unittest.main()
