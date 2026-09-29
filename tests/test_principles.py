"""Principles as skill-owned source: where one comes from, and where it lands.

The point these cases defend is ownership. A principle is authored in the skill
that uses it, so the compiler supplies none, substitutes none, and can reach none
from anywhere else. A skill's guidance is its own. And a principle holds across
every task, so the skill is the one owner that places it: no task, knowledge
unit, or facet can.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.bundlepaths import ROOT, principle_path
from degardis.markdown import read_markdown

from tests.support import (
    REPO_ROOT,
    alpha,
    codes,
    compiled,
    copy_skills,
    edit_frontmatter,
    conditions_of,
    edit_yaml,
    field_of,
    inspect_one,
    pages,
    run,
    write_source,
)


# The alpha fixture's skill-level principles, in its manifest's order.
ALPHA_PRINCIPLES = ("evidence", "expenditure", "reporting", "delegation", "provenance")


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

    def test_the_message_names_the_missing_id_without_assuming_a_source_path(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"] = ["clear-reporting"]
        _, _, diagnostics = compiled(alpha(self.root))
        message = next(
            record.message
            for record in diagnostics.records
            if record.code == "manifest.unknown-principle"
        )
        self.assertIn("principles names 'clear-reporting'", message)
        self.assertNotIn("principles/clear-reporting.md", message)

    def test_a_principle_the_skill_does_not_select_is_reported(self):
        write_source(
            alpha(self.root) / "principles" / "spare.md",
            "title: Spare",
            "Named by nothing.",
        )
        self.assertIn("principle.unused", codes(alpha(self.root), "warning"))

    def test_a_principle_every_task_names_is_still_unused(self):
        """A task is not an owner, so naming a principle from every task places
        it nowhere: each task warns of a field it does not define, and the
        principle warns that the skill does not name it."""
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"].remove("evidence")
        for task in ("document", "repair", "review"):
            with edit_frontmatter(alpha(self.root) / "tasks" / f"{task}.md") as fields:
                fields["principles"] = ["evidence"]
        warnings = codes(alpha(self.root), "warning")
        self.assertIn("task.unknown-field", warnings)
        self.assertIn("principle.unused", warnings)
        for name, text in pages(alpha(self.root)).items():
            with self.subTest(page=name):
                self.assertNotIn(principle_path("evidence"), text)

    def reference_from_knowledge(self, principle: str, *units: str) -> None:
        for unit in units:
            path = alpha(self.root) / "knowledge" / f"{unit}.md"
            path.write_text(
                path.read_text(encoding="utf-8") + f"\nSee [[principle:{principle}]].\n",
                encoding="utf-8",
            )

    def test_a_principle_only_knowledge_references_stays_unused(self):
        """Carrying the unit makes no task an owner, so the principle still has
        none, and the reference names a principle the bundle ships no page for."""
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"].remove("delegation")
        self.reference_from_knowledge("delegation", "failure-modes")
        _, _, diagnostics = compiled(alpha(self.root))
        found = {(record.code, record.path) for record in diagnostics.records}
        unit = alpha(self.root) / "knowledge" / "failure-modes.md"
        self.assertIn(
            ("principle.unused", alpha(self.root) / "principles" / "delegation.md"),
            found,
        )
        self.assertIn(("inline.unknown-target", unit), found)

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
            ("title: Evidence\napplicability: ''", "principle.invalid-applicability"),
            ("title: Evidence\napplicability: Before a claim", "principle.invalid-applicability"),
            ("title: Evidence\napplicability: []", "principle.invalid-applicability"),
            ("title: Evidence\napplicability: [Before a claim, '']", "principle.invalid-applicability"),
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

    def test_the_root_links_every_skill_principle_without_repeating_its_body(self):
        root = pages(alpha(self.root))[ROOT]
        for name in ALPHA_PRINCIPLES:
            source = alpha(self.root) / "principles" / f"{name}.md"
            with self.subTest(principle=name):
                self.assertIn(
                    f"[{field_of(source, 'title')}]({principle_path(name)})", root
                )
                lead = read_markdown(source).body.splitlines()[0]
                self.assertNotIn(lead, root)


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

    def rows(self) -> dict[str, list[str]]:
        """Each principle row, split into its fields, keyed by principle id."""
        status, report, stderr = run(
            "inspect", str(alpha(self.root)), "--only", "principles"
        )
        self.assertEqual((0, ""), (status, stderr))
        lines = report.splitlines()
        heading = next(line for line in lines if line.startswith("principles "))
        block = lines[lines.index(heading) + 1 :]
        block = block[: block.index("")]
        block = [line for line in block if not line.startswith(" ")]
        self.assertEqual(f"principles {len(block)}", heading)
        return {line.split()[0]: line.split() for line in block}

    def conditions(self, name: str) -> list[str]:
        """The `applicability` lines nested under one principle row, in order."""
        _, report, _ = run("inspect", str(alpha(self.root)), "--only", "principles")
        lines = report.splitlines()
        start = next(
            index for index, line in enumerate(lines) if line.startswith(f"{name} ")
        )
        nested = []
        for line in lines[start + 1 :]:
            if not line.startswith("  applicability "):
                break
            nested.append(line.removeprefix("  applicability "))
        return nested

    def body_bytes(self, name: str) -> str:
        source = alpha(self.root) / "principles" / f"{name}.md"
        return f"{len(read_markdown(source).body.encode('utf-8'))}B"

    def test_the_dimension_names_each_principle_its_source_and_its_placement(self):
        rows = self.rows()
        self.assertEqual(sorted(ALPHA_PRINCIPLES), list(rows))
        self.assertEqual(
            [
                "evidence",
                "principles/evidence.md",
                self.body_bytes("evidence"),
                "->",
                ROOT,
                "linked=none",
                f"page={principle_path('evidence')}",
            ],
            rows["evidence"],
        )

    def test_a_principle_row_names_each_page_whose_authored_text_names_it(self):
        """The root lists this principle; a guide that names it in its own text
        is a page that points a reader at it, reported beside the owner."""
        guide = alpha(self.root) / "guides" / "toolchain.md"
        guide.write_text(
            guide.read_text(encoding="utf-8") + "\nHold to [[principle:evidence]].\n",
            encoding="utf-8",
        )
        self.assertEqual(
            [
                "->",
                ROOT,
                "linked=guide:toolchain",
                f"page={principle_path('evidence')}",
            ],
            self.rows()["evidence"][3:],
        )

    def test_a_conditional_principle_states_its_conditions_once(self):
        """A principle has one `applicability` list, so its owner is listed bare
        and its conditions follow the row once each, in authored order."""
        source = alpha(self.root) / "principles" / "delegation.md"
        line = " ".join(self.rows()["delegation"])
        self.assertEqual(
            f"delegation principles/delegation.md {self.body_bytes('delegation')} "
            f"-> {ROOT} linked=none page={principle_path('delegation')}",
            line,
        )
        self.assertEqual(conditions_of(source), self.conditions("delegation"))

    def test_a_task_carrying_knowledge_that_references_a_principle_only_names_it(self):
        """A knowledge unit owns no principle, so its reference names the
        principle on every task page carrying the unit: those tasks are `linked`
        pages, and the skill stays the one placement."""
        unit = alpha(self.root) / "knowledge" / "change-surface.md"
        unit.write_text(
            unit.read_text(encoding="utf-8") + "\nSee [[principle:delegation]].\n",
            encoding="utf-8",
        )
        line = " ".join(self.rows()["delegation"])
        self.assertEqual(
            f"delegation principles/delegation.md {self.body_bytes('delegation')} "
            f"-> {ROOT} linked=task:review, task:document "
            f"page={principle_path('delegation')}",
            line,
        )

    def test_an_unconditional_principle_has_no_applicability_line(self):
        self.assertEqual([], self.conditions("evidence"))

    def test_a_principle_the_skill_does_not_select_has_no_placement(self):
        write_source(
            alpha(self.root) / "principles" / "spare.md",
            "title: Spare",
            "Named by nothing.",
        )
        self.assertEqual(
            [
                "spare",
                "principles/spare.md",
                self.body_bytes("spare"),
                "->",
                "-",
                "linked=none",
                "page=-",
            ],
            self.rows()["spare"],
        )

    def test_a_skill_stating_no_principle_reports_none(self):
        for name in ALPHA_PRINCIPLES:
            (alpha(self.root) / "principles" / f"{name}.md").unlink()
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            del data["content"]["principles"]
            data.pop("principles")
        self.assertEqual({}, self.rows())


if __name__ == "__main__":
    unittest.main()
