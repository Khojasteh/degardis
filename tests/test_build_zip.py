"""The zip artifact a build writes with --zip."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from degardis.build import build_skills

from tests.support import FIXTURES, zip_names, zip_text


class ZipOutputTests(unittest.TestCase):
    def test_build_emits_one_zip_archive_per_skill_with_zip_option(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = build_skills(FIXTURES, output, as_zip=True)
            self.assertEqual(3, len(paths))
            for path in paths:
                self.assertEqual(output / f"{path.stem}.zip", path)

    def test_zip_archive_has_no_target_specific_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory), as_zip=True)[0]
            names = zip_names(path)
            self.assertIn("SKILL.md", names)
            self.assertIn("agents/openai.yaml", names)
            self.assertFalse(any(name.startswith(".") for name in names))

    def test_scripts_and_assets_are_packaged_in_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory), as_zip=True)[0]
            names = zip_names(path)
            self.assertIn("scripts/greet.py", names)
            self.assertIn("assets/template.md", names)
            text = zip_text(path, "SKILL.md")
            self.assertIn("scripts/greet.py", text)
            self.assertIn("assets/template.md", text)
            with zipfile.ZipFile(path) as archive:
                script_mode = archive.getinfo("scripts/greet.py").external_attr >> 16
                asset_mode = archive.getinfo("assets/template.md").external_attr >> 16
            self.assertTrue(script_mode & 0o100)
            self.assertFalse(asset_mode & 0o100)

    def test_zip_rebuild_replaces_only_selected_skill_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_skills(FIXTURES, output, as_zip=True)
            stale_folder = output / "alpha"
            stale_folder.mkdir()
            paths = build_skills(FIXTURES / "alpha", output, as_zip=True)
            self.assertFalse(stale_folder.exists())
            self.assertTrue((output / "beta.zip").is_file())
            self.assertTrue((output / "gamma.zip").is_file())
            self.assertEqual({"alpha"}, {path.stem for path in paths})

    def test_archives_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            content = first.read_bytes()
            second = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            self.assertEqual(content, second.read_bytes())
            with zipfile.ZipFile(second) as archive:
                self.assertIsNone(archive.testzip())
