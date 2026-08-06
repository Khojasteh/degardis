"""Validation of entry files: their kinds, fields, and ordering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import inspect_skills, validate

from tests.support import copy_skills


class EntryValidationTests(unittest.TestCase):
    def test_unrecognized_entry_kind_warns_and_still_reaches_the_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "gamma" / "entries" / "rule-three.yaml"
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            data["kind"] = "guideline"
            entry.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "gamma"])[0]
            build_skills(root / "gamma", root / "output")
            generated = (
                root / "output" / "gamma" / "references" / "entries" / "rule-three.md"
            ).read_text(encoding="utf-8")

        self.assertEqual([], result["errors"])
        self.assertTrue(
            any(
                "unrecognized kind guideline compiled as declared" in warning
                for warning in result["warnings"]
            )
        )
        self.assertIn("**Kind:** `guideline`", generated)

    def test_empty_entry_kind_remains_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "gamma" / "entries" / "rule-three.yaml"
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            data["kind"] = "  "
            entry.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            errors = validate(root / "gamma")

        self.assertTrue(
            any("kind must be a non-empty string" in error for error in errors)
        )

    def test_omitted_behavior_bearing_entry_fields_warn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "gamma" / "entries" / "rule-three.yaml"
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            for field in ("title", "kind", "priority", "rationale"):
                data.pop(field, None)
            entry.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "gamma"])[0]

        warnings = "\n".join(result["warnings"])
        self.assertEqual([], result["errors"])
        self.assertIn("title is missing", warnings)
        self.assertIn("kind is missing", warnings)
        # A skill that orders nothing is told once, not once per entry.
        self.assertIn("no entry declares a priority", warnings)
        self.assertNotIn("priority is missing", warnings)
        # An inert optional field stays silent.
        self.assertNotIn("rationale", warnings)

    def test_a_missing_priority_warns_when_other_entries_declare_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entries = root / "alpha" / "entries"
            first = yaml.safe_load((entries / "rule-one.yaml").read_text("utf-8"))
            first["priority"] = 10
            (entries / "rule-one.yaml").write_text(
                yaml.safe_dump(first, sort_keys=False), encoding="utf-8"
            )
            second = dict(first, id="alpha.rule-two", title="Rule Two")
            second.pop("priority")
            (entries / "rule-two.yaml").write_text(
                yaml.safe_dump(second, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "alpha"])[0]

        warnings = "\n".join(result["warnings"])
        self.assertIn("rule-two.yaml: priority is missing", warnings)
        self.assertNotIn("no entry declares a priority", warnings)

    def test_shared_priorities_and_titles_warn_but_still_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entries = root / "alpha" / "entries"
            first = yaml.safe_load((entries / "rule-one.yaml").read_text("utf-8"))
            first["priority"] = 10
            (entries / "rule-one.yaml").write_text(
                yaml.safe_dump(first, sort_keys=False), encoding="utf-8"
            )
            (entries / "rule-two.yaml").write_text(
                yaml.safe_dump(dict(first, id="alpha.rule-two"), sort_keys=False),
                encoding="utf-8",
            )

            result = inspect_skills([root / "alpha"])[0]
            build_skills(root / "alpha", root / "output")

        warnings = "\n".join(result["warnings"])
        self.assertEqual([], result["errors"])
        self.assertIn("entries share priority 10", warnings)
        self.assertIn("entries share the title", warnings)

    def test_entry_list_fields_reject_scalar_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "entries" / "rule-one.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["require"] = "Do the whole requirement."
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(
                any("require must be a list of strings" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "require must be a list of strings"
            ):
                build_skills(root / "alpha", root / "output")
