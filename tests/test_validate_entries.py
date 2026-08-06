"""Validation of entry files and the fields they declare."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import validate

from tests.support import copy_skills


class EntryValidationTests(unittest.TestCase):
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
