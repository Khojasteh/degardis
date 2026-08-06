"""The validate command: its exit status and the shape of its report."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.cli import main
from degardis.validate import validate

from tests.support import (
    FIXTURES,
    copy_skills,
    make_skill_markdown_cross_warning_boundary,
)


class ValidateCommandTests(unittest.TestCase):
    def test_validate_command_returns_nonzero_for_invalid_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["missing-profile"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

            self.assertEqual(1, code)
            report = stdout.getvalue()
            self.assertIn("Validation\n", report)
            self.assertIn("[FAIL] Alpha (alpha)", report)
            self.assertIn("1. Unknown default profiles for alpha: missing-profile", report)
            self.assertIn("Summary: 0 passed, 1 failed, 1 total.", report)

    def test_validate_command_reports_each_skill_like_a_test_run(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["validate", str(FIXTURES)])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("[PASS] Alpha (alpha)", report)
        self.assertIn("[PASS] Beta (beta)", report)
        self.assertIn("[PASS] Gamma (gamma)", report)
        self.assertIn("Summary: 3 passed, 0 failed, 3 total.", report)

    def test_validate_reports_oversized_skill_markdown_as_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            make_skill_markdown_cross_warning_boundary(root)
            manifest = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["extra"]
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("[PASS] Gamma (gamma)", report)
        self.assertIn(
            "Warning: gamma: generated SKILL.md has 507 lines; the recommended",
            report,
        )
        self.assertIn("Warnings: 1.", report)
