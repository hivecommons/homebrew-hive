#!/usr/bin/env python3
"""Dry-run inventory of generated contribute releases eligible for pruning.

Reports which `contribute-<digest12>` / `contribute-candidate-<digest12>`
releases fall outside the retention policy. It never deletes anything.

Retention, applied per channel: a release is kept if it is among the newest
--keep releases, is younger than --min-age-days, or its tag is protected
(referenced by the formula on main or on the open generated branch, or listed
with --protect-tag). Hand-maintained releases (crux, hotshot, ...) never match.
Any API failure aborts with a non-zero exit so nothing is ever reported from
partial data.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

CHANNEL_PATTERNS = {
    "stable": re.compile(r"^contribute-[0-9a-f]{12}$"),
    "candidate": re.compile(r"^contribute-candidate-[0-9a-f]{12}$"),
}
FORMULAE = {"stable": "contribute", "candidate": "contribute-candidate"}
TAG_REF = re.compile(r"/releases/download/(contribute(?:-candidate)?-[0-9a-f]{12})/")


class ApiError(RuntimeError):
    pass


def gh_api(path: str, *extra: str) -> str:
    proc = subprocess.run(["gh", "api", *extra, path], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ApiError(f"gh api {path} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def channel_of(tag: str) -> str | None:
    for channel, pattern in CHANNEL_PATTERNS.items():
        if pattern.match(tag):
            return channel
    return None


def fetch_releases(repo: str) -> list[dict]:
    # --paginate --slurp yields one JSON array of pages.
    pages = json.loads(gh_api(f"repos/{repo}/releases?per_page=100", "--paginate", "--slurp"))
    return [release for page in pages for release in page]


def fetch_formula_tags(repo: str, ref: str, formula: str) -> set[str]:
    try:
        text = gh_api(f"repos/{repo}/contents/Formula/{formula}.rb?ref={ref}", "-H", "Accept: application/vnd.github.raw")
    except ApiError as exc:
        if "404" in str(exc) or "Not Found" in str(exc):
            return set()
        raise
    return set(TAG_REF.findall(text))


def protected_tags(repo: str, extra: list[str]) -> set[str]:
    tags = set(extra)
    for formula in FORMULAE.values():
        for ref in ("main", f"generated/{formula}"):
            tags |= fetch_formula_tags(repo, ref, formula)
    return tags


def plan(releases: list[dict], protected: set[str], keep: int, min_age_days: int, now: datetime) -> dict:
    cutoff = now - timedelta(days=min_age_days)
    result = {}
    for channel in CHANNEL_PATTERNS:
        generated = sorted(
            (r for r in releases if channel_of(r["tag_name"]) == channel),
            key=lambda r: parse_time(r["created_at"]),
            reverse=True,
        )
        kept, candidates = [], []
        for index, release in enumerate(generated):
            if (
                index < keep
                or parse_time(release["created_at"]) >= cutoff
                or release["tag_name"] in protected
            ):
                kept.append(release["tag_name"])
            else:
                candidates.append(release["tag_name"])
        result[channel] = {"kept": kept, "candidates": candidates}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--min-age-days", type=int, default=14)
    parser.add_argument("--protect-tag", action="append", default=[])
    args = parser.parse_args()
    try:
        releases = fetch_releases(args.repo)
        protected = protected_tags(args.repo, args.protect_tag)
    except (ApiError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = plan(releases, protected, args.keep, args.min_age_days, datetime.now(timezone.utc))
    for channel, data in report.items():
        print(f"{channel}: keep={len(data['kept'])} prune-candidates={len(data['candidates'])}")
        for tag in data["candidates"]:
            print(f"  would delete {tag}")
    print("dry run: nothing was deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
