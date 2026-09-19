"""Principles as skill-owned source: where one comes from, and where it lands.

The point these cases defend is ownership. A principle is authored in the skill
that uses it, so the compiler supplies none, substitutes none, and can reach none
from anywhere else. A skill's guidance is its own.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.bundlepaths import ROOT, principle_path

from tests.support import (
    REPO_ROOT,
    alpha,
    codes,
    compiled,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    inspect_one,
    pages,
    write_source,
)
from tests.test_cli import run


class OwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    # The two directories the package is allowed to carry prose in, and what
    # each is for. Manual topics are the compiler explaining the source format;
    # explain codes are the compiler explaining its own checks. Neither is
    # guidance a compiled skill can carry.
    PACKAGE_PROSE_DIRECTORIES = ("manual_topics", "explain_codes")

    def test_the_compiler_package_ships_no_principle_of_its_own(self):
        """Canonical guidance in the compiler would put its words in someone
        else's skill, and would change a bundle without the source changing.

        Named files are not what this refuses, because the next corpus would
        arrive under a name nobody listed. Every non-Python file the package
        ships is accounted for instead, so a new directory of prose fails this
        until someone says what it is.
        """
        package = REPO_ROOT / "degardis"
        unaccounted = sorted(
            path.relative_to(package).as_posix()
            for path in package.rglob("*")
            if path.is_file()
            and path.suffix != ".py"
            and "__pycache__" not in path.parts
            and path.parts[len(package.parts)] not in self.PACKAGE_PROSE_DIRECTORIES
        )
        self.assertEqual(
            [],
            unaccounted,
            "the package ships prose outside its manual topics and check "
            "explanations; a skill's guidance is authored in that skill",
        )

    def test_a_principle_resolves_only_to_this_skill_s_own_file(self):
        source = alpha(self.root) / "principles" / "evidence.md"
        self.assertTrue(source.is_file())
        _, result, _ = compiled(alpha(self.root))
        self.assertEqual(
            source, result.content.sources.principles["evidence"].path
        )

    def test_a_name_with_no_local_file_fails_compilation(self):
        (alpha(self.root) / "principles" / "evidence.md").unlink()
        self.assertIn("manifest.unknown-principle", codes(alpha(self.root)))

    def test_no_installed_skill_can_supply_a_missing_principle(self):
        """A sibling skill stating the same id changes nothing here."""
        (alpha(self.root) / "principles" / "delegation.md").unlink()
        write_source(
            self.root / "beta" / "principles" / "delegation.md",
            "title: Delegation",
            "Beta's own.",
        )
        self.assertIn("manifest.unknown-principle", codes(alpha(self.root)))

    def test_the_message_names_the_file_that_would_have_answered(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"] = ["clear-reporting"]
        _, _, diagnostics = compiled(alpha(self.root))
        message = next(
            record.message
            for record in diagnostics.records
            if record.code == "manifest.unknown-principle"
        )
        self.assertIn("principles/clear-reporting.md", message)

    def test_a_principle_the_skill_does_not_select_is_reported(self):
        write_source(
            alpha(self.root) / "principles" / "spare.md",
            "title: Spare",
            "Named by nothing.",
        )
        self.assertIn("principle.unused", codes(alpha(self.root), "warning"))

    def test_a_principle_named_by_every_task_is_suggested_at_skill_level(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"].remove("evidence")
        for task in ("document", "repair", "review"):
            with edit_frontmatter(alpha(self.root) / "tasks" / f"{task}.md") as fields:
                fields["principles"] = ["evidence"]

        self.assertIn("principle.all-tasks", codes(alpha(self.root), "warning"))

    def test_a_principle_named_at_skill_and_task_level_is_reported(self):
        with edit_frontmatter(alpha(self.root) / "tasks" / "review.md") as fields:
            fields["principles"] = ["evidence"]

        self.assertIn(
            "principle.duplicate-placement", codes(alpha(self.root), "warning")
        )

    def test_editing_a_principle_changes_its_generated_page(self):
        page = principle_path("reporting")
        before = pages(alpha(self.root))[page]
        path = alpha(self.root) / "principles" / "reporting.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nOne more sentence.\n",
            encoding="utf-8",
        )
        after = pages(alpha(self.root))[page]
        self.assertNotEqual(before, after)
        self.assertIn("One more sentence.", after)

    def test_editing_a_principle_changes_the_source_fingerprint(self):
        before = inspect_one(alpha(self.root))["source_fingerprint"]["digest"]
        path = alpha(self.root) / "principles" / "reporting.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nOne more sentence.\n",
            encoding="utf-8",
        )
        after = inspect_one(alpha(self.root))["source_fingerprint"]["digest"]
        self.assertNotEqual(before, after)


class SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def write(self, fields: str, body: str = "Guidance text.") -> set[str]:
        write_source(
            alpha(self.root) / "principles" / "evidence.md", fields, body
        )
        return codes(alpha(self.root))

    def test_a_principle_needs_only_a_title(self):
        self.assertEqual(set(), self.write("title: Evidence"))

    def test_a_principle_with_no_title_is_reported(self):
        self.assertIn("principle.missing-title", self.write(""))

    def test_each_unreadable_field_names_itself(self):
        for fields, code in (
            ("title: ''", "principle.invalid-title"),
            ("title: Evidence\nactivation: ''", "principle.invalid-activation"),
        ):
            with self.subTest(code=code):
                self.assertIn(code, self.write(fields))

    def test_an_unprefixed_field_warns_without_blocking_generation(self):
        write_source(
            alpha(self.root) / "principles" / "evidence.md",
            "title: Evidence\ntasks: [review]",
        )
        self.assertIn(
            "principle.unknown-field", codes(alpha(self.root), "warning")
        )
        self.assertIn(principle_path("evidence"), pages(alpha(self.root)))

    def test_a_summary_is_an_unknown_principle_field(self):
        write_source(
            alpha(self.root) / "principles" / "evidence.md",
            "title: Evidence\nsummary: Brief.",
        )
        self.assertIn(
            "principle.unknown-field",
            codes(alpha(self.root), "warning"),
        )

    def test_a_principle_declaring_an_id_is_refused(self):
        self.assertIn(
            "principle.unexpected-id", self.write("title: Evidence\nid: evidence")
        )

    def test_a_principle_with_no_body_is_refused(self):
        self.assertIn("principle.empty", self.write("title: Evidence", body=""))

    def test_a_principle_pattern_of_the_wrong_shape_is_reported(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["principles"] = [""]
        self.assertIn("content.invalid-principles", codes(alpha(self.root)))


class RootListingTests(unittest.TestCase):
    """The root links to each skill principle without repeating its body."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.pages = pages(alpha(self.root))

    def test_every_skill_principle_is_listed_on_the_root(self):
        placement = inspect_one(alpha(self.root))["principles"]
        self.assertEqual(
            ["evidence", "expenditure", "reporting", "delegation", "provenance"],
            placement["selected"],
        )
        self.assertIn("[Keep observation apart from inference](references/principles/evidence.md)", self.pages[ROOT])

    def test_a_principle_body_reaches_its_own_page_unedited(self):
        source = (alpha(self.root) / "principles" / "provenance.md").read_text(
            encoding="utf-8"
        )
        page = self.pages[principle_path("provenance")]
        for line in source.split("---", 2)[2].splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                with self.subTest(line=line[:40]):
                    self.assertIn(line.strip(), page)

    def test_the_root_links_to_a_principle_without_repeating_its_body(self):
        text = pages(alpha(self.root))[ROOT]
        self.assertIn("[Keep observation apart from inference](references/principles/evidence.md)", text)
        self.assertNotIn("Say which of observed, inferred", text)


class InspectionTests(unittest.TestCase):
    """A principle is ordinary skill source, so `inspect` is where it is read.

    There is no command of its own, for the same reason there is none for tasks
    or facets: a construct with its own verb reads as a special case, and this
    one is not.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def report(self, *extra: str) -> str:
        status, report, stderr = run(
            "inspect", str(alpha(self.root)), "--only", "principles", *extra
        )
        self.assertEqual((0, ""), (status, stderr))
        return report

    def test_the_dimension_names_each_principle_its_source_and_its_placement(self):
        report = self.report()
        self.assertIn("principles 5", report)
        self.assertIn("evidence    principles/evidence.md", report)
        self.assertIn("-> SKILL.md", report)
        self.assertIn("page=references/principles/evidence.md", report)

    def test_a_principle_the_skill_does_not_select_has_no_placement(self):
        write_source(
            alpha(self.root) / "principles" / "spare.md",
            "title: Spare",
            "Named by nothing.",
        )
        status, report, _ = run(
            "inspect", str(alpha(self.root)), "--only", "principles"
        )
        self.assertEqual(0, status)
        self.assertIn("spare", report)
        self.assertIn("-> -", report)

    def test_a_skill_stating_no_principle_reports_none(self):
        for name in ("evidence", "expenditure", "reporting", "delegation", "provenance"):
            (alpha(self.root) / "principles" / f"{name}.md").unlink()
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            del data["content"]["principles"]
            data.pop("principles")
        report = self.report()
        self.assertIn("principles 0", report)

    def test_there_is_no_principles_command(self):
        """Removing it is the point: nothing about a principle is special."""
        import contextlib
        import io

        from degardis.cli import parser

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["principles", "."])
        self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
