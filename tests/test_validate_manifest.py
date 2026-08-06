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

from tests.support import FIXTURES, copy_skills


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

            errors = validate(root / "gamma")

            self.assertTrue(
                any(
                    "primary workflow not found: gamma.missing" in error
                    for error in errors
                )
            )

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

                    errors = validate(source.parent)

                    self.assertTrue(
                        any(
                            f"{field} must be a non-empty string" in error
                            for error in errors
                        )
                    )
                    with self.assertRaisesRegex(
                        DegardisError,
                        f"{field} must be a non-empty string",
                    ):
                        build_skills(source.parent, root / "output")

    def test_manifest_fields_enforce_documented_types(self):
        cases = (
            (
                "format_version",
                lambda data: data.__setitem__("format_version", "1"),
                "format_version must be an integer",
            ),
            (
                "version",
                lambda data: data.__setitem__("version", 1),
                "version must be a non-empty string",
            ),
            (
                "description",
                lambda data: data.__setitem__("description", ["invalid"]),
                "description must be a non-empty string",
            ),
            (
                "primary_workflow",
                lambda data: data.__setitem__("primary_workflow", 7),
                "primary_workflow must be a non-empty string",
            ),
            (
                "title",
                lambda data: data.__setitem__("title", []),
                "title must be a non-empty string",
            ),
            (
                "interface",
                lambda data: data.__setitem__("interface", []),
                "interface must be a mapping",
            ),
            (
                "display_name",
                lambda data: data["interface"].__setitem__("display_name", 123),
                "interface.display_name must be a non-empty string",
            ),
            (
                "brand_color",
                lambda data: data["interface"].__setitem__("brand_color", {}),
                "interface.brand_color must be a non-empty string",
            ),
        )
        for field, mutate, message in cases:
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

                    errors = validate(root / "gamma")

                    self.assertTrue(any(message in error for error in errors))
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

            errors = validate(manifest.parent)

            self.assertTrue(
                any(
                    "unsupported format_version 2; supported versions: 1" in error
                    for error in errors
                )
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
        self.assertTrue(
            any(
                "entry_kinds is derived from the skill content" in warning
                for warning in result["warnings"]
            )
        )
