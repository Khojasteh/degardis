"""What the generated pages say, and what the compiler refuses to do to them."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis import wording
from degardis.bundlepaths import FACET_INDEX, ROOT, facet_path, guide_path, principle_path, task_path
from degardis.render import (
    PRINCIPLE_BUDGET_BYTES,
    FACET_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
)

from tests.support import (
    alpha,
    codes,
    compiled,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    field_of,
    pages,
    write_source,
    write_text,
)
from tests.support import task_path as source_task


class RootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.pages = pages(alpha(self.root))

    def text(self) -> str:
        return self.pages[ROOT]

    def test_the_root_opens_with_host_frontmatter_then_the_display_name_and_purpose(self):
        lines = self.text().splitlines()
        self.assertEqual(
            [
                "---",
                "name: alpha",
                "description: Carry every construct kind this format defines, in one source.",
                "metadata:",
                "  version: 1.0.0",
                "  generated_by: degardis/2.0.0",
                "  copyright: Copyright (c) 2026 Alpha",
                "  license: MIT",
                "---",
                "# Alpha",
            ],
            lines[:10],
        )
        self.assertIn("Exercise the compiler", self.text())

    def test_the_root_omits_optional_host_fields_that_the_manifest_does_not_declare(self):
        lines = pages(self.root / "beta")[ROOT].splitlines()
        self.assertEqual(
            [
                "---",
                "name: beta",
                "description: A second skill, so discovery and multi-skill builds have one to find.",
                "metadata:",
                "  version: 0.2.0",
                "  generated_by: degardis/2.0.0",
                "---",
                "# Beta",
            ],
            lines[:8],
        )

    def test_the_root_states_every_recognition_cue_under_its_task(self):
        """The cue is what routes a request, and it sits under the link it
        routes to. The route itself is a conformance case."""
        text = self.text()
        self.assertIn(f"[Review a change]({task_path('review')})", text)
        self.assertIn("  - the requester asks for actionable risks in a change", text)

    def test_every_selected_principle_has_a_linkable_page(self):
        self.assertIn(principle_path("delegation"), self.pages)
        self.assertIn("Delegate only a bounded", self.pages[principle_path("delegation")])

    def test_the_root_points_at_the_facet_index_without_listing_facets(self):
        text = self.text()
        self.assertIn(FACET_INDEX, text)
        self.assertNotIn("Legacy code", text)

    def test_the_root_s_sections_appear_in_the_order_a_reader_needs_them(self):
        """Everything above the routing holds whatever the task, and an agent
        that has chosen its task leaves the root, so routing is last."""
        text = self.text()
        order = [
            f"## {wording.READING_HEADING}",
            f"## {wording.PRINCIPLES_HEADING}",
            f"## {wording.FACETS_HEADING}",
            f"## {wording.TASKS_HEADING}",
        ]
        found = [text.index(heading) for heading in order]
        self.assertEqual(sorted(found), found)
        self.assertEqual(
            f"## {wording.TASKS_HEADING}",
            next(line for line in reversed(text.splitlines()) if line.startswith("## ")),
        )

    def test_the_root_carries_no_heading_for_a_section_with_nothing_in_it(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            del data["content"]["facets"]
        text = pages(alpha(self.root))[ROOT]
        self.assertNotIn(f"## {wording.FACETS_HEADING}", text)

    def test_a_one_task_skill_says_so_rather_than_offering_a_choice(self):
        for name in ("repair", "review"):
            source_task(self.root, "alpha", name).unlink()
        text = pages(alpha(self.root))[ROOT]
        self.assertIn(wording.TASKS_SINGLE_LEAD, text)
        self.assertNotIn(wording.TASKS_UNMATCHED, text)

    def test_a_multi_task_root_says_what_to_do_when_nothing_matches(self):
        self.assertIn(wording.TASKS_UNMATCHED, self.text())


class TaskPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.pages = pages(alpha(self.root))

    def page(self, name: str) -> str:
        return self.pages[task_path(name)]

    def checklist(self, field: str) -> str:
        """One field of the guide fixture, from the file that declares it."""
        return field_of(alpha(self.root) / "guides" / "checklist.md", field)

    def test_the_sections_appear_in_the_order_a_reader_needs_them(self):
        text = self.page("review")
        order = [
            f"## {wording.GOAL_HEADING}",
            f"## {wording.APPROACH_HEADING}",
            f"## {wording.KNOWLEDGE_HEADING}",
            f"## {wording.GUIDES_HEADING}",
        ]
        found = [text.index(heading) for heading in order]
        self.assertEqual(sorted(found), found)

    def test_a_section_with_nothing_to_carry_contributes_no_heading(self):
        text = self.page("document")
        self.assertNotIn(f"### {wording.KNOWLEDGE_KIND_HEADINGS['constraint']}", text)
        self.assertNotIn(f"## {wording.PRINCIPLES_HEADING}", text)

    def test_the_page_carries_the_whole_closure_rather_than_a_link_to_it(self):
        text = self.page("review")
        self.assertIn("What a change can reach", text)
        self.assertIn("The surface is what someone outside the change", text)

    def test_a_unit_body_opens_with_its_authored_lead(self):
        text = self.page("review")
        self.assertLess(
            text.index("A change's surface is everything a consumer can observe"),
            text.index("The surface is what someone outside the change"),
        )

    def test_a_unit_body_is_re_levelled_under_the_heading_the_page_gave_it(self):
        text = self.page("repair")
        self.assertIn("#### How this system fails", text)
        self.assertIn("##### Wrong value", text)

    def test_a_task_does_not_repeat_skill_principles(self):
        text = self.page("review")
        self.assertNotIn("Hedges, attributions, and dates are part of a claim", text)

    def test_a_guide_renders_with_its_condition_and_a_resolved_link(self):
        row = wording.GUIDE_ROW_CONDITIONAL.format(
            activation=self.checklist("activation"),
            title=self.checklist("title"),
            link="../guides/checklist.md",
        )
        self.assertIn(row, self.page("review"))

    def test_a_guide_states_the_same_reason_on_every_task_that_names_it(self):
        condition = self.checklist("activation")
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["guides"] = ["checklist"]
        rendered = pages(alpha(self.root))
        self.assertIn(condition, rendered[task_path("document")])
        self.assertIn(condition, rendered[task_path("review")])

    def test_an_unconditional_guide_uses_the_guides_section_without_a_condition(self):
        condition = self.checklist("activation")
        with edit_frontmatter(alpha(self.root) / "guides" / "checklist.md") as fields:
            fields.pop("activation")
        text = pages(alpha(self.root))[task_path("review")]
        self.assertIn(f"## {wording.GUIDES_HEADING}", text)
        self.assertIn(wording.GUIDES_LEAD, text)
        self.assertIn(
            wording.GUIDE_ROW.format(
                title=self.checklist("title"), link="../guides/checklist.md"
            ),
            text,
        )
        self.assertNotIn(condition, text)
        self.assertGreater(
            text.index(f"## {wording.GUIDES_HEADING}"),
            text.index(f"## {wording.KNOWLEDGE_HEADING}"),
        )

    def test_conditional_guides_follow_unconditional_guides(self):
        """One heading holds both readings, and the unconditional one is read first."""
        write_source(
            alpha(self.root) / "guides" / "always.md",
            "title: Always read",
        )
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["guides"].append("always")
        text = pages(alpha(self.root))[task_path("review")]
        self.assertEqual(1, text.count(f"## {wording.GUIDES_HEADING}"))
        self.assertLess(
            text.index("[Always read](../guides/always.md)"),
            text.index(self.checklist("activation")),
        )

    def test_a_guide_is_named_by_its_frontmatter_title(self):
        target = alpha(self.root) / "guides" / "checklist.md"
        target.write_text(
            "---\ntitle: Guide title\n---\n\n# Different heading\n",
            encoding="utf-8",
        )
        self.assertIn(
            "[Guide title](../guides/checklist.md)",
            pages(alpha(self.root))[task_path("review")],
        )

    def test_a_guide_body_does_not_need_a_heading(self):
        target = alpha(self.root) / "guides" / "checklist.md"
        target.write_text(
            "---\ntitle: Boundary checklist\n---\n\n- Result:\n- Boundary:\n",
            encoding="utf-8",
        )
        rendered = pages(alpha(self.root))
        self.assertIn("[Boundary checklist](../guides/checklist.md)", rendered[task_path("review")])
        _, result, _ = compiled(alpha(self.root))
        self.assertTrue(
            result.rendered.pages[guide_path("checklist")].startswith(
                "# Boundary checklist\n\n"
            )
        )

    def test_a_task_body_becomes_the_approach_section(self):
        self.assertIn("Read the whole change before judging any part of it.", self.page("review"))

    def test_custom_construct_metadata_never_reaches_generated_pages(self):
        marker = "metadata-that-must-not-render"
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["x-external"] = {"marker": marker}
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["x-external"] = {"marker": marker}
        with edit_frontmatter(alpha(self.root) / "knowledge" / "change-surface.md") as fields:
            fields["x-external"] = {"marker": marker}
        with edit_frontmatter(alpha(self.root) / "principles" / "evidence.md") as fields:
            fields["x-external"] = {"marker": marker}
        with edit_frontmatter(alpha(self.root) / "facets" / "python.md") as fields:
            fields["x-external"] = {"marker": marker}
        with edit_frontmatter(alpha(self.root) / "guides" / "checklist.md") as fields:
            fields["x-external"] = {"marker": marker}
        rendered = pages(alpha(self.root))
        self.assertNotIn(marker, rendered[ROOT])
        self.assertNotIn(marker, rendered[task_path("review")])
        self.assertNotIn(marker, rendered[principle_path("evidence")])
        self.assertNotIn(marker, rendered[facet_path("python")])
        self.assertNotIn(marker, rendered[guide_path("checklist")])
        for path, text in rendered.items():
            if path != ROOT:
                self.assertNotEqual("---", text.splitlines()[0])

    def test_guide_frontmatter_is_validated_and_omitted_from_the_bundle(self):
        marker = "metadata-that-must-not-render"
        guide = alpha(self.root) / "guides" / "checklist.md"
        write_text(
            guide,
            f"---\ntitle: Checklist\nx-external: {{marker: {marker}}}\n---\n\nGuide body.\n",
        )
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.records)
        text = result.rendered.pages[guide_path("checklist")]
        self.assertEqual("# Checklist", text.splitlines()[0])
        self.assertEqual(1, text.count("# Checklist"))
        self.assertNotIn(marker, text)

    def test_an_unprefixed_guide_field_warns_without_preventing_building(self):
        guide = alpha(self.root) / "guides" / "checklist.md"
        write_text(
            guide,
            "---\ntitle: Checklist\nexternal: partner\n---\n\nGuide body.\n",
        )
        self.assertIn("guide.unknown-field", codes(alpha(self.root), "warning"))
        self.assertNotIn("guide.unknown-field", codes(alpha(self.root)))

    def test_inline_references_render_every_kind(self):
        source = alpha(self.root) / "tasks" / "review.md"
        source.write_text(
            source.read_text(encoding="utf-8")
            + "\nSee [[task:repair]], [[principle:evidence]], [[facet:python]], "
            "[[guide:checklist]], "
            "[[asset:template.md]], and [[script:greet.py]].\n",
            encoding="utf-8",
        )
        text = pages(alpha(self.root))[task_path("review")]
        self.assertIn("[Repair wrong behavior](repair.md)", text)
        self.assertIn("[Keep observation apart from inference](../principles/evidence.md)", text)
        self.assertIn("[Python](../facets/python.md)", text)
        self.assertNotIn(" — The behavior is correct", text)
        self.assertNotIn(" — Say which", text)
        self.assertNotIn(" — Python language", text)
        self.assertIn("[Published interface checklist](../guides/checklist.md)", text)
        self.assertIn("[template.md](../../assets/template.md)", text)
        self.assertIn("[greet.py](../../scripts/greet.py)", text)

    def test_an_inline_reference_note_suffix_stays_literal(self):
        source = alpha(self.root) / "tasks" / "review.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\n[[asset:template.md|note]]\n",
            encoding="utf-8",
        )
        text = pages(alpha(self.root))[task_path("review")]
        self.assertIn("[[asset:template.md|note]]", text)

    def test_an_unknown_inline_target_is_reported(self):
        source = alpha(self.root) / "tasks" / "review.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\n[[task:absent]]\n",
            encoding="utf-8",
        )
        self.assertIn("inline.unknown-target", codes(alpha(self.root)))

    def test_an_unknown_inline_kind_is_reported(self):
        source = alpha(self.root) / "tasks" / "review.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\n[[unknown:review]]\n",
            encoding="utf-8",
        )
        self.assertIn("inline.unknown-kind", codes(alpha(self.root)))


class FacetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def index(self) -> str:
        return pages(alpha(self.root))[FACET_INDEX]

    def test_the_index_tells_the_reader_to_load_every_applicable_facet(self):
        self.assertIn(wording.FACET_INDEX_LEAD, self.index())

    def test_the_index_groups_by_category_when_there_is_more_than_one(self):
        text = self.index()
        self.assertIn("## Language", text)
        self.assertIn("## Timing", text)

    def test_the_index_is_a_flat_list_when_one_category_covers_everything(self):
        """One category over every row is a heading that separates nothing."""
        with edit_frontmatter(alpha(self.root) / "facets" / "urgent.md") as fields:
            fields["category"] = "Language"
        text = pages(alpha(self.root))[FACET_INDEX]
        self.assertNotIn("## Language", text)
        self.assertIn("- [Urgent work]", text)

    def test_a_description_renders_only_where_its_author_wrote_one(self):
        text = self.index()
        self.assertIn("- [Python](python.md) — Python language and ecosystem guidance.", text)
        self.assertIn("- [Legacy code](legacy.md)\n", text)

    def test_the_index_never_repeats_what_a_facet_says(self):
        self.assertNotIn("Characterize before changing", self.index())

    def test_a_facet_page_carries_its_author_s_words_and_no_others(self):
        text = pages(alpha(self.root))[facet_path("python")]
        self.assertIn("# Python", text)
        self.assertIn("Python language and ecosystem guidance.", text)
        self.assertIn("Prefer the standard library", text)

    def test_a_facet_named_for_the_index_is_refused(self):
        source = alpha(self.root) / "facets" / "python.md"
        source.rename(source.with_name("index.md"))
        self.assertIn("facet.reserved-id", codes(alpha(self.root)))

    def test_two_facets_with_one_title_are_refused(self):
        with edit_frontmatter(alpha(self.root) / "facets" / "legacy.md") as fields:
            fields["title"] = "Python"
        self.assertIn("facet.duplicate-title", codes(alpha(self.root)))

    def test_a_facet_guide_renders_last_with_its_own_condition_and_link(self):
        """The reader decides on a separate load after reading the page that
        sent them, so the links come under the guidance rather than above it."""
        guide = alpha(self.root) / "guides" / "toolchain.md"
        row = wording.GUIDE_ROW_CONDITIONAL.format(
            activation=field_of(guide, "activation"),
            title=field_of(guide, "title"),
            link="../guides/toolchain.md",
        )
        text = pages(alpha(self.root))[facet_path("python")]
        self.assertIn(row, text)
        self.assertLess(text.index("Prefer the standard library"), text.index(row))
        self.assertIn(f"## {wording.GUIDES_HEADING}", text)
        self.assertIn(wording.GUIDES_LEAD, text)

    def test_an_unconditional_facet_guide_reads_as_the_facet_s_own_load(self):
        guide = alpha(self.root) / "guides" / "toolchain.md"
        condition = field_of(guide, "activation")
        with edit_frontmatter(guide) as fields:
            fields.pop("activation")
        text = pages(alpha(self.root))[facet_path("python")]
        self.assertIn(
            wording.GUIDE_ROW.format(
                title=field_of(guide, "title"), link="../guides/toolchain.md"
            ),
            text,
        )
        self.assertNotIn(condition, text)

    def test_a_facet_that_names_no_guide_contributes_no_guides_heading(self):
        self.assertNotIn(
            f"## {wording.GUIDES_HEADING}",
            pages(alpha(self.root))[facet_path("urgent")],
        )

    def test_one_guide_named_by_a_task_and_a_facet_reaches_both_pages(self):
        """It stays one page and one condition, wherever it is reached from."""
        rendered = pages(alpha(self.root))
        link = "[Published interface checklist](../guides/checklist.md)"
        self.assertIn(link, rendered[task_path("review")])
        self.assertIn(link, rendered[facet_path("legacy")])

    def test_a_facet_guide_the_manifest_does_not_ship_is_refused(self):
        with edit_frontmatter(alpha(self.root) / "facets" / "python.md") as fields:
            fields["guides"] = ["absent"]
        self.assertIn("facet.unknown-guide", codes(alpha(self.root)))

    def test_a_guide_only_a_facet_names_is_not_reported_as_unreached(self):
        """The facet page is a reader, so the guide is not weight nothing uses."""
        self.assertNotIn("content.unconsumed", codes(alpha(self.root), "warning"))
        with edit_frontmatter(alpha(self.root) / "facets" / "python.md") as fields:
            fields.pop("guides")
        self.assertIn("content.unconsumed", codes(alpha(self.root), "warning"))


class OutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_a_link_to_a_file_the_bundle_does_not_ship_is_refused(self):
        write_source(
            alpha(self.root) / "knowledge" / "linked.md",
            "kind: concept\ntitle: Linked",
            "See [the note](../guides/absent.md).",
        )
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["linked"]
        self.assertIn("output.broken-reference", codes(alpha(self.root)))

    def test_a_generated_page_and_a_copied_file_cannot_claim_one_path(self):
        """A copied file keeps its source-relative path, so it can land on a page.

        Selecting a file already under the generated task path as an asset
        copies it to `references/tasks/`, where the generated task pages are
        written. One would overwrite the other, and which survives would depend
        on the filesystem.
        """
        write_text(alpha(self.root) / "references" / "tasks" / "review.md", "# Copy\n")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["assets"] = ["assets/*.md", "references/tasks/*.md"]
        self.assertIn("output.path-collision", codes(alpha(self.root)))

    def test_a_guide_the_manifest_does_not_ship_is_refused(self):
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["guides"] = ["absent"]
        self.assertIn("task.unknown-guide", codes(alpha(self.root)))

    def test_a_shipped_file_no_task_names_is_warned_about(self):
        write_text(alpha(self.root) / "guides" / "spare.md", "---\ntitle: Spare\n---\n\n# Spare\n")
        self.assertIn("content.unconsumed", codes(alpha(self.root), "warning"))

    def test_a_body_link_counts_as_naming_a_shipped_file(self):
        write_text(alpha(self.root) / "guides" / "spare.md", "---\ntitle: Spare\n---\n\n# Spare\n")
        path = alpha(self.root) / "knowledge" / "change-surface.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text + "\nSee [the spare note](../guides/spare.md).\n", encoding="utf-8"
        )
        self.assertNotIn("content.unconsumed", codes(alpha(self.root), "warning"))

    def test_an_inline_reference_in_a_guide_counts_as_using_a_file(self):
        write_text(alpha(self.root) / "guides" / "spare.md", "---\ntitle: Spare\n---\n\n# Spare\n")
        path = alpha(self.root) / "guides" / "checklist.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nSee [[guide:spare]].\n",
            encoding="utf-8",
        )
        self.assertNotIn("content.unconsumed", codes(alpha(self.root), "warning"))


class BudgetTests(unittest.TestCase):
    """Nothing is dropped to make a page fit; the finding names what is on it."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_an_oversize_task_page_is_reported_with_its_largest_contributors(self):
        write_source(
            alpha(self.root) / "knowledge" / "huge.md",
            "kind: concept\ntitle: Huge",
            "Padding sentence. " * (TASK_BUDGET_BYTES // 10),
        )
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["huge"]
        result = next(
            record
            for record in _records(alpha(self.root))
            if record.code == "render.task-budget"
        )
        self.assertIn("huge", result.message)
        self.assertIn("Largest contributors", result.message)

    def test_nothing_is_dropped_from_an_oversize_page(self):
        marker = "A sentence nothing may remove."
        write_source(
            alpha(self.root) / "knowledge" / "huge.md",
            "kind: concept\ntitle: Huge",
            marker + " Padding. " * (TASK_BUDGET_BYTES // 10),
        )
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["huge"]
        self.assertIn(marker, pages(alpha(self.root))[task_path("document")])

    def test_an_oversize_root_is_reported(self):
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["purpose"] = "Padding sentence. " * (ROOT_BUDGET_BYTES // 10)
        self.assertIn("render.root-budget", codes(alpha(self.root), "warning"))

    def test_an_oversize_principle_page_is_reported(self):
        write_source(
            alpha(self.root) / "principles" / "evidence.md",
            "title: Keep observation apart from inference",
            "Padding sentence. " * (PRINCIPLE_BUDGET_BYTES // 10),
        )
        self.assertIn("render.principle-budget", codes(alpha(self.root), "warning"))

    def test_an_oversize_guide_is_reported(self):
        path = alpha(self.root) / "guides" / "checklist.md"
        path.write_text(
            "---\ntitle: Checklist\n---\n\n" + "Padding sentence. " * (GUIDE_BUDGET_BYTES // 10),
            encoding="utf-8",
        )
        self.assertIn("render.guide-budget", codes(alpha(self.root), "warning"))

    def test_an_oversize_facet_page_is_reported(self):
        path = alpha(self.root) / "facets" / "python.md"
        path.write_text(
            "---\ntitle: Python\ncategory: Language\n---\n\n"
            + "Padding sentence. " * (FACET_BUDGET_BYTES // 10),
            encoding="utf-8",
        )
        self.assertIn("render.facet-budget", codes(alpha(self.root), "warning"))

    def test_a_facet_page_within_its_budget_is_not_reported(self):
        """The fixture's facets are small, so the check has to stay quiet on a
        source that has not crossed it; otherwise the case above would pass
        against a warning raised unconditionally."""
        self.assertNotIn("render.facet-budget", codes(alpha(self.root), "warning"))

    def test_a_non_markdown_guide_is_refused(self):
        path = alpha(self.root) / "guides" / "reference.txt"
        write_text(path, "Padding sentence. " * (GUIDE_BUDGET_BYTES // 10))
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["guides"].append("guides/reference.txt")
        self.assertIn("source.unsupported", codes(alpha(self.root)))


def _records(path: Path):
    _, _, diagnostics = compiled(path)
    return diagnostics.records


if __name__ == "__main__":
    unittest.main()
