"""Validation of skill.yaml itself, and of validate's own plumbing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import inspect_skills, validate

from tests.support import (
    FIXTURES,
    copy_skills,
    diagnostic_codes,
    set_interface_fields,
)


class ManifestValidationTests(unittest.TestCase):
    def test_fixture_collection_validates(self):
        self.assertEqual([], validate(FIXTURES))

    def test_validate_skill_does_not_mask_internal_compiler_failures(self):
        with mock.patch(
            "degardis.validate._inspect_skill",
            side_effect=RuntimeError("injected compiler defect"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "injected compiler defect",
            ):
                validate(FIXTURES / "gamma")

    def test_validate_does_not_mask_internal_discovery_failures(self):
        with mock.patch(
            "degardis.validate.discover_skill_paths",
            side_effect=RuntimeError("injected discovery defect"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "injected discovery defect",
            ):
                validate(FIXTURES)

    def test_validate_collects_expected_discovery_failures(self):
        with mock.patch(
            "degardis.validate.discover_skill_paths",
            side_effect=OSError("injected filesystem failure"),
        ):
            self.assertEqual(
                ["injected filesystem failure"],
                validate(FIXTURES),
            )

    def test_missing_primary_workflow_remains_a_source_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["primary_workflow"] = "gamma.missing"
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            result = inspect_skills([root / "gamma"])[0]

            self.assertIn("workflow.missing-primary", diagnostic_codes(result, "error"))

    def test_legal_metadata_fields_must_be_non_empty_strings(self):
        for field, value in (
            ("license", ""),
            ("license", ["Apache-2.0"]),
            ("copyright", ""),
            ("copyright", {"holder": "Example Corp"}),
        ):
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha" / "skill.yaml"
                    data = yaml.safe_load(source.read_text(encoding="utf-8"))
                    data[field] = value
                    source.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    result = inspect_skills([source.parent])[0]

                    self.assertIn("manifest.invalid-type", diagnostic_codes(result, "error"))
                    with self.assertRaises(DegardisError):
                        build_skills(source.parent, root / "output")

    def test_manifest_fields_enforce_documented_types(self):
        cases = (
            (
                "format_version",
                lambda data: data.__setitem__("format_version", "1"),
                "manifest.invalid-type",
            ),
            (
                "version",
                lambda data: data.__setitem__("version", 1),
                "manifest.invalid-type",
            ),
            (
                "description",
                lambda data: data.__setitem__("description", ["invalid"]),
                "manifest.invalid-type",
            ),
            (
                "primary_workflow",
                lambda data: data.__setitem__("primary_workflow", 7),
                "manifest.invalid-type",
            ),
            (
                "title",
                lambda data: data.__setitem__("title", []),
                "manifest.invalid-type",
            ),
            (
                "interface",
                lambda data: data.__setitem__("interface", []),
                "manifest.invalid-type",
            ),
            (
                "display_name",
                lambda data: data["interface"].__setitem__("display_name", 123),
                "interface.invalid-type",
            ),
            (
                "brand_color",
                lambda data: data["interface"].__setitem__("brand_color", {}),
                "interface.invalid-type",
            ),
        )
        for field, mutate, expected_code in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    manifest = root / "gamma" / "skill.yaml"
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                    mutate(data)
                    manifest.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    result = inspect_skills([root / "gamma"])[0]

                    self.assertIn(expected_code, diagnostic_codes(result, "error"))
                    with self.assertRaises(DegardisError):
                        build_skills(root / "gamma", root / "output")
                    self.assertFalse((root / "output").exists())

    def test_unsupported_format_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["format_version"] = 2
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            result = inspect_skills([manifest.parent])[0]

            self.assertIn(
                "manifest.unsupported-format_version",
                diagnostic_codes(result, "error"),
            )

    def test_manifest_entry_kinds_are_ignored_and_derived_from_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["entry_kinds"] = "policy"
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            self.assertEqual([], validate(root / "gamma"))
            result = inspect_skills([root / "gamma"])[0]
            build_skills(root / "gamma", root / "output")

        self.assertNotIn("declared_entry_kinds", result)
        self.assertEqual({"rule": 1}, result["entry_kind_counts"])
        self.assertIn("manifest.derived-field", diagnostic_codes(result, "warning"))


class DefaultPromptTests(unittest.TestCase):
    """The suggested invocation, authored once for hosts that differ."""

    def test_a_prompt_naming_no_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_interface_fields(
                root,
                "alpha",
                default_prompt="Run the fixture workflow.",
            )

            result = inspect_skills([root / "alpha"])[0]

        self.assertIn(
            "interface.default_prompt-token", diagnostic_codes(result, "error")
        )

    def test_a_hardcoded_host_invocation_warns_without_failing(self):
        """Every host shape is recognized, not only the one a target renders."""
        for prefix in ("$", "/", "@", "#"):
            with self.subTest(prefix=prefix):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    set_interface_fields(
                        root,
                        "alpha",
                        default_prompt=f"Ask {prefix}alpha to run this.",
                    )

                    result = inspect_skills([root / "alpha"])[0]

                self.assertEqual([], result["errors"])
                self.assertIn(
                    "interface.default_prompt-literal-token",
                    diagnostic_codes(result, "warning"),
                )

    def test_another_skills_hardcoded_name_is_not_read_as_this_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_interface_fields(
                root,
                "alpha",
                default_prompt="Ask $beta to run this.",
            )

            result = inspect_skills([root / "alpha"])[0]

        self.assertIn(
            "interface.default_prompt-token", diagnostic_codes(result, "error")
        )
