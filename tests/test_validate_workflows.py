"""Validation of workflow files: their ids, steps, and reachability."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import inspect_skills

from tests.support import copy_skills, diagnostic_codes


class WorkflowValidationTests(unittest.TestCase):
    def test_an_unreached_workflow_warns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "gamma" / "workflows" / "run.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            orphan = dict(data, id="gamma.orphan", title="Orphan")
            (source.parent / "orphan.yaml").write_text(
                yaml.safe_dump(orphan, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "gamma"])[0]

        self.assertEqual([], result["errors"])
        self.assertIn("workflow.unreachable", diagnostic_codes(result, "warning"))

    def test_a_primary_workflow_without_a_description_warns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "gamma" / "workflows" / "run.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data.pop("description", None)
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "gamma"])[0]

        self.assertIn(
            "workflow.missing-description",
            diagnostic_codes(result, "warning"),
        )

    def test_a_step_without_an_instruction_warns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "gamma" / "workflows" / "run.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["steps"].append({"action": "finish"})
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([root / "gamma"])[0]

        self.assertEqual([], result["errors"])
        self.assertIn(
            "workflow.step-missing-instruction", diagnostic_codes(result, "warning")
        )

    def test_cross_skill_workflow_use_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "workflows" / "run.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["steps"].append({"use": "beta.run"})
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = inspect_skills([root / "alpha"])[0]
            self.assertIn(
                "workflow.unknown-reference", diagnostic_codes(result, "error")
            )

    def test_duplicate_workflow_ids_are_rejected_by_validate_and_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            duplicate = root / "alpha" / "workflows" / "duplicate.yaml"
            duplicate.write_text(
                "id: alpha.run\nsteps:\n- Repeat the primary workflow.\n",
                encoding="utf-8",
            )

            result = inspect_skills([root / "alpha"])[0]

            self.assertIn("workflow.duplicate-id", diagnostic_codes(result, "error"))
            with self.assertRaises(DegardisError):
                build_skills(root / "alpha", root / "output")

    def test_malformed_workflow_steps_are_rejected(self):
        invalid_steps = (
            42,
            {"use": 42},
            {"use": "alpha.run", "action": "also-run"},
        )
        for step in invalid_steps:
            with self.subTest(step=step):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha" / "workflows" / "run.yaml"
                    data = yaml.safe_load(source.read_text(encoding="utf-8"))
                    data["steps"] = [step]
                    source.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    result = inspect_skills([root / "alpha"])[0]

                    self.assertIn(
                        "workflow.invalid-step", diagnostic_codes(result, "error")
                    )
                    with self.assertRaises(DegardisError):
                        build_skills(root / "alpha", root / "output")
