"""The manifest, its interface metadata, and the content it selects."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.content import CONTENT_KEYS
from degardis.registry import REQUIRED_MANIFEST_FIELDS

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


class ManifestFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def manifest(self):
        return edit_yaml(self.skill / "skill.yaml")

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
            with self.subTest(field=field), self.manifest() as data:
                data.pop(field)
            self.assertIn(code, codes(self.skill))
            self.setUp()

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

    def test_a_manifest_declares_no_facet(self):
        """Which facets apply is the running agent's to decide, so a list here
        would order something no author orders."""
        with self.manifest() as data:
            data["facets"] = ["python"]
        self.assertIn("manifest.unknown-field", codes(self.skill))

    def test_tasks_are_the_routing_order_as_bare_ids(self):
        from degardis.registry import load_skill_path

        self.assertEqual(
            ("review", "repair", "document"),
            load_skill_path(self.skill).tasks,
        )
        for value in ([], ["Review"], ["review", "review"], [{"id": "review"}]):
            with self.subTest(value=value), self.manifest() as data:
                data["tasks"] = value
            self.assertIn("manifest.invalid-tasks", codes(self.skill))
            self.setUp()

    def test_a_routed_name_with_no_task_file_is_reported(self):
        """A route to a page that is not there sends the agent nowhere."""
        with self.manifest() as data:
            data["tasks"] = ["review", "repair", "document", "audit"]
        self.assertIn("manifest.unknown-task", codes(self.skill))

    def test_a_task_file_no_route_names_is_reported(self):
        """The other direction: a page in the bundle no request can reach."""
        with self.manifest() as data:
            data["tasks"] = ["review", "repair"]
        self.assertIn("manifest.unrouted-task", codes(self.skill))

    def test_a_manifest_keeps_prefixed_custom_metadata_without_using_it(self):
        from degardis.registry import load_skill_path

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
        from degardis.registry import load_skill_path

        self.assertEqual(
            ("evidence", "expenditure", "reporting", "delegation", "provenance"),
            load_skill_path(self.skill).principles,
        )
        for value in ([], ["Evidence"], ["evidence", "evidence"], [{"id": "evidence"}]):
            with self.subTest(value=value), self.manifest() as data:
                data["principles"] = value
            self.assertIn("manifest.invalid-principles", codes(self.skill))
            self.setUp()

    def test_a_field_of_the_wrong_shape_is_reported(self):
        with self.manifest() as data:
            data["version"] = 3
        self.assertIn("manifest.invalid-version", codes(self.skill))

    def test_each_string_and_mapping_field_names_its_own_invalid_code(self):
        cases = (
            ("version", "", "manifest.invalid-version"),
            ("license", "", "manifest.invalid-license"),
            ("copyright", "", "manifest.invalid-copyright"),
            ("description", "", "manifest.invalid-description"),
            ("purpose", "", "manifest.invalid-purpose"),
            ("content", [], "manifest.invalid-content"),
            ("interface", [], "manifest.invalid-interface"),
        )
        for field, value, code in cases:
            with self.subTest(field=field), self.manifest() as data:
                data[field] = value
            self.assertIn(code, codes(self.skill))
            self.setUp()

    def test_a_manifest_name_that_is_not_an_identifier_is_reported(self):
        renamed = self.root / "Alpha"
        self.skill.rename(renamed)
        self.skill = renamed
        with self.manifest() as data:
            data["name"] = "Alpha"
        self.assertIn("manifest.invalid-name", codes(self.skill))

    def test_a_long_description_warns(self):
        with self.manifest() as data:
            data["description"] = "word " * 300
        self.assertIn("manifest.description-length", codes(self.skill, "warning"))

    def test_the_purpose_is_what_the_generated_root_states(self):
        """Two sentences to two readers: one chooses the skill, one runs it."""
        from degardis.registry import load_skill_path

        skill = load_skill_path(self.skill)
        self.assertTrue(skill.purpose.startswith("Exercise the compiler"))

    def test_a_manifest_with_no_purpose_has_its_description_stand_in(self):
        from degardis.registry import load_skill_path

        with self.manifest() as data:
            data.pop("purpose")
        skill = load_skill_path(self.skill)
        self.assertEqual(skill.description, skill.purpose)


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def test_each_required_interface_field_has_its_own_code(self):
        expected = {
            "display_name": "interface.missing-display_name",
            "short_description": "interface.missing-short_description",
            "default_prompt": "interface.missing-default_prompt",
        }
        for field, code in expected.items():
            with self.subTest(field=field):
                with edit_yaml(self.skill / "skill.yaml") as data:
                    data["interface"].pop(field)
                self.assertIn(code, codes(self.skill))
                self.setUp()

    def test_an_unknown_interface_field_is_reported(self):
        set_interface_fields(self.root, "alpha", colour="purple")
        self.assertIn("interface.unknown-field", codes(self.skill))

    def test_each_invalid_interface_field_names_itself(self):
        for field, code in (
            ("display_name", "interface.invalid-display_name"),
            ("short_description", "interface.invalid-short_description"),
            ("default_prompt", "interface.invalid-default_prompt"),
        ):
            with self.subTest(field=field):
                set_interface_fields(self.root, "alpha", **{field: ""})
                self.assertIn(code, codes(self.skill))
                self.setUp()

    def test_a_brand_colour_must_be_a_hex_triplet(self):
        set_interface_fields(self.root, "alpha", brand_color="purple")
        self.assertIn("interface.invalid-brand_color", codes(self.skill))
        self.setUp()
        set_interface_fields(self.root, "alpha", brand_color="#5B4B8A")
        self.assertEqual(set(), codes(self.skill))

    def test_a_long_short_description_warns(self):
        set_interface_fields(
            self.root,
            "alpha",
            short_description="Turn any supplied material into a clear, "
            "audience-appropriate, well-structured summary",
        )
        self.assertIn(
            "interface.short_description-length", codes(self.skill, "warning")
        )

    def test_a_prompt_naming_no_skill_warns(self):
        set_interface_fields(self.root, "alpha", default_prompt="Do the task.")
        self.assertIn("interface.default_prompt-token", codes(self.skill, "warning"))

    def test_a_prompt_spelling_one_host_syntax_is_reported(self):
        for prompt in ("Use $alpha.", "Use /alpha.", "Use @alpha.", "Use #alpha."):
            with self.subTest(prompt=prompt):
                set_interface_fields(self.root, "alpha", default_prompt=prompt)
                self.assertIn(
                    "interface.default_prompt-literal-token", codes(self.skill)
                )
                self.setUp()


class ContentSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

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

    def test_a_pattern_list_of_the_wrong_shape_is_reported(self):
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["knowledge"] = "knowledge/*.md"
        self.assertIn("content.invalid-knowledge", codes(self.skill))

    def test_each_content_field_names_its_own_invalid_code(self):
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
            with self.subTest(field=field), edit_yaml(self.skill / "skill.yaml") as data:
                data["content"][field] = [""]
            self.assertIn(code, codes(self.skill))
            self.setUp()

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

    def test_bytecode_beside_a_script_is_never_selected(self):
        write_text(self.skill / "scripts" / "__pycache__" / "greet.pyc", "x")
        set_content_patterns(self.root, "alpha", scripts=["scripts/**/*"])
        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
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
