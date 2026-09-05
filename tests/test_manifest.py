"""The manifest, its interface metadata, and the content it selects."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.content import CONTENT_KEYS
from degardis.registry import MANIFEST_BINDING_KEYS, REQUIRED_MANIFEST_FIELDS

from tests.support import (
    codes,
    copy_skills,
    edit_yaml,
    set_content_patterns,
    set_interface_fields,
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
            ("primary_workflow", "manifest.missing-primary_workflow"),
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
                "primary_workflow",
                "content",
                "interface",
            },
            {field for field, _ in REQUIRED_MANIFEST_FIELDS},
        )

    def test_an_unknown_field_is_reported(self):
        with self.manifest() as data:
            data["patterns"] = ["inspect-plan-act"]
        self.assertIn("manifest.unknown-field", codes(self.skill))

    def test_a_field_of_the_wrong_shape_is_reported(self):
        with self.manifest() as data:
            data["version"] = 3
        self.assertIn("manifest.invalid-type", codes(self.skill))

    def test_a_binding_list_must_be_a_list_of_stems(self):
        for key in MANIFEST_BINDING_KEYS:
            with self.subTest(key=key), self.manifest() as data:
                data[key] = "one-thing"
            self.assertIn("manifest.invalid-type", codes(self.skill))
            self.setUp()

    def test_a_binding_named_twice_is_reported(self):
        with self.manifest() as data:
            data["policies"] = ["run-authority", "run-authority"]
        self.assertIn("manifest.duplicate-binding", codes(self.skill))

    def test_a_name_that_is_not_an_identifier_is_reported(self):
        with self.manifest() as data:
            data["primary_workflow"] = "Run Me"
        self.assertIn("manifest.invalid-name", codes(self.skill))

    def test_a_long_description_warns(self):
        with self.manifest() as data:
            data["description"] = "word " * 300
        self.assertIn("manifest.description-length", codes(self.skill, "warning"))

    def test_a_primary_workflow_nothing_selects_is_reported(self):
        with self.manifest() as data:
            data["primary_workflow"] = "absent"
        self.assertIn("source.unknown-reference", codes(self.skill))

    def test_a_bound_construct_of_the_wrong_kind_is_reported(self):
        with self.manifest() as data:
            data["policies"] = ["scoped-change"]
        self.assertIn("source.cross-kind-reference", codes(self.skill))

    def test_guidance_bound_where_a_policy_belongs_is_reported(self):
        with self.manifest() as data:
            data["policies"] = ["run-context"]
        self.assertIn("guidance.invalid-application", codes(self.skill))

    def test_a_profile_bound_where_a_policy_belongs_is_reported(self):
        """A profile is selected at runtime, so nothing binding may name one."""
        with self.manifest() as data:
            data["policies"] = ["quick"]
        self.assertIn("profile.workflow-dependency", codes(self.skill))


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

    def test_a_brand_colour_must_be_a_hex_triplet(self):
        set_interface_fields(self.root, "alpha", brand_color="purple")
        self.assertIn("interface.invalid-type", codes(self.skill))
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
        from tests.support import inspect_one

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
        self.assertNotIn("content.missing-workflows", found)

    def test_a_skill_with_no_workflows_selected_is_reported(self):
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"].pop("workflows")
        self.assertIn("content.missing-workflows", codes(self.skill))

    def test_an_unknown_content_key_is_reported(self):
        set_content_patterns(self.root, "alpha", entries=["entries/*.yaml"])
        self.assertIn("content.unknown-field", codes(self.skill))

    def test_a_pattern_list_of_the_wrong_shape_is_reported(self):
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["rules"] = "rules/*.yaml"
        self.assertIn("content.invalid-type", codes(self.skill))

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
        from tests.support import inspect_one

        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertIn("assets/template.md", selected)
        self.assertNotIn("assets/draft.md", selected)

    def test_a_pattern_reaching_outside_the_skill_is_reported(self):
        set_content_patterns(self.root, "alpha", assets=["../beta/**/*.yaml"])
        self.assertIn("content.outside-skill", codes(self.skill))

    def test_bytecode_beside_a_script_is_never_selected(self):
        write_text(self.skill / "scripts" / "__pycache__" / "greet.pyc", "x")
        set_content_patterns(self.root, "alpha", scripts=["scripts/**/*"])
        from tests.support import inspect_one

        selected = {row["path"] for row in inspect_one(self.skill)["sources"]}
        self.assertEqual(
            [], [path for path in selected if "__pycache__" in path]
        )

    def test_a_construct_key_selecting_a_non_yaml_file_is_reported(self):
        write_text(self.skill / "rules" / "notes.txt", "not yaml")
        set_content_patterns(self.root, "alpha", rules=["rules/*"])
        self.assertIn("source.unsupported", codes(self.skill))

    def test_references_selecting_a_non_markdown_file_is_reported(self):
        write_text(self.skill / "references" / "notes.txt", "not markdown")
        set_content_patterns(self.root, "alpha", references=["references/**/*"])
        self.assertIn("source.unsupported", codes(self.skill))

    def test_two_files_of_one_kind_sharing_a_stem_are_reported(self):
        write_text(
            self.skill / "rules" / "extra" / "scoped-change.yaml",
            (self.skill / "rules" / "scoped-change.yaml").read_text(encoding="utf-8"),
        )
        set_content_patterns(self.root, "alpha", rules=["rules/**/*.yaml"])
        self.assertIn("source.duplicate-id", codes(self.skill))

    def test_a_filename_that_is_not_an_identifier_is_reported(self):
        source = self.skill / "rules" / "scoped-change.yaml"
        source.rename(self.skill / "rules" / "Scoped Change.yaml")
        self.assertIn("source.invalid-name", codes(self.skill))


if __name__ == "__main__":
    unittest.main()
