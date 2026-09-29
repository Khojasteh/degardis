"""The manifest, its interface metadata, and the content it selects."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from degardis.content import CONTENT_KEYS
from degardis.registry import (
    DESCRIPTION_LIMIT,
    NAME_LIMIT,
    REQUIRED_MANIFEST_FIELDS,
    load_skill_path,
)

from tests.support import (
    codes,
    copy_skills,
    edit_yaml,
    inspect_one,
    set_content_patterns,
    set_interface_fields,
    write_source,
    write_text,
)


class FixtureCase(unittest.TestCase):
    """A fresh copy of the alpha fixture per test, and per row of a table."""

    def setUp(self) -> None:
        self.skill = self.fresh()
        self.root = self.skill.parent

    def fresh(self) -> Path:
        """A new copy of the alpha fixture, so one table row cannot leak into the next."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return copy_skills(Path(directory.name)) / "alpha"


class ManifestFieldTests(FixtureCase):
    def manifest(self, skill: Path | None = None):
        return edit_yaml((skill or self.skill) / "skill.yaml")

    def test_the_fixture_reports_nothing(self):
        self.assertEqual(set(), codes(self.skill))
        self.assertEqual(set(), codes(self.skill, "warning"))

    def test_a_required_field_left_out_names_the_key_it_is_missing(self):
        """One code per key, so an author who knows the key knows the code.

        The pairs are written out rather than read from the reader's own table,
        so the case states what the format requires instead of what the module
        currently spells.
        """
        for field, code in (
            ("format_version", "manifest.missing-format_version"),
            ("version", "manifest.missing-version"),
            ("description", "manifest.missing-description"),
            ("tasks", "manifest.missing-tasks"),
            ("content", "manifest.missing-content"),
            ("interface", "manifest.missing-interface"),
        ):
            with self.subTest(field=field):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data.pop(field)
                self.assertIn(code, codes(skill))

    def test_every_field_the_format_requires_has_a_case_above(self):
        """`name` is the exception: discovery needs it before any check runs."""
        self.assertEqual(
            {
                "name",
                "format_version",
                "version",
                "description",
                "tasks",
                "content",
                "interface",
            },
            {field for field, _ in REQUIRED_MANIFEST_FIELDS},
        )

    def test_a_field_the_manifest_schema_does_not_define_is_reported(self):
        with self.manifest() as data:
            data["owner"] = "documentation"
        self.assertIn("manifest.unknown-field", codes(self.skill))

    def test_tasks_are_the_routing_order_as_bare_ids(self):
        self.assertEqual(
            ("review", "repair", "document"),
            load_skill_path(self.skill).tasks,
        )
        for value in ([], ["Review"], ["review", "review"], [{"id": "review"}]):
            with self.subTest(value=value):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data["tasks"] = value
                self.assertIn("manifest.invalid-tasks", codes(skill))

    def test_a_refused_task_list_reports_one_finding_rather_than_one_per_task(self):
        """A list the manifest check refuses names nothing, so comparing every
        task file against it would call each one unrouted by a list that may
        name it."""
        for value, code in (
            (None, "manifest.missing-tasks"),
            (["Review", "repair", "document"], "manifest.invalid-tasks"),
        ):
            with self.subTest(value=value):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    if value is None:
                        data.pop("tasks")
                    else:
                        data["tasks"] = value
                found = codes(skill)
                self.assertIn(code, found)
                self.assertNotIn("manifest.unrouted-task", found)

    def test_a_refused_principle_list_calls_no_principle_unused(self):
        with self.manifest() as data:
            data["principles"] = ["Evidence", "expenditure"]
        self.assertIn("manifest.invalid-principles", codes(self.skill))
        self.assertNotIn("principle.unused", codes(self.skill, "warning"))

    def test_a_routed_name_with_no_task_file_is_reported(self):
        """A route to a page that is not there sends the agent nowhere."""
        with self.manifest() as data:
            data["tasks"] = ["review", "repair", "document", "audit"]
        result = inspect_one(self.skill)
        message = next(
            record.message
            for record in result["diagnostics"]
            if record.code == "manifest.unknown-task"
        )
        self.assertIn("tasks names 'audit'", message)
        self.assertNotIn("tasks/audit.md", message)

    def test_a_task_file_no_route_names_is_reported(self):
        """The other direction: a page in the bundle no request can reach."""
        with self.manifest() as data:
            data["tasks"] = ["review", "repair"]
        self.assertIn("manifest.unrouted-task", codes(self.skill))

    def test_a_manifest_keeps_prefixed_custom_metadata_without_using_it(self):
        with self.manifest() as data:
            data["x-owner"] = "platform"
            data["x-tags"] = ["summary", "writing"]
        self.assertEqual(set(), codes(self.skill))
        self.assertEqual(
            {"x-owner": "platform", "x-tags": ["summary", "writing"]},
            {
                name: value
                for name, value in load_skill_path(self.skill).manifest.items()
                if name.startswith("x-")
            },
        )

    def test_principles_are_a_skill_level_list_of_bare_ids(self):
        self.assertEqual(
            ("evidence", "expenditure", "reporting", "delegation", "provenance"),
            load_skill_path(self.skill).principles,
        )
        for value in ([], ["Evidence"], ["evidence", "evidence"], [{"id": "evidence"}]):
            with self.subTest(value=value):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data["principles"] = value
                self.assertIn("manifest.invalid-principles", codes(skill))

    def test_each_string_and_mapping_field_names_its_own_invalid_code(self):
        for field, value, code in (
            ("version", 3, "manifest.invalid-version"),
            ("version", "", "manifest.invalid-version"),
            ("license", "", "manifest.invalid-license"),
            ("copyright", "", "manifest.invalid-copyright"),
            ("description", "", "manifest.invalid-description"),
            ("stance", "", "manifest.invalid-stance"),
            ("content", [], "manifest.invalid-content"),
            ("interface", [], "manifest.invalid-interface"),
        ):
            with self.subTest(field=field, value=value):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data[field] = value
                self.assertIn(code, codes(skill))

    def test_a_manifest_name_that_is_not_an_identifier_is_reported(self):
        renamed = self.root / "Alpha"
        self.skill.rename(renamed)
        with self.manifest(renamed) as data:
            data["name"] = "Alpha"
        self.assertIn("manifest.invalid-name", codes(renamed))

    def test_a_description_past_the_limit_is_refused(self):
        with self.manifest() as data:
            data["description"] = "w" * (DESCRIPTION_LIMIT + 1)
        self.assertIn("manifest.description-length", codes(self.skill))

    def test_a_description_at_the_limit_is_accepted(self):
        with self.manifest() as data:
            data["description"] = "w" * DESCRIPTION_LIMIT
        self.assertEqual(set(), codes(self.skill))
        self.assertEqual(set(), codes(self.skill, "warning"))

    def test_a_description_containing_an_xml_tag_is_refused(self):
        for tag in (
            "<example>",
            "</example>",
            "<br/>",
            '<a href="x">',
            "<!-- note -->",
            "<?xml version='1.0'?>",
        ):
            with self.subTest(tag=tag):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data["description"] = f"Summarize {tag} material."
                self.assertIn("manifest.invalid-description", codes(skill))

    def test_angle_brackets_that_form_no_tag_are_accepted(self):
        for text in ("Use when x < y and y > z.", "Map a -> b.", "Accept <3 or 5>."):
            with self.subTest(text=text):
                skill = self.fresh()
                with self.manifest(skill) as data:
                    data["description"] = text
                self.assertEqual(set(), codes(skill))

    def test_a_name_past_the_limit_is_refused_and_one_at_it_is_accepted(self):
        for length, refused in ((NAME_LIMIT, False), (NAME_LIMIT + 1, True)):
            with self.subTest(length=length):
                name = "a" * length
                skill = self.fresh()
                renamed = skill.parent / name
                skill.rename(renamed)
                with self.manifest(renamed) as data:
                    data["name"] = name
                self.assertEqual(refused, "manifest.name-length" in codes(renamed))
                self.assertNotIn("manifest.invalid-name", codes(renamed))

    def test_a_name_containing_a_brand_warns(self):
        for name in ("claude-helper", "my-openai-notes", "copilotkit"):
            with self.subTest(name=name):
                skill = self.fresh()
                renamed = skill.parent / name
                skill.rename(renamed)
                with self.manifest(renamed) as data:
                    data["name"] = name
                self.assertIn("manifest.name-brand", codes(renamed, "warning"))
                self.assertEqual(set(), codes(renamed))

    def test_the_briefing_is_what_the_generated_root_states(self):
        """Two texts to two readers: one chooses the skill, one runs it."""
        skill = load_skill_path(self.skill)
        self.assertTrue(skill.stance.startswith("Exercise the compiler"))
        self.assertNotEqual(skill.description, skill.stance)

    def test_a_manifest_with_no_briefing_has_none(self):
        """The description is not a fallback: it is written for another reader."""
        with self.manifest() as data:
            data.pop("stance")
        skill = load_skill_path(self.skill)
        self.assertEqual("", skill.stance)


class InterfaceTests(FixtureCase):
    def test_each_required_interface_field_has_its_own_code(self):
        for field, code in (
            ("display_name", "interface.missing-display_name"),
            ("short_description", "interface.missing-short_description"),
            ("default_prompt", "interface.missing-default_prompt"),
        ):
            with self.subTest(field=field):
                skill = self.fresh()
                with edit_yaml(skill / "skill.yaml") as data:
                    data["interface"].pop(field)
                self.assertIn(code, codes(skill))

    def test_an_unknown_interface_field_is_reported(self):
        set_interface_fields(self.root, "alpha", color="purple")
        self.assertIn("interface.unknown-field", codes(self.skill))

    def test_each_invalid_interface_field_names_itself(self):
        for field, code in (
            ("display_name", "interface.invalid-display_name"),
            ("short_description", "interface.invalid-short_description"),
            ("default_prompt", "interface.invalid-default_prompt"),
        ):
            with self.subTest(field=field):
                skill = self.fresh()
                set_interface_fields(skill.parent, "alpha", **{field: ""})
                self.assertIn(code, codes(skill))

    def test_an_interface_field_past_its_limit_is_refused_and_one_at_it_is_accepted(self):
        """The limits are written out, so the case states what the format
        requires instead of what the module currently spells."""
        for field, limit, code in (
            ("display_name", 64, "interface.display_name-length"),
            ("short_description", 64, "interface.short_description-length"),
            ("default_prompt", 1024, "interface.default_prompt-length"),
        ):
            for length, refused in ((limit, False), (limit + 1, True)):
                with self.subTest(field=field, length=length):
                    value = ("Use alpha " + "w" * length)[:length]
                    skill = self.fresh()
                    set_interface_fields(skill.parent, "alpha", **{field: value})
                    self.assertEqual(refused, code in codes(skill))

    def test_a_prompt_must_name_this_skill_exactly(self):
        for prompt in ("Do the task.", "Use {name}.", "Use alphabet."):
            with self.subTest(prompt=prompt):
                skill = self.fresh()
                set_interface_fields(skill.parent, "alpha", default_prompt=prompt)
                self.assertIn(
                    "interface.default_prompt-token", codes(skill, "warning")
                )

    def test_a_prompt_names_the_skill_without_host_syntax(self):
        set_interface_fields(self.root, "alpha", default_prompt="Use alpha.")
        self.assertNotIn(
            "interface.default_prompt-token", codes(self.skill, "warning")
        )

    def test_a_prompt_spelling_host_syntax_is_reported(self):
        for prompt in ("Use $alpha.", "Use /alpha.", "Use @alpha.", "Use #alpha."):
            with self.subTest(prompt=prompt):
                skill = self.fresh()
                set_interface_fields(skill.parent, "alpha", default_prompt=prompt)
                self.assertIn(
                    "interface.default_prompt-literal-token", codes(skill)
                )


class ContentSelectionTests(FixtureCase):
    def test_content_keys_are_the_ones_a_report_counts(self):
        """The report's count line and the selection share one key list, so a
        new content key cannot appear in one and be missing from the other."""
        self.assertEqual(set(CONTENT_KEYS), set(inspect_one(self.skill)["counts"]))

    def test_a_missing_content_mapping_is_reported_once(self):
        """One mistake, one code.

        The manifest's required-field check already names the absent key, so
        the content reader stays quiet rather than giving the same mistake a
        second code and sending the author looking for a second repair.
        """
        with edit_yaml(self.skill / "skill.yaml") as data:
            data.pop("content")
        found = codes(self.skill)
        self.assertIn("manifest.missing-content", found)
        self.assertNotIn("content.missing-tasks", found)

    def test_a_skill_with_no_tasks_selected_is_reported(self):
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"].pop("tasks")
        self.assertIn("content.missing-tasks", codes(self.skill))

    def test_an_unknown_content_key_is_reported(self):
        set_content_patterns(self.root, "alpha", entries=["entries/*.md"])
        self.assertIn("content.unknown-field", codes(self.skill))

    def test_each_content_field_names_its_own_invalid_code(self):
        """Both shapes a pattern list can take wrongly: not a list at all, and a
        list holding a pattern that selects nothing because it says nothing."""
        expected = {
            "tasks": "content.invalid-tasks",
            "principles": "content.invalid-principles",
            "knowledge": "content.invalid-knowledge",
            "facets": "content.invalid-facets",
            "guides": "content.invalid-guides",
            "scripts": "content.invalid-scripts",
            "assets": "content.invalid-assets",
        }
        self.assertEqual(set(CONTENT_KEYS), set(expected))
        for field, code in expected.items():
            for value in ([""], f"{field}/*.md"):
                with self.subTest(field=field, value=value):
                    skill = self.fresh()
                    with edit_yaml(skill / "skill.yaml") as data:
                        data["content"][field] = value
                    self.assertIn(code, codes(skill))

    def test_a_pattern_matching_nothing_is_reported(self):
        set_content_patterns(self.root, "alpha", assets=["assets/*.txt"])
        self.assertIn("content.unmatched-pattern", codes(self.skill))

    def test_a_pattern_matching_only_in_another_case_is_reported(self):
        """Selection is a property of the source, not of the host's filesystem,
        so a wrongly cased pattern fails everywhere rather than only on Linux."""
        set_content_patterns(self.root, "alpha", assets=["Assets/*.md"])
        self.assertIn("content.unmatched-pattern", codes(self.skill))

    def test_a_key_whose_exclusions_empty_it_is_reported(self):
        set_content_patterns(
            self.root, "alpha", assets=["assets/*.md", "!assets/**/*"]
        )
        self.assertIn("content.empty-selection", codes(self.skill))

    def test_an_exclusion_removes_what_an_earlier_pattern_selected(self):
        write_text(self.skill / "assets" / "draft.md", "# Draft\n")
        set_content_patterns(
            self.root, "alpha", assets=["assets/*.md", "!assets/draft.md"]
        )
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/template.md", selected)
        self.assertNotIn("assets/draft.md", selected)

    def test_a_pattern_reaching_outside_the_skill_is_reported(self):
        set_content_patterns(self.root, "alpha", assets=["../beta/**/*.yaml"])
        self.assertIn("content.outside-skill", codes(self.skill))

    def test_a_wildcard_passes_over_a_dot_directory_and_a_path_can_name_it(self):
        write_text(self.skill / "assets" / ".cache" / "note.md", "# Cached\n")
        set_content_patterns(self.root, "alpha", assets=["assets/**/*.md"])
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/template.md", selected)
        self.assertNotIn("assets/.cache/note.md", selected)
        set_content_patterns(
            self.root, "alpha", assets=["assets/*.md", "assets/.cache/note.md"]
        )
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/.cache/note.md", selected)

    @unittest.skipUnless(os.name == "nt", "the hidden attribute is set through Windows")
    def test_a_wildcard_passes_over_a_file_the_host_hides_and_a_path_can_name_it(self):
        """A file its author cannot see is one they cannot write an exclusion
        for, so a wildcard leaves it out, while a pattern that spells out the
        path was written about that file and selects it."""
        import ctypes

        write_text(self.skill / "assets" / "visible.md", "# Visible\n")
        hidden = self.skill / "assets" / "template.md"
        kernel = ctypes.windll.kernel32
        self.assertTrue(kernel.SetFileAttributesW(str(hidden), 0x2))
        self.addCleanup(kernel.SetFileAttributesW, str(hidden), 0x80)
        set_content_patterns(self.root, "alpha", assets=["assets/*.md"])
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/visible.md", selected)
        self.assertNotIn("assets/template.md", selected)
        set_content_patterns(
            self.root, "alpha", assets=["assets/visible.md", "assets/template.md"]
        )
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/template.md", selected)

    def test_bytecode_beside_a_script_is_never_selected(self):
        write_text(self.skill / "scripts" / "__pycache__" / "greet.pyc", "x")
        set_content_patterns(self.root, "alpha", scripts=["scripts/**/*"])
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("scripts/greet.py", selected)
        self.assertEqual([], [path for path in selected if "__pycache__" in path])

    def test_a_selection_carries_the_ids_the_files_name(self):
        write_source(
            self.skill / "knowledge" / "extra-limit.md",
            "kind: fact\ntitle: Extra",
        )
        rows = {
            row["path"]: row["id"] for row in inspect_one(self.skill)["sources"]
        }
        self.assertEqual("extra-limit", rows["knowledge/extra-limit.md"])
        self.assertEqual("", rows["scripts/greet.py"])


if __name__ == "__main__":
    unittest.main()
