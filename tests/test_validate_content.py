"""Validation of the content selection and the output paths it implies."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import inspect_skills, validate

from tests.support import copy_skills


class ContentValidationTests(unittest.TestCase):
    def test_unsupported_content_field_is_reported_as_a_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["documents"] = ["documents/*.md"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([source.parent])[0]

        self.assertEqual([], result["errors"])
        self.assertTrue(
            any(
                "unrecognized content fields ignored: documents" in warning
                for warning in result["warnings"]
            )
        )

    def test_content_globs_must_stay_inside_skill_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            outside = root / "outside.yaml"
            outside.write_text(
                "id: alpha.outside\nrule: Outside content\n",
                encoding="utf-8",
            )
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["entries"] = ["../outside.yaml"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(source.parent)

            self.assertTrue(
                any("content patterns must stay within" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "content patterns must stay within"
            ):
                build_skills(source.parent, root / "output")

    def test_generated_reference_filenames_must_be_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entries = root / "alpha" / "entries"
            (entries / "hyphen.yaml").write_text(
                "id: alpha.foo-bar\nrule: Hyphen form\n",
                encoding="utf-8",
            )
            (entries / "dot.yaml").write_text(
                "id: alpha.foo.bar\nrule: Dot form\n",
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(any("output path collision" in error for error in errors))
            with self.assertRaisesRegex(DegardisError, "output path collision"):
                build_skills(root / "alpha", root / "output")
