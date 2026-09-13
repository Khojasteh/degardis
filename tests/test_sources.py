"""Reading one source file: its identity, its fields, and its body."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.markdown import read_markdown
from degardis.model import Diagnostics, SourceError
from degardis.sources import (
    read_knowledge,
    read_principle,
    read_facet,
    read_task,
)

from tests.support import (
    alpha,
    codes,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    task_path,
    write_source,
    write_text,
)


TASK = """\
title: Review a change
recognize:
- the requester asks for risks in a change
goal: Every actionable risk is named.
"""


class ReaderHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def read(self, reader, name: str, fields: str, body: str = "Body text."):
        path = self.root / name
        write_source(path, fields, body)
        diagnostics = Diagnostics()
        construct = reader(read_markdown(path), diagnostics)
        return construct, {record.code for record in diagnostics.records}

    def task(self, fields: str, body: str = "Body text.", name="tasks/review.md"):
        return self.read(read_task, name, fields, body)

    def facet(self, fields: str, body: str = "Body text."):
        return self.read(read_facet, "facets/python.md", fields, body)

    def principle(self, fields: str, body: str = "Body text."):
        return self.read(read_principle, "principles/evidence.md", fields, body)

    def knowledge(self, fields: str, body: str = "Body text."):
        path = self.root / "knowledge" / "change-surface.md"
        write_source(path, fields, body)
        diagnostics = Diagnostics()
        construct = read_knowledge(read_markdown(path), diagnostics)
        return construct, {record.code for record in diagnostics.records}


class TaskReaderTests(ReaderHarness):
    def test_a_task_is_read_with_its_id_taken_from_the_filename(self):
        task, found = self.task(TASK)
        self.assertEqual(set(), found)
        self.assertEqual("review", task.id)
        self.assertEqual("Review a change", task.title)
        self.assertEqual(("the requester asks for risks in a change",), task.recognize)
        self.assertEqual("Every actionable risk is named.", task.goal)
        self.assertEqual("Body text.", task.body)

    def test_a_task_declaring_an_id_is_refused(self):
        _, found = self.task(TASK + "id: review\n")
        self.assertIn("task.unexpected-id", found)

    def test_a_task_keeps_prefixed_custom_metadata_without_using_it(self):
        task, found = self.task(TASK + "x-owner: writing-team\nx-tags: [review, draft]\n")
        self.assertEqual(set(), found)
        self.assertEqual(
            {"x-owner": "writing-team", "x-tags": ["review", "draft"]},
            task.metadata,
        )

    def test_an_unprefixed_task_field_warns_without_preventing_reading(self):
        task, found = self.task(TASK + "owner: writing-team\n")
        self.assertIsNotNone(task)
        self.assertEqual({"task.unknown-field"}, found)

    def declared(self, **overrides: str) -> str:
        """The valid task fields, with named ones replaced or dropped.

        Built from a mapping rather than by editing the sample's text, so
        removing a list field takes its items with it and the result is still
        readable YAML — otherwise a test meaning to drop `recognize` would leave
        its bullets behind and report a parse failure instead of the check.
        """
        fields = {
            "title": "title: Review a change",
            "recognize": "recognize:\n- the requester asks for risks in a change",
            "goal": "goal: Every actionable risk is named.",
        }
        fields.update(overrides)
        return "\n".join(value for value in fields.values() if value)

    def test_each_required_task_field_reports_its_own_missing_code(self):
        for field, code in (
            ("title", "task.missing-title"),
            ("recognize", "task.missing-recognize"),
            ("goal", "task.missing-goal"),
        ):
            with self.subTest(field=field):
                _, found = self.task(self.declared(**{field: ""}))
                self.assertIn(code, found)

    def test_each_unreadable_task_field_reports_its_own_invalid_code(self):
        for field, value, code in (
            ("title", "title: ''", "task.invalid-title"),
            ("goal", "goal: []", "task.invalid-goal"),
            ("recognize", "recognize: []", "task.invalid-recognize"),
            ("knowledge", "knowledge: [Change-Surface]", "task.invalid-knowledge"),
            ("principles", "principles: [Evidence]", "task.invalid-principles"),
            ("guides", "guides: []", "task.invalid-guides"),
        ):
            with self.subTest(code=code):
                _, found = self.task(self.declared(**{field: value}))
                self.assertIn(code, found)

    def test_a_task_principle_is_a_bare_id(self):
        task, found = self.task(
            TASK + "principles:\n- evidence\n- delegation\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual(("evidence", "delegation"), task.principles)

    def test_a_knowledge_reference_is_a_bare_id(self):
        task, found = self.task(TASK + "knowledge:\n- change-surface\n")
        self.assertEqual(set(), found)
        self.assertEqual("change-surface", task.knowledge[0])

    def test_a_typed_knowledge_reference_is_reported(self):
        _, found = self.task(TASK + "knowledge:\n- concept:change-surface\n")
        self.assertIn("task.invalid-knowledge", found)

    def test_a_task_names_a_guide_by_its_bare_id(self):
        task, found = self.task(TASK + "guides:\n- house-style\n")
        self.assertEqual(set(), found)
        self.assertEqual(("house-style",), task.guides)

    def test_a_task_guide_must_be_a_bare_id(self):
        _, found = self.task(TASK + "guides:\n- guide: house-style\n")
        self.assertIn("task.invalid-guides", found)


class KnowledgeReaderTests(ReaderHarness):
    def test_a_unit_is_read_with_its_declared_kind_and_bare_key(self):
        unit, found = self.knowledge(
            "kind: concept\ntitle: What a change can reach\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual("change-surface", unit.key)
        self.assertEqual("concept", unit.kind)

    def test_a_unit_declaring_an_id_is_refused(self):
        _, found = self.knowledge("kind: concept\ntitle: Surface\nid: surface\n")
        self.assertIn("knowledge.unexpected-id", found)

    def test_a_unit_with_no_kind_is_reported(self):
        _, found = self.knowledge("title: Surface\n")
        self.assertIn("knowledge.missing-kind", found)

    def test_a_unit_with_no_title_is_reported(self):
        _, found = self.knowledge("kind: concept\n")
        self.assertIn("knowledge.missing-title", found)

    def test_each_unreadable_unit_field_reports_its_own_code(self):
        for fields, code in (
            ("kind: idea\ntitle: Surface", "knowledge.invalid-kind"),
            ("kind: concept\ntitle: ''", "knowledge.invalid-title"),
            ("kind: concept\ntitle: Surface\nrequires: [Surface]", "knowledge.invalid-requires"),
        ):
            with self.subTest(code=code):
                _, found = self.knowledge(fields)
                self.assertIn(code, found)

    def test_a_unit_keeps_prefixed_custom_metadata_without_using_it(self):
        unit, found = self.knowledge(
            "kind: concept\ntitle: Surface\nx-owner: documentation\nx-external: {id: 42}\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual(
            {"x-owner": "documentation", "x-external": {"id": 42}}, unit.metadata
        )

    def test_an_unprefixed_unit_field_warns_without_preventing_reading(self):
        unit, found = self.knowledge("kind: concept\ntitle: Surface\nowner: documentation\n")
        self.assertIsNotNone(unit)
        self.assertEqual({"knowledge.unknown-field"}, found)

    def test_a_summary_is_an_unknown_unit_field(self):
        _, found = self.knowledge("kind: concept\ntitle: Surface\nsummary: Brief.\n")
        self.assertEqual({"knowledge.unknown-field"}, found)

    def test_a_unit_with_no_body_is_refused(self):
        """The body is the knowledge; without it the page gets a bare heading."""
        _, found = self.knowledge("kind: concept\ntitle: Surface\n", body="")
        self.assertIn("knowledge.empty", found)


class PrincipleReaderTests(ReaderHarness):
    def test_a_principle_keeps_prefixed_custom_metadata_without_using_it(self):
        principle, found = self.principle(
            "title: Evidence\nx-source: handbook\nx-labels: [claims, reports]\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual(
            {"x-source": "handbook", "x-labels": ["claims", "reports"]},
            principle.metadata,
        )

    def test_an_unprefixed_principle_field_warns_without_preventing_reading(self):
        principle, found = self.principle("title: Evidence\nsource: handbook\n")
        self.assertIsNotNone(principle)
        self.assertEqual({"principle.unknown-field"}, found)


class FacetReaderTests(ReaderHarness):
    def test_a_facet_is_read_with_its_optional_fields(self):
        facet, found = self.facet(
            "title: Python\ncategory: Language\ndescription: Python guidance.\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual(("python", "Python", "Language"), (facet.id, facet.title, facet.category))
        self.assertEqual("Python guidance.", facet.description)

    def test_a_facet_needs_only_a_title(self):
        facet, found = self.facet("title: Python\n")
        self.assertEqual(set(), found)
        self.assertEqual("", facet.description)
        self.assertEqual((), facet.guides)

    def test_a_facet_names_guides_by_bare_id_in_the_order_it_wrote_them(self):
        facet, found = self.facet("title: Python\nguides:\n- toolchain\n- checklist\n")
        self.assertEqual(set(), found)
        self.assertEqual(("toolchain", "checklist"), facet.guides)

    def test_a_facet_keeps_prefixed_custom_metadata_without_using_it(self):
        facet, found = self.facet(
            "title: Python\nx-owner: platform\nx-labels: [python, tooling]\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual(
            {"x-owner": "platform", "x-labels": ["python", "tooling"]},
            facet.metadata,
        )

    def test_a_facet_declaring_an_id_is_refused(self):
        _, found = self.facet("title: Python\nid: py\n")
        self.assertIn("facet.unexpected-id", found)

    def test_a_facet_with_no_title_is_reported(self):
        _, found = self.facet("category: Language\n")
        self.assertIn("facet.missing-title", found)

    def test_each_unreadable_facet_field_reports_its_own_code(self):
        for fields, code in (
            ("title: ''", "facet.invalid-title"),
            ("title: Python\ncategory: ''", "facet.invalid-category"),
            ("title: Python\ndescription: ''", "facet.invalid-description"),
            ("title: Python\nguides: toolchain", "facet.invalid-guides"),
            ("title: Python\nguides:\n- Toolchain", "facet.invalid-guides"),
            (
                "title: Python\nguides:\n- toolchain\n- toolchain",
                "facet.invalid-guides",
            ),
        ):
            with self.subTest(code=code):
                _, found = self.facet(fields)
                self.assertIn(code, found)

    def test_a_facet_field_the_schema_does_not_define_is_reported(self):
        _, found = self.facet("title: Python\napplies: {terms: [py]}\n")
        self.assertIn("facet.unknown-field", found)

    def test_a_facet_with_no_body_is_refused(self):
        _, found = self.facet("title: Python\n", body="")
        self.assertIn("facet.empty", found)


class SourceIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_a_filename_that_cannot_be_an_id_is_reported(self):
        source = task_path(self.root, "alpha", "review")
        source.rename(source.with_name("Review_Change.md"))
        self.assertIn("source.invalid-name", codes(alpha(self.root)))

    def test_two_files_of_one_kind_sharing_a_stem_are_reported(self):
        source = alpha(self.root) / "knowledge" / "change-surface.md"
        write_text(
            alpha(self.root) / "knowledge" / "nested" / "change-surface.md",
            source.read_text(encoding="utf-8"),
        )
        with_nested = ["knowledge/*.md", "knowledge/nested/*.md"]
        from tests.support import set_content_patterns

        set_content_patterns(self.root, "alpha", knowledge=with_nested)
        self.assertIn("source.duplicate-id", codes(alpha(self.root)))

    def test_a_selected_file_that_is_not_markdown_is_reported(self):
        write_text(alpha(self.root) / "knowledge" / "notes.yaml", "title: x\n")
        from tests.support import set_content_patterns

        set_content_patterns(self.root, "alpha", knowledge=["knowledge/*"])
        self.assertIn("source.unsupported", codes(alpha(self.root)))

    def test_a_source_with_no_frontmatter_is_refused(self):
        write_text(
            alpha(self.root) / "knowledge" / "change-surface.md",
            "# What a change can reach\n\nThe surface is what a consumer sees.\n",
        )
        self.assertIn("source.missing-frontmatter", codes(alpha(self.root)))

    def test_a_frontmatter_block_that_never_closes_is_refused(self):
        write_text(
            alpha(self.root) / "knowledge" / "change-surface.md",
            "---\ntitle: What a change can reach\n\nBody with no closing fence.\n",
        )
        self.assertIn("source.missing-frontmatter", codes(alpha(self.root)))

    def test_a_source_that_cannot_be_decoded_is_reported(self):
        path = alpha(self.root) / "knowledge" / "change-surface.md"
        path.write_bytes(b"---\ntitle: \xff\xfe bad\n---\n\nBody.\n")
        self.assertIn("source.unreadable", codes(alpha(self.root)))

    def test_an_invalid_guide_frontmatter_is_refused(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\nexternal: [missing\n---\n\n# Checklist\n",
        )
        self.assertIn("source.invalid-yaml", codes(alpha(self.root)))

    def test_a_guide_needs_a_title(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\n---\n\nGuide body.\n",
        )
        self.assertIn("guide.missing-title", codes(alpha(self.root)))

    def test_a_guide_title_must_be_a_non_empty_string(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\ntitle: ''\n---\n\nGuide body.\n",
        )
        self.assertIn("guide.invalid-title", codes(alpha(self.root)))

    def test_a_guide_activation_must_be_a_non_empty_string(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\ntitle: Checklist\nactivation: ''\n---\n\nGuide body.\n",
        )
        self.assertIn("guide.invalid-activation", codes(alpha(self.root)))

    def test_a_guide_cannot_declare_its_id(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\nid: checklist\ntitle: Checklist\n---\n\nGuide body.\n",
        )
        self.assertIn("guide.unexpected-id", codes(alpha(self.root)))

    def test_a_guide_needs_conditionally_relevant_knowledge(self):
        write_text(
            alpha(self.root) / "guides" / "checklist.md",
            "---\ntitle: Checklist\n---\n",
        )
        self.assertIn("guide.empty", codes(alpha(self.root)))

    def test_a_guide_file_stem_is_its_unique_id(self):
        write_text(
            alpha(self.root) / "guides" / "nested" / "checklist.md",
            "---\ntitle: Another checklist\n---\n\nGuide body.\n",
        )
        with edit_yaml(alpha(self.root) / "skill.yaml") as manifest:
            manifest["content"]["guides"].append("guides/nested/*.md")
        self.assertIn("source.duplicate-id", codes(alpha(self.root)))

    def test_reading_a_missing_file_raises_the_unreadable_check(self):
        with self.assertRaises(SourceError) as raised:
            read_markdown(self.root / "nowhere.md")
        self.assertEqual("source.unreadable", raised.exception.code)

    def test_a_body_is_kept_exactly_as_written(self):
        """The compiler moves an author's words; it never edits them."""
        body = "Line one.\n\n    indented\n\n- bullet\n"
        path = self.root / "knowledge" / "kept.md"
        write_source(path, "title: Kept", body)
        self.assertEqual(body.strip("\n"), read_markdown(path).body)

    def test_frontmatter_fields_round_trip_without_touching_the_body(self):
        path = task_path(self.root, "alpha", "review")
        before = read_markdown(path).body
        with edit_frontmatter(path) as fields:
            fields["title"] = "Reviewed"
        after = read_markdown(path)
        self.assertEqual(before, after.body)
        self.assertEqual("Reviewed", after.fields["title"])


if __name__ == "__main__":
    unittest.main()
