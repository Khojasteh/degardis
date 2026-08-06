"""The validate command: its exit status and the shape of its report."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.cli import main

from tests.support import FIXTURES, copy_skills


class ValidateCommandTests(unittest.TestCase):
    def test_validate_command_returns_nonzero_for_invalid_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["assets"] = ["assets/*.png"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

            self.assertEqual(1, code)
            report = stdout.getvalue()
            self.assertIn("Validation\n", report)
            self.assertIn("[FAIL] Alpha (alpha)", report)
            self.assertIn(
                "1. alpha: content.assets pattern assets/*.png matches nothing", report
            )
            self.assertIn("Summary: 0 passed, 1 failed, 1 error, 0 warnings, 1 total.", report)

    def test_validate_command_reports_each_skill_like_a_test_run(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["validate", str(FIXTURES)])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("[PASS] Alpha (alpha)", report)
        self.assertIn("[PASS] Beta (beta)", report)
        self.assertIn("[PASS] Gamma (gamma)", report)
        self.assertIn("Summary: 3 passed, 0 failed, 0 errors, 0 warnings, 3 total.", report)

    def test_validate_warns_for_unrecognized_fields_at_every_level(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["descriptino"] = "typo field"
            data["interface"]["display_nam"] = "typo field"
            data["content"]["entires"] = ["entries/*.yaml"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            entry_data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            entry_data["rationalee"] = "typo field"
            entry.write_text(yaml.safe_dump(entry_data, sort_keys=False), encoding="utf-8")
            workflow = root / "alpha" / "workflows" / "run.yaml"
            workflow_data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            workflow_data["titel"] = "typo field"
            workflow_data["steps"].append({"action": "finish", "instructoin": "typo"})
            workflow.write_text(
                yaml.safe_dump(workflow_data, sort_keys=False),
                encoding="utf-8",
            )
            profile = root / "alpha" / "profiles" / "alpha-only.yaml"
            profile_data = yaml.safe_load(profile.read_text(encoding="utf-8"))
            profile_data["lable"] = "typo field"
            profile.write_text(
                yaml.safe_dump(profile_data, sort_keys=False),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        self.assertEqual(0, code)
        report = " ".join(stdout.getvalue().split())
        for message in (
            "unrecognized manifest fields ignored: descriptino",
            "unrecognized interface fields ignored: display_nam",
            "unrecognized content fields ignored: entires",
            "unrecognized entry fields ignored: rationalee",
            "unrecognized workflow fields ignored: titel",
            "has unrecognized fields ignored: instructoin",
            "unrecognized profile fields ignored: lable",
        ):
            with self.subTest(message=message):
                self.assertIn(message, report)

    def test_validate_aggregates_multiple_issues_in_one_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["unknown_field"] = "on"
            data["content"]["assets"] = ["assets/*.png"]
            data["interface"]["default_prompt"] = "Missing token"
            data["content"]["unknown"] = ["unknown/**/*"]
            text = yaml.safe_dump(data, sort_keys=False)
            text = text.replace("unknown_field: 'on'", "unknown_field: on")
            manifest.write_text(text, encoding="utf-8")
            workflow = root / "alpha" / "workflows" / "run.yaml"
            workflow_data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            workflow_data["steps"].append({"use": "beta.run"})
            workflow.write_text(
                yaml.safe_dump(workflow_data, sort_keys=False),
                encoding="utf-8",
            )
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            entry_data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            entry_data["priority"] = "high"
            entry_data["kind"] = "guideline"
            entry_data["require"] = "Not a list"
            entry.write_text(
                yaml.safe_dump(entry_data, sort_keys=False),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        self.assertEqual(1, code)
        report = " ".join(stdout.getvalue().split())
        for message in (
            "content.assets pattern assets/*.png matches nothing",
            "interface.default_prompt must mention $alpha",
            "cross-skill",
            "workflow reference beta.run",
            "unrecognized kind guideline compiled as declared",
            "must be an integer",
            "must be a list of strings",
            "Warning: alpha: unrecognized manifest fields ignored: unknown_field",
            "Warning: alpha: unrecognized content fields ignored: unknown",
            "may coerce in YAML",
        ):
            with self.subTest(message=message):
                self.assertIn(message, report)

    def test_validate_names_the_check_behind_every_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            text = entry.read_text(encoding="utf-8")
            text += "priority: high\nscope: &Shared applies everywhere\n"
            entry.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertEqual(1, code)
        self.assertIn("priority must be an integer (entry.invalid-type)", report)
        self.assertIn("quote the value (yaml.altered-scalar)", report)
        self.assertIn("Run `degardis explain CODE [CODE ...]`", report)

    def test_validate_reports_no_explain_hint_when_nothing_is_found(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["validate", str(FIXTURES / "alpha")])

        report = stdout.getvalue()
        self.assertEqual(0, code)
        self.assertNotIn("degardis explain", report)
