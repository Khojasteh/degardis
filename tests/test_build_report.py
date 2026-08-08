"""What a build reports, and what it refuses before writing anything."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.cli import main
from degardis.model import DegardisError

from tests.support import FIXTURES, copy_skills


class BuildReportTests(unittest.TestCase):
    def test_build_report_names_the_artifact_without_measuring_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    ["build", str(FIXTURES / "alpha"), "--output", str(output)]
                )
            artifact = output / "alpha"

        report = stdout.getvalue()
        self.assertEqual(0, code)
        self.assertIn("Artifact", report)
        self.assertIn(str(artifact.resolve()), report)
        # Sizing the generated SKILL.md is `degardis agent`'s job, not build's.
        self.assertNotIn("SKILL.md", report)
        self.assertNotIn(" bytes", report)
        self.assertNotIn(" lines", report)

    def test_build_warns_about_unrecognized_content_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["unknown"] = ["unknown/**/*"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(source.parent),
                        "--output",
                        str(Path(directory) / "output"),
                    ]
                )

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("unrecognized content fields ignored: unknown", report)
        self.assertIn("Summary: 1 skill built as folder, 1 warning.", report)

    def test_build_reports_every_validation_error_at_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["interface"]["default_prompt"] = "Missing token"
            data["content"]["assets"] = ["assets/*.png"]
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaises(DegardisError) as raised:
                build_skills(root / "alpha", root / "output")

        message = str(raised.exception)
        self.assertIn("2 errors:", message)
        self.assertIn("interface.default_prompt must mention $alpha", message)
        self.assertIn("content.assets pattern assets/*.png matches nothing", message)

    def test_build_rejects_invalid_interface_before_replacing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = root / "output"
            artifact = build_skills(root / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            del data["interface"]
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                DegardisError, "interface.display_name is required"
            ):
                build_skills(root / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))
