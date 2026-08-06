"""What a build reports, and what it refuses before writing anything."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import SkillCompiler, build_skills
from degardis.model import DegardisError, DegardisWarning

from tests.support import copy_skills, make_skill_markdown_cross_warning_boundary


class BuildReportTests(unittest.TestCase):
    def test_build_rejects_unsupported_content_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["unknown"] = ["unknown/**/*"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                DegardisError, "unsupported content fields: unknown"
            ):
                build_skills(source.parent, Path(directory) / "output")

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

    def test_explicit_profiles_warn_for_oversized_selected_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            make_skill_markdown_cross_warning_boundary(root)
            output = Path(directory) / "output"

            with self.assertWarnsRegex(
                DegardisWarning,
                "generated SKILL.md has 507 lines",
            ):
                artifact = SkillCompiler(root / "gamma").build(
                    output,
                    profiles=["all"],
                )[0]

            self.assertTrue(artifact.is_dir())
            self.assertEqual(
                507,
                len(
                    (artifact / "SKILL.md")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
            )
