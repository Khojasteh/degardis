"""Placement: which knowledge reaches a page, and where each principle is stated.

These are the decisions the compiler makes on the author's behalf, so they are
the decisions an author has to be able to predict. Each case here names one of
them.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.analysis import measure, plan_skill
from degardis.bundlepaths import guide_path
from degardis.markdown import read_markdown
from degardis.sources import SourceSet

from tests.support import (
    alpha,
    codes,
    compiled,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    inspect_one,
    task_path,
    write_source,
)


class SkillPrincipleTests(unittest.TestCase):
    """The skill, rather than each task, selects its shared principles."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        _, self.result, _ = compiled(alpha(self.root))
        self.principles = self.result.plan.principles

    def test_the_skill_selection_keeps_manifest_order(self):
        self.assertEqual(
            ["evidence", "expenditure", "reporting", "delegation", "provenance"],
            [item.id for item in self.principles],
        )

    def test_an_unknown_skill_principle_is_reported(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"].append("clear-reporting")
        _, result, _ = compiled(alpha(self.root))
        self.assertEqual(
            ["evidence", "expenditure", "reporting", "delegation", "provenance"],
            [item.id for item in result.plan.principles],
        )
        self.assertIn("manifest.unknown-principle", codes(alpha(self.root)))


class TaskClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def plan(self):
        _, result, _ = compiled(alpha(self.root))
        return result.plan

    def test_a_task_carries_the_knowledge_it_named(self):
        item = self.plan().task("review")
        self.assertEqual(
            ("evidence-required", "order-findings", "house-limits"),
            item.direct,
        )

    def test_a_requirement_is_compiled_in_rather_than_left_as_a_lookup(self):
        """The source decomposition is the author's; it is not a route."""
        item = self.plan().task("review")
        self.assertEqual(("change-surface",), item.required)
        self.assertIn("change-surface", [unit.key for unit in item.closure])

    def test_kind_order_controls_the_rendered_closure(self):
        item = self.plan().task("review")
        self.assertEqual(
            ["change-surface", "house-limits", "evidence-required", "order-findings"],
            [unit.key for unit in item.closure],
        )
        self.assertEqual(
            ["concept", "fact", "constraint", "guidance"],
            [unit.kind for unit in item.closure],
        )

    def test_author_order_is_preserved_within_one_kind(self):
        path = task_path(self.root, "alpha", "repair")
        with edit_frontmatter(path) as fields:
            fields["knowledge"] = ["failure-modes", "change-surface"]
        item = self.plan().task("repair")
        self.assertEqual(
            ["failure-modes", "change-surface"],
            [unit.id for unit in item.of_kind("concept")],
        )

    def test_a_unit_two_tasks_need_is_compiled_into_both_pages(self):
        carriers = {
            row["key"]: row["tasks"]
            for row in inspect_one(alpha(self.root))["knowledge"]
        }
        self.assertEqual(
            ["document", "review"], sorted(carriers["change-surface"])
        )

    def test_a_reference_naming_no_selected_file_is_reported(self):
        with edit_frontmatter(task_path(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        self.assertIn("task.unknown-knowledge", codes(alpha(self.root)))

    def test_a_requirement_naming_no_selected_file_is_reported(self):
        path = alpha(self.root) / "knowledge" / "order-findings.md"
        with edit_frontmatter(path) as fields:
            fields["requires"] = ["nowhere"]
        self.assertIn("knowledge.unknown-requires", codes(alpha(self.root)))

    def test_a_requirement_cycle_is_reported_rather_than_broken_silently(self):
        knowledge = alpha(self.root) / "knowledge"
        with edit_frontmatter(knowledge / "change-surface.md") as fields:
            fields["requires"] = ["failure-modes"]
        with edit_frontmatter(knowledge / "failure-modes.md") as fields:
            fields["requires"] = ["change-surface"]
        self.assertIn("knowledge.requirement-cycle", codes(alpha(self.root)))

    def test_one_cycle_is_one_finding_wherever_the_walk_entered_it(self):
        """Entered from either unit, a cycle is the same loop and the same repair."""
        knowledge = alpha(self.root) / "knowledge"
        with edit_frontmatter(knowledge / "change-surface.md") as fields:
            fields["requires"] = ["failure-modes"]
        with edit_frontmatter(knowledge / "failure-modes.md") as fields:
            fields["requires"] = ["change-surface"]
        with edit_frontmatter(task_path(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["change-surface", "failure-modes"]
        found = [
            record
            for record in inspect_one(alpha(self.root))["diagnostics"]
            if record.code == "knowledge.requirement-cycle"
        ]
        self.assertEqual(1, len(found))

    def test_knowledge_no_task_reaches_is_warned_about(self):
        write_source(
            alpha(self.root) / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
        self.assertIn("knowledge.orphan", codes(alpha(self.root), "warning"))

    def test_a_task_whose_page_would_restate_the_router_is_warned_about(self):
        path = task_path(self.root, "alpha", "document")
        write_source(
            path,
            "title: Document what exists\n"
            "cues:\n- the requester asks for reader-facing text\n"
            "goal: A reader can act on the text alone.\n",
            body="",
        )
        self.assertIn("task.empty", codes(alpha(self.root), "warning"))

    def test_a_task_carrying_only_a_hand_off_is_not_reported_as_empty(self):
        """A hand-off is placed from a declaration, so the page carries more
        than the goal its router entry could have stated."""
        path = task_path(self.root, "alpha", "document")
        write_source(
            path,
            "title: Document what exists\n"
            "cues:\n- the requester asks for reader-facing text\n"
            "goal: A reader can act on the text alone.\n"
            "handoffs:\n- task: review\n",
            body="",
        )
        self.assertNotIn("task.empty", codes(alpha(self.root), "warning"))


class GuideRequirementTests(unittest.TestCase):
    """A guide's `requires` is the guide's own list, and is checked like
    knowledge `requires`: each name must resolve, and the chain must end."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.guides = alpha(self.root) / "guides"

    def test_a_requirement_an_owner_also_names_is_on_both_lists(self):
        """Each page lists what it owns, so a guide the owner names keeps its
        declared place there and stays on the list of the guide requiring it."""
        with edit_frontmatter(task_path(self.root, "alpha", "review")) as fields:
            fields["guides"] = ["compatibility", "checklist"]
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.records)
        self.assertEqual(
            ("compatibility", "checklist"), result.plan.task("review").guides
        )
        self.assertEqual(("compatibility",), result.plan.guide("checklist").guides)

    def test_a_requirement_naming_no_selected_guide_is_reported(self):
        with edit_frontmatter(self.guides / "checklist.md") as fields:
            fields["requires"] = ["compatibility", "nowhere"]
        _, result, diagnostics = compiled(alpha(self.root))
        found = [
            (record.code, record.path)
            for record in diagnostics.records
            if record.code == "guide.unknown-requires"
        ]
        self.assertEqual(
            [("guide.unknown-requires", self.guides / "checklist.md")], found
        )
        self.assertEqual(
            ("compatibility", "nowhere"), result.plan.guide("checklist").guides
        )
        page = result.rendered.pages[guide_path("checklist")]
        self.assertIn("](compatibility.md)", page)
        self.assertNotIn("nowhere", page)

    def test_a_guide_no_owner_reaches_still_has_its_requirements_checked(self):
        """A requirement is a fact about the file that declares it, so it is
        checked whether or not anything opens that file yet."""
        write_source(
            self.guides / "spare.md", "title: Spare\nrequires:\n- nowhere", "Spare."
        )
        self.assertIn("guide.unknown-requires", codes(alpha(self.root)))

    def test_a_guide_requirement_cycle_is_one_finding(self):
        with edit_frontmatter(self.guides / "compatibility.md") as fields:
            fields["requires"] = ["checklist"]
        _, _, diagnostics = compiled(alpha(self.root))
        found = [
            record.message
            for record in diagnostics.records
            if record.code == "guide.requirement-cycle"
        ]
        self.assertEqual(1, len(found))
        self.assertIn("checklist -> compatibility -> checklist", found[0])

    def test_a_guide_requiring_itself_is_a_cycle(self):
        with edit_frontmatter(self.guides / "toolchain.md") as fields:
            fields["requires"] = ["toolchain"]
        self.assertIn("guide.requirement-cycle", codes(alpha(self.root)))


class QualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def measured(self):
        _, result, _ = compiled(alpha(self.root))
        return measure(result.plan, result.content.sources)

    def test_quality_counts_what_the_placement_produced(self):
        quality = self.measured()
        self.assertEqual(3, quality.tasks)
        self.assertEqual(5, quality.principles)

    def test_duplicated_bytes_report_what_closure_repeated(self):
        """A unit on two pages is compiled twice; that is the cost of one load.

        Measured as the difference the second carrier makes, so the number has
        to be the repeated unit's own bytes rather than any total that happens
        to be above zero.
        """
        unit = alpha(self.root) / "knowledge" / "change-surface.md"
        carried_twice = len(read_markdown(unit).body.encode("utf-8"))
        before = self.measured().duplicated_bytes
        with edit_frontmatter(task_path(self.root, "alpha", "document")) as fields:
            fields.pop("knowledge")
        self.assertEqual(carried_twice, before - self.measured().duplicated_bytes)

    def test_a_unit_written_twice_is_reported_as_a_near_duplicate(self):
        source = (alpha(self.root) / "knowledge" / "failure-modes.md").read_text(
            encoding="utf-8"
        )
        (alpha(self.root) / "knowledge" / "failure-shapes.md").write_text(
            source.replace("How this system fails", "How this system breaks"),
            encoding="utf-8",
        )
        pairs = {
            tuple(sorted((left, right)))
            for left, right, _ in self.measured().near_duplicates
        }
        self.assertIn(
            ("failure-modes", "failure-shapes"), pairs
        )

    def test_measuring_a_source_with_no_task_reports_zeroes_rather_than_failing(self):
        """Every coverage ratio divides by a count a broken source can zero."""
        empty = SourceSet()
        quality = measure(plan_skill(empty), empty)
        self.assertEqual(0, quality.tasks)
        self.assertEqual(0.0, quality.constraint_ratio)


if __name__ == "__main__":
    unittest.main()
