"""The list command and the metadata it reports for each skill."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.cli import main

from tests.support import FIXTURES, copy_skills


class ListCommandTests(unittest.TestCase):
    def test_list_accepts_multiple_explicit_skills(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(
                [
                    "list",
                    str(FIXTURES / "alpha"),
                    str(FIXTURES / "gamma"),
                ]
            )
        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("Skills (2)", report)
        self.assertIn("Alpha (alpha)  v1.0.0", report)
        self.assertIn("Gamma (gamma)  v1.0.0", report)
        self.assertNotIn("Beta (beta)", report)
        self.assertIn("Description", report)
        self.assertIn("Profiles", report)
        self.assertIn("License", report)
        self.assertIn("Copyright", report)
        self.assertIn("Source", report)

    def test_list_reports_whether_skill_uses_scripts(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["list", str(FIXTURES / "alpha"), str(FIXTURES / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertRegex(report, r"Scripts\s+(Yes|No)")

    def test_list_reports_missing_optional_metadata_and_profiles(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["list", str(FIXTURES / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("Skills (1)", report)
        self.assertIn("Profiles    None", report)
        self.assertIn("License     Not specified", report)
        self.assertIn("Copyright   Not specified", report)

    def test_list_reports_legal_metadata_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["license"] = "MIT"
            data["copyright"] = "Copyright (c) Example"
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["list", str(root / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("License     MIT", report)
        self.assertIn("Copyright   Copyright (c) Example", report)
