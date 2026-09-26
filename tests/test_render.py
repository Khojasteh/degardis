"""What the generated pages say, and what the compiler refuses to do to them."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis import __version__, wording
from degardis.build import build_skills
from degardis.bundlepaths import (
    FACET_INDEX,
    ICON_OUTPUTS,
    OPENAI_METADATA,
    REGISTER,
    ROOT,
    facet_path,
    guide_path,
    principle_path,
    task_path,
)
from degardis.model import Diagnostics
from degardis.package import openai_metadata
from degardis.render import (
    PRINCIPLE_BUDGET_BYTES,
    FACET_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
    LinkUse,
)
from degardis.validate import _check_outputs as check_outputs

from tests.support import (
    alpha,
    codes,
    compiled,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    field_of,
    folder_names,
    inspect_one,
    pages,
    write_raster_icon,
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
                'description: "Carry every construct kind this format defines, in one source."',
                "metadata:",
                '  version: "1.0.0"',
                f"  generated_by: degardis/{__version__}",
                '  copyright: "Copyright (c) 2026 Alpha"',
                '  license: "MIT"',
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
                'description: "A second skill, so discovery and multi-skill builds have one to find."',
                "metadata:",
                '  version: "0.2.0"',
                f"  generated_by: degardis/{__version__}",
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
            f"## {wording.REGISTER_HEADING}",
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


class HostMetadataTests(unittest.TestCase):
    """What a host parses as YAML reads back as the value the manifest states.

    A host discovers a skill from its frontmatter and displays it from its
    interface metadata, so a value YAML reads differently from what the author
    wrote is a skill the host misnames, truncates, or cannot load at all.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def frontmatter(self) -> dict:
        text = pages(alpha(self.root))[ROOT]
        _, block, _ = text.split("---\n", 2)
        return yaml.safe_load(block)

    def test_every_root_frontmatter_value_reads_back_as_the_manifest_states_it(self):
        values = {
            "description": "Summarize notes: key points, as tracked in #42.\nThen stop.",
            "version": "1.10",
            "copyright": "Copyright: 2026 Alpha #1",
            "license": "'MIT' or \"Apache-2.0\"",
        }
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data.update(values)
        fields = self.frontmatter()
        self.assertEqual(values["description"], fields["description"])
        for key in ("version", "copyright", "license"):
            with self.subTest(key=key):
                self.assertEqual(values[key], fields["metadata"][key])

    def test_interface_metadata_reads_back_characters_beyond_the_basic_plane(self):
        """libyaml refuses the surrogate pairs a JSON escape would write."""
        interface = {
            "display_name": "Alpha \N{MEMO}",
            "short_description": "Notes \N{MEMO} kept",
            "default_prompt": "Use alpha \N{MEMO}.",
        }
        metadata = openai_metadata(interface, {}, "alpha")
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        read = yaml.load(metadata, Loader=loader)["interface"]
        self.assertEqual(interface["display_name"], read["display_name"])
        self.assertEqual(interface["short_description"], read["short_description"])


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
        self.assertTrue(
            rendered[guide_path("checklist")].startswith("# Boundary checklist\n\n")
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

    def test_a_known_kind_this_skill_ships_none_of_names_an_unknown_target(self):
        """The kind is right and the target is missing, so the repair is the target."""
        source = self.root / "beta" / "tasks" / "note.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nSee [[guide:absent]].\n",
            encoding="utf-8",
        )
        found = codes(self.root / "beta")
        self.assertIn("inline.unknown-target", found)
        self.assertNotIn("inline.unknown-kind", found)

    def append_to_review(self, text: str) -> None:
        source = alpha(self.root) / "tasks" / "review.md"
        source.write_text(source.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_an_inline_reference_in_nested_list_content_is_resolved(self):
        """Indentation inside a list is the list's, not an indented code block."""
        self.append_to_review(
            "\n- Before merging:\n  - Check the interface:\n"
            "    - Open [[guide:checklist]] first.\n"
            "\n10. Then report.\n\n    Name [[task:repair]] as the follow-up.\n"
        )
        page = pages(alpha(self.root))[task_path("review")]
        self.assertIn(
            "Open [Published interface checklist](../guides/checklist.md) first.", page
        )
        self.assertIn("Name [Repair wrong behavior](repair.md) as", page)
        self.assertNotIn("[[", page)

    def test_an_unknown_target_in_nested_list_content_is_reported(self):
        self.append_to_review("\n- Before merging:\n  - Check:\n    - Open [[guide:absent]].\n")
        self.assertIn("inline.unknown-target", codes(alpha(self.root)))

    def test_a_link_in_a_code_sample_is_left_exactly_as_written(self):
        """A sample shows link syntax; it is not a link the bundle has to resolve."""
        write_source(
            alpha(self.root) / "knowledge" / "samples.md",
            "kind: guidance\ntitle: Linking samples",
            "Link like this:\n\n```markdown\nSee [the setup guide](setup.md).\n```\n\n"
            "Or inline: `[the notes](notes.md)`.\n\n"
            "    [indented](indented.md)\n",
        )
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["change-surface", "samples"]
        self.assertEqual(set(), codes(alpha(self.root)))
        page = pages(alpha(self.root))[task_path("document")]
        self.assertIn("\nSee [the setup guide](setup.md).\n", page)
        self.assertIn("`[the notes](notes.md)`", page)
        self.assertIn("    [indented](indented.md)", page)

    def test_a_title_written_across_lines_stays_on_the_line_it_labels(self):
        """A heading, a route, or a list row ends at its first newline."""
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["title"] = "Review\na change"
            fields["recognize"] = ["the requester asks\nfor risks"]
        with edit_frontmatter(alpha(self.root) / "guides" / "checklist.md") as fields:
            fields["activation"] = "When the change\ntouches an interface"
        rendered = pages(alpha(self.root))
        self.assertIn("# Review a change\n", rendered[task_path("review")])
        self.assertIn(f"**[Review a change]({task_path('review')})**", rendered[ROOT])
        self.assertIn("  - the requester asks for risks\n", rendered[ROOT])
        self.assertIn(
            "- When the change touches an interface: [Published interface checklist]",
            rendered[task_path("review")],
        )


class RegisterTests(unittest.TestCase):
    """The form the root hands the agent in place of a directory listing."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def register(self) -> str:
        return pages(alpha(self.root))[REGISTER]

    def rows(self) -> list[list[str]]:
        """The principle and guide rows, between the task record and the ledger."""
        _, _, after_record = self.register().partition(
            f"## {wording.TASK_RECORD_HEADING}\n"
        )
        _, _, page_tables = after_record.partition("\n## ")
        page_tables, _, _ = page_tables.partition(
            f"## {wording.CONFORMANCE_HEADING}"
        )
        return [
            self.cells(line)
            for line in page_tables.splitlines()
            if line.startswith("|") and not line.startswith(("|Id|", "|---|"))
        ]

    def row(self, identifier: str) -> list[str]:
        return next(row for row in self.rows() if row[0] == identifier)

    @staticmethod
    def cells(line: str) -> list[str]:
        """One line's cells, splitting where a Markdown reader would.

        An escaped pipe is a character inside a cell, so a naive split reports
        the very column shift the escaping exists to prevent.
        """
        return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]

    def test_the_form_carries_no_prose_of_its_own(self):
        """It is a template to copy and fill, not something to read. What the
        columns mean is stated on the root that sends the agent here, so a copy
        taken today cannot disagree with a rule reworded tomorrow."""
        lines = [line for line in self.register().splitlines() if line.strip()]
        for line in lines:
            with self.subTest(line=line):
                self.assertTrue(line.startswith(("#", "|")), line)

    def test_every_cell_the_agent_owns_starts_at_one_resting_value(self):
        """Which pages a run needs is the agent's to decide, so the compiler
        supplies what the source says and judges none of it."""
        rows = self.rows()
        self.assertNotEqual([], rows)
        for row in rows:
            with self.subTest(row=row):
                self.assertEqual(len(wording.REGISTER_COLUMNS), len(row))
                self.assertEqual(wording.REGISTER_EMPTY, row[2])
                self.assertEqual(wording.REGISTER_EMPTY, row[3])
                self.assertEqual(wording.REGISTER_EMPTY, row[4])

    def test_the_resting_value_is_one_an_agent_can_type_anywhere(self):
        """An agent resets a cell by writing this value back, often through a
        shell command, and a shell that mangles or refuses a non-ASCII
        character turns a reset into a failed or corrupted update."""
        self.assertTrue(wording.REGISTER_EMPTY.isascii())

    def test_the_rules_name_the_resting_value_the_form_uses(self):
        """The form carries no prose, so the root is the only place an agent
        learns what a placeholder means; one the rules never mention is one the
        agent has to guess at. A row's `Applies when` needs no such entry: it is
        read as the condition it states, `always` included."""
        self.assertIn(f"`{wording.REGISTER_EMPTY}`", wording.REGISTER_INSTRUCTIONS)

    def test_a_construct_that_states_no_condition_is_not_pre_judged(self):
        """A verdict follows from encountering a link, and nothing has been
        encountered when the form is copied. Filling one in would hand the
        agent a decision it has not reached and cannot see the basis for."""
        self.assertEqual(wording.REGISTER_EMPTY, self.row("reporting")[2])

    def test_no_condition_is_stated_rather_than_left_unfilled(self):
        """`Applies when` is the source's statement, not a cell awaiting the agent.
        Written with the resting value, an unconditional row would read as a
        condition nobody has filled in yet."""
        self.assertEqual(wording.REGISTER_UNCONDITIONAL, self.row("reporting")[1])
        self.assertNotEqual(wording.REGISTER_EMPTY, wording.REGISTER_UNCONDITIONAL)

    def test_a_conditional_construct_arrives_beside_its_condition(self):
        """A listing of the directories would give names and nothing else,
        leaving the agent to open a page to learn whether it had to."""
        activation = field_of(alpha(self.root) / "guides" / "checklist.md", "activation")
        self.assertEqual(activation, self.row("checklist")[1])

    def test_a_row_names_a_construct_by_the_id_its_filename_carries(self):
        """Identity is the file stem, so a renamed file is a renamed row and
        the agent matches this table to a page by the same name either way."""
        (alpha(self.root) / "guides" / "checklist.md").rename(
            alpha(self.root) / "guides" / "interface-checklist.md"
        )
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["guides"] = ["interface-checklist"]
        ids = [row[0] for row in self.rows()]
        self.assertIn("interface-checklist", ids)
        self.assertNotIn("checklist", ids)

    def test_tables_are_compact_markdown(self):
        """The copied ledger is machine-facing state, so alignment padding is
        byte cost without meaning while Markdown still needs valid separators."""
        for table in self.register().split("## ")[1:]:
            lines = [line for line in table.splitlines() if line.startswith("|")]
            with self.subTest(table=table.splitlines()[0]):
                self.assertTrue(all("| " not in line and " |" not in line for line in lines))
                self.assertIn("|---|", lines[1])

    def test_an_authored_condition_stays_inside_one_cell(self):
        """An activation is prose, and a pipe or a wrap in it would end the
        cell early and shift every column after it."""
        with edit_frontmatter(alpha(self.root) / "guides" / "checklist.md") as fields:
            fields["activation"] = "When the change touches an API | a schema"
        row = self.row("checklist")
        self.assertEqual(len(wording.REGISTER_COLUMNS), len(row))
        self.assertEqual(r"When the change touches an API \| a schema", row[1])

    def test_the_register_separates_principles_from_guides(self):
        """They are two namespaces to the author and two rules to the agent,
        and a bare id only names one construct inside one of them."""
        principles, _, guides = self.register().partition(
            f"## {wording.GUIDES_HEADING}"
        )
        self.assertIn(f"## {wording.PRINCIPLES_HEADING}", principles)
        self.assertIn("reporting", self.ids_in(principles))
        self.assertIn("checklist", self.ids_in(guides))
        self.assertNotIn("checklist", principles)
        self.assertNotIn("reporting", guides)

    def ids_in(self, section: str) -> list[str]:
        return [
            self.cells(line)[0]
            for line in section.splitlines()
            if line.startswith("|") and not line.startswith(("|Id|", "|---|"))
        ]


class GeneratedNameTests(unittest.TestCase):
    """What happens when the source already occupies a name the compiler wants."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        write_raster_icon(alpha(self.root) / "brand.png", (10, 20, 30, 255))
        for target in (REGISTER, *ICON_OUTPUTS.values()):
            write_text(alpha(self.root) / target, "author's own file")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["interface"]["icon"] = "brand.png"
            data["content"]["assets"] = ["assets/*.md", "assets/*.png"]

    def test_the_author_s_file_keeps_the_address_and_builds_clean(self):
        """The author wrote that file on purpose. A name this compiler chose is
        the one that gives way, and a build that refused would be refusing over
        a name the author never agreed to reserve."""
        self.assertEqual(set(), codes(alpha(self.root)))

    def test_each_generated_file_is_written_beside_it_under_a_free_name(self):
        _, result, _ = compiled(alpha(self.root))
        addresses = result.content.addresses
        self.assertNotEqual(REGISTER, addresses.register)
        for role, preferred in ICON_OUTPUTS.items():
            with self.subTest(role=role):
                self.assertNotEqual(preferred, addresses.icons[role])
        self.assertNotIn(
            addresses.register,
            {REGISTER, *ICON_OUTPUTS.values()},
        )

    def test_whatever_points_at_a_moved_file_points_at_where_it_went(self):
        """A reassignment nothing followed would leave the root naming a file
        that is not there, which is worse than the collision it avoided."""
        _, result, _ = compiled(alpha(self.root))
        addresses = result.content.addresses
        root = result.rendered.page_texts()[ROOT]
        self.assertIn(addresses.register, root)
        self.assertNotIn(REGISTER, root)
        self.assertIn(addresses.register, result.rendered.pages)
        metadata = openai_metadata(
            result.content.skill.interface,
            result.content.icon_addresses,
            result.content.skill.name,
        )
        for address in addresses.icons.values():
            with self.subTest(address=address):
                self.assertIn(f"./{address}", metadata)

    def test_the_build_writes_both_the_author_s_file_and_the_generated_one(self):
        workspace = Path(self.directory.name) / "out"
        artifact = build_skills(alpha(self.root), workspace)[0]
        _, result, _ = compiled(alpha(self.root))
        names = folder_names(artifact)
        for preferred in (REGISTER, *ICON_OUTPUTS.values()):
            with self.subTest(preferred=preferred):
                self.assertIn(preferred, names)
                self.assertEqual(
                    "author's own file",
                    (artifact / preferred).read_text(encoding="utf-8"),
                )
        self.assertIn(result.content.addresses.register, names)
        for address in result.content.addresses.icons.values():
            with self.subTest(address=address):
                self.assertIn(address, names)


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

    def test_a_facet_named_index_keeps_its_page_and_the_index_moves(self):
        """`index` is this compiler's name for the index, not a name the author
        may not use. A file stem is a construct's identity, so the facet keeps
        the address its filename gives it and the index is written beside it.
        """
        source = alpha(self.root) / "facets" / "python.md"
        source.rename(source.with_name("index.md"))
        _, result, _ = compiled(alpha(self.root))
        index = result.content.addresses.facet_index
        self.assertNotEqual(FACET_INDEX, index)
        self.assertEqual(set(), codes(alpha(self.root)))
        self.assertIn("Python language and ecosystem guidance", pages(alpha(self.root))[FACET_INDEX])
        self.assertIn(wording.FACET_INDEX_LEAD, result.rendered.pages[index])
        self.assertIn(index, result.rendered.page_texts()[ROOT])

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

    def test_a_link_by_path_is_refused_at_the_file_that_wrote_it(self):
        """Bundle content is linked by inline reference, which the compiler places.

        A path is written from the author's file and read from a page elsewhere,
        so it would name the wrong file, and the finding belongs to the file the
        author has to edit rather than to every page carrying the text.
        """
        linked = alpha(self.root) / "knowledge" / "linked.md"
        write_source(
            linked, "kind: concept\ntitle: Linked", "See [the note](../guides/absent.md)."
        )
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["linked"]
        records = [
            record
            for record in inspect_one(alpha(self.root))["diagnostics"]
            if record.code == "link.internal-path"
        ]
        self.assertEqual([linked], [record.path for record in records])
        self.assertIn("../guides/absent.md", records[0].message)

    def test_every_markdown_form_of_a_link_by_path_is_refused(self):
        forms = (
            "[the note](../guides/checklist.md)",
            "![a diagram](../assets/template.md)",
            "[titled](checklist.md 'A title')",
            "[titled](checklist.md (A title))",
            "[bracketed](<../guides/checklist.md>)",
            "[by reference][note]\n\n[note]: ../assets/template.md",
            '<a href="../guides/checklist.md">the note</a>',
            "[rooted](/guides/checklist.md)",
        )
        for index, form in enumerate(forms):
            with self.subTest(form=form):
                root = copy_skills(Path(self.directory.name) / f"form{index}")
                source = source_task(root, "alpha", "review")
                source.write_text(
                    source.read_text(encoding="utf-8") + f"\n{form}\n", encoding="utf-8"
                )
                self.assertIn("link.internal-path", codes(alpha(root)))

    def test_an_external_link_or_an_anchor_is_left_as_written(self):
        text = (
            "See [the site](https://example.test/x), [mail](mailto:a@b.test), "
            "and [the goal](#goal)."
        )
        source = source_task(self.root, "alpha", "review")
        source.write_text(source.read_text(encoding="utf-8") + f"\n{text}\n", encoding="utf-8")
        self.assertEqual(set(), codes(alpha(self.root)))
        self.assertIn(text, pages(alpha(self.root))[task_path("review")])

    def test_a_generated_link_to_a_file_the_bundle_does_not_ship_is_refused(self):
        """Every link the compiler writes is checked against what the build ships.

        No source can produce one now that authored links go through inline
        references, so the case plants one: the check exists to catch the
        compiler itself naming a page it did not write.
        """
        _, result, _ = compiled(alpha(self.root))
        result.rendered.links.append(LinkUse(target=guide_path("absent"), page=ROOT))
        diagnostics = Diagnostics()
        check_outputs(result, diagnostics)
        self.assertEqual(
            ["output.broken-reference"], [record.code for record in diagnostics.records]
        )

    def test_a_copied_file_differing_from_a_generated_one_only_in_case_is_refused(self):
        """A case-insensitive file system writes both names to one file."""
        write_text(alpha(self.root) / "Skill.md", "x")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["assets"] = ["assets/*.md", "Skill.md"]
        self.assertIn("output.path-collision", codes(alpha(self.root)))

    def test_a_compiler_named_file_yields_to_a_source_file_differing_only_in_case(self):
        write_text(alpha(self.root) / "assets" / "Instruction-Register.md", "x")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["assets"] = ["assets/*.md"]
        _, result, _ = compiled(alpha(self.root))
        self.assertNotEqual(REGISTER.casefold(), result.content.addresses.register.casefold())
        self.assertNotIn("output.path-collision", codes(alpha(self.root)))

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

    def test_a_copied_file_on_a_name_the_host_owns_is_refused(self):
        """These two addresses are the host's, not this compiler's.

        A host finds a skill by opening `SKILL.md` and reads its interface from
        `agents/openai.yaml`, so neither can be written anywhere else to make
        room. Nothing can be reassigned, so the author is told instead.
        """
        for target in (ROOT, OPENAI_METADATA):
            with self.subTest(target=target):
                directory = tempfile.TemporaryDirectory()
                self.addCleanup(directory.cleanup)
                root = copy_skills(Path(directory.name))
                write_text(alpha(root) / target, "x")
                with edit_yaml(alpha(root) / "skill.yaml") as data:
                    data["content"]["assets"] = ["assets/*.md", target]
                self.assertIn("output.path-collision", codes(alpha(root)))

    def test_a_guide_the_manifest_does_not_ship_is_refused(self):
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["guides"] = ["absent"]
        self.assertIn("task.unknown-guide", codes(alpha(self.root)))

    def test_a_shipped_file_no_task_names_is_warned_about(self):
        write_text(alpha(self.root) / "guides" / "spare.md", "---\ntitle: Spare\n---\n\n# Spare\n")
        self.assertIn("content.unconsumed", codes(alpha(self.root), "warning"))

    def test_a_guide_that_is_not_markdown_is_refused(self):
        write_text(alpha(self.root) / "guides" / "reference.txt", "Reference notes.")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"]["guides"].append("guides/reference.txt")
        self.assertIn("source.unsupported", codes(alpha(self.root)))

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
        self.assertEqual(source_task(self.root, "alpha", "document"), result.path)
        self.assertIn("huge", result.message)

    def test_a_task_page_exactly_at_its_budget_is_not_reported_and_one_byte_over_is(self):
        """The budget is what one load may cost, so a page that costs exactly
        that fits. The page is grown one byte of a unit body at a time, so its
        size is measured rather than predicted."""
        unit = alpha(self.root) / "knowledge" / "padding.md"
        with edit_frontmatter(source_task(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["padding"]

        def compiled_at(length: int) -> tuple[int, set[str]]:
            write_source(unit, "kind: fact\ntitle: Padding", "x" * length)
            _, result, diagnostics = compiled(alpha(self.root))
            size = result.rendered.page_bytes(task_path("document"))
            return size, {record.code for record in diagnostics.records}

        size, _ = compiled_at(1)
        at_budget = 1 + TASK_BUDGET_BYTES - size
        size, found = compiled_at(at_budget)
        self.assertEqual(TASK_BUDGET_BYTES, size)
        self.assertNotIn("render.task-budget", found)
        size, found = compiled_at(at_budget + 1)
        self.assertEqual(TASK_BUDGET_BYTES + 1, size)
        self.assertIn("render.task-budget", found)

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


def _records(path: Path):
    _, _, diagnostics = compiled(path)
    return diagnostics.records


if __name__ == "__main__":
    unittest.main()
