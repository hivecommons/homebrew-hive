"""Tests for the GitHub issue forms under .github/ISSUE_TEMPLATE/.

GitHub validates issue forms only when someone opens the chooser, so a broken
form or a stale dropdown is invisible to CI. These tests check the structure
GitHub requires and pin the dropdowns that enumerate repository facts to
their sources of truth: the Formula dropdown to Formula/*.rb and the Runtime
dropdown to the HIVE_CONTRIBUTE_RUNTIME values the wrapper accepts.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only where PyYAML is absent
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
FORMULA_DIR = REPO_ROOT / "Formula"
WRAPPER = REPO_ROOT / "scripts" / "contribute-wrapper.sh.in"

# https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema
FORM_ELEMENT_TYPES = {"markdown", "textarea", "input", "dropdown", "checkboxes"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def form_paths() -> list[Path]:
    return sorted(p for p in TEMPLATE_DIR.glob("*.yml") if p.name != "config.yml")


def dropdown_options(form: dict, field_id: str) -> list[str]:
    for element in form["body"]:
        if element.get("id") == field_id:
            return element["attributes"]["options"]
    raise AssertionError(f"no dropdown with id {field_id!r}")


def formula_names() -> set[str]:
    return {p.stem for p in FORMULA_DIR.glob("*.rb")}


def wrapper_runtimes() -> set[str]:
    """Return the HIVE_CONTRIBUTE_RUNTIME values the wrapper's validation accepts."""
    text = WRAPPER.read_text()
    match = re.search(
        r'case "\$requested_runtime" in\n\s*([a-z|]+)\) ;;\n\s*\*\) echo "unknown HIVE_CONTRIBUTE_RUNTIME',
        text,
    )
    if not match:
        raise AssertionError("runtime validation case not found in contribute-wrapper.sh.in")
    return set(match.group(1).split("|")) - {"auto"}


@unittest.skipUnless(yaml, "PyYAML not installed")
class IssueFormStructureTests(unittest.TestCase):
    def test_forms_exist(self):
        self.assertEqual(
            [p.name for p in form_paths()], ["bug_report.yml", "feature_request.yml"]
        )

    def test_every_form_has_required_top_level_keys(self):
        for path in form_paths():
            with self.subTest(form=path.name):
                form = load_yaml(path)
                for key in ("name", "description", "body"):
                    self.assertIn(key, form)
                    self.assertTrue(form[key], f"{key} is empty")
                self.assertIsInstance(form["body"], list)
                self.assertIsInstance(form.get("labels", []), list)

    def test_body_elements_are_well_formed(self):
        for path in form_paths():
            form = load_yaml(path)
            seen_ids: set[str] = set()
            non_markdown = 0
            for index, element in enumerate(form["body"]):
                with self.subTest(form=path.name, element=index):
                    self.assertIn(element.get("type"), FORM_ELEMENT_TYPES)
                    self.assertIsInstance(element.get("attributes"), dict)
                    if element["type"] == "markdown":
                        self.assertNotIn("id", element)
                        self.assertTrue(element["attributes"].get("value", "").strip())
                        continue
                    non_markdown += 1
                    self.assertTrue(element["attributes"].get("label"), "label missing")
                    element_id = element.get("id")
                    self.assertIsNotNone(element_id, "non-markdown element has no id")
                    self.assertRegex(element_id, ID_PATTERN)
                    self.assertNotIn(element_id, seen_ids, "duplicate id")
                    seen_ids.add(element_id)
                    required = element.get("validations", {}).get("required", False)
                    self.assertIsInstance(required, bool)
                    if element["type"] == "dropdown":
                        options = element["attributes"].get("options")
                        self.assertIsInstance(options, list)
                        self.assertTrue(options, "dropdown has no options")
                        self.assertEqual(len(options), len(set(options)), "duplicate option")
                        for option in options:
                            self.assertIsInstance(option, str)
                            self.assertNotEqual(option.strip().lower(), "none")
                    else:
                        self.assertNotIn("options", element["attributes"])
                    if "render" in element["attributes"]:
                        self.assertEqual(element["type"], "textarea")
            with self.subTest(form=path.name):
                self.assertGreater(non_markdown, 0, "form has no input elements")

    def test_markdown_links_are_absolute(self):
        link = re.compile(r"\]\(([^)]+)\)")
        for path in form_paths():
            form = load_yaml(path)
            for element in form["body"]:
                if element["type"] != "markdown":
                    continue
                for target in link.findall(element["attributes"]["value"]):
                    with self.subTest(form=path.name, link=target):
                        self.assertTrue(target.startswith("https://"), target)


@unittest.skipUnless(yaml, "PyYAML not installed")
class IssueChooserConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = load_yaml(TEMPLATE_DIR / "config.yml")

    def test_blank_issues_flag_is_boolean(self):
        self.assertIsInstance(self.config.get("blank_issues_enabled"), bool)

    def test_contact_links_are_complete_and_unique(self):
        links = self.config.get("contact_links")
        self.assertIsInstance(links, list)
        self.assertTrue(links)
        names = [link.get("name") for link in links]
        self.assertEqual(len(names), len(set(names)), "duplicate contact link name")
        for link in links:
            with self.subTest(link=link.get("name")):
                for key in ("name", "url", "about"):
                    self.assertTrue(link.get(key), f"{key} missing")
                self.assertTrue(link["url"].startswith("https://"), link["url"])

    def test_security_contact_link_points_at_org_policy(self):
        urls = [link["url"] for link in self.config["contact_links"]]
        self.assertIn("https://github.com/hivecommons/.github/blob/main/SECURITY.md", urls)


@unittest.skipUnless(yaml, "PyYAML not installed")
class BugReportContractTests(unittest.TestCase):
    """The bug form enumerates tap facts; keep it in step with their sources."""

    def setUp(self):
        self.form = load_yaml(TEMPLATE_DIR / "bug_report.yml")

    def test_formula_dropdown_lists_every_formula_in_the_tap(self):
        options = dropdown_options(self.form, "formula")
        # Options may carry a parenthesised hint, e.g. "contribute (hive-contribute)".
        listed = {option.split(" (", 1)[0].strip() for option in options}
        self.assertEqual(listed, formula_names())

    def test_runtime_dropdown_matches_wrapper_accepted_set(self):
        options = dropdown_options(self.form, "runtime")
        runtimes = wrapper_runtimes()
        named = {option for option in options if " " not in option and "/" not in option}
        self.assertEqual(named, runtimes)
        # The prose escape hatches must remain for installs that never reach
        # the wrapper and for formulae that have no runtime at all.
        prose = set(options) - named
        self.assertTrue(any(option.startswith("none") for option in prose), options)
        self.assertTrue(any(option.startswith("not applicable") for option in prose), options)

    def test_formula_and_runtime_are_required(self):
        for element in self.form["body"]:
            if element.get("id") in {"formula", "platform", "stage", "runtime", "version"}:
                with self.subTest(field=element["id"]):
                    self.assertTrue(element.get("validations", {}).get("required"))

    def test_log_field_renders_as_shell_and_warns_about_secrets(self):
        logs = next(element for element in self.form["body"] if element.get("id") == "logs")
        self.assertEqual(logs["attributes"].get("render"), "shell")
        self.assertIn("Redact", logs["attributes"]["description"])

    def test_upstream_trackers_are_named_for_hand_maintained_formulae(self):
        intro = self.form["body"][0]["attributes"]["value"]
        self.assertIn("https://github.com/hivecommons/hotshot/issues", intro)
        self.assertIn("https://github.com/hivecommons/hive/issues", intro)


@unittest.skipUnless(yaml, "PyYAML not installed")
class FeatureRequestContractTests(unittest.TestCase):
    def setUp(self):
        self.form = load_yaml(TEMPLATE_DIR / "feature_request.yml")

    def test_area_dropdown_covers_hand_maintained_formulae(self):
        options = dropdown_options(self.form, "area")
        hand_maintained = formula_names() - {"contribute"}
        joined = " ".join(options).lower()
        for name in hand_maintained:
            with self.subTest(formula=name):
                self.assertIn(name, joined)

    def test_intro_names_generated_and_hand_maintained_files(self):
        intro = self.form["body"][0]["attributes"]["value"]
        self.assertIn("Formula/contribute*.rb", intro)
        for name in formula_names() - {"contribute"}:
            self.assertIn(f"Formula/{name}.rb", intro)


if __name__ == "__main__":
    unittest.main()
