#!/usr/bin/env python3
"""Unit tests for scripts/prune-releases.py (dry-run retention planning)."""
from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "prune-releases.py"
spec = importlib.util.spec_from_file_location("prune_releases", SCRIPT)
prune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune)

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def rel(tag: str, age_days: int) -> dict:
    return {"tag_name": tag, "created_at": (NOW - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def stable(n: int, age_days: int) -> dict:
    return rel(f"contribute-{n:012x}", age_days)


def candidate(n: int, age_days: int) -> dict:
    return rel(f"contribute-candidate-{n:012x}", age_days)


class PlanTests(unittest.TestCase):
    def test_keeps_newest_n_and_young_releases(self):
        releases = [stable(i, 20 + i) for i in range(5)] + [stable(100, 1)]
        result = prune.plan(releases, set(), keep=2, min_age_days=14, now=NOW)["stable"]
        self.assertEqual(len(result["kept"]), 3)
        self.assertEqual(set(result["candidates"]), {f"contribute-{i:012x}" for i in (2, 3, 4)})

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

    def test_api_failure_exits_nonzero_without_report(self):
        with mock.patch.object(prune, "gh_api", side_effect=prune.ApiError("boom")), \
                mock.patch("sys.argv", ["prune", "--repo", "o/r"]), \
                mock.patch("builtins.print") as out:
            self.assertEqual(prune.main(), 1)
            self.assertNotIn("would delete", " ".join(str(c) for c in out.call_args_list))


if __name__ == "__main__":
    unittest.main()
