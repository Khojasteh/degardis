"""The folder artifact a build writes by default."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills

from tests.support import FIXTURES, copy_skills, folder_names, folder_text


class FolderOutputTests(unittest.TestCase):
    def test_build_emits_one_flat_folder_per_skill_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = build_skills(FIXTURES, output)
            self.assertEqual(3, len(paths))
            for path in paths:
                self.assertEqual(output / path.name, path)
                self.assertTrue(path.is_dir())

    def test_folder_has_no_target_specific_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory))[0]
            names = folder_names(path)
            self.assertIn("SKILL.md", names)
            self.assertIn("agents/openai.yaml", names)
            self.assertFalse(any(name.startswith(".") for name in names))
            text = folder_text(path, "SKILL.md")
            self.assertNotIn("Related Skills", text)

    def test_legal_metadata_is_emitted_in_spec_compliant_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["license"] = "Apache-2.0"
            data["copyright"] = "Copyright 2026 Example Corp"
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            path = build_skills(source.parent, root / "output")[0]
            text = folder_text(path, "SKILL.md")
            frontmatter = yaml.safe_load(text.split("---", 2)[1])

            self.assertEqual("Apache-2.0", frontmatter["license"])
            self.assertEqual(
                "Copyright 2026 Example Corp",
                frontmatter["metadata"]["copyright"],
            )
            self.assertEqual("1.0.0", frontmatter["metadata"]["version"])
            self.assertEqual(
                "degardis/1.0.1",
                frontmatter["metadata"]["generated_by"],
            )
            self.assertNotIn("format_version", frontmatter["metadata"])
            self.assertNotIn("copyright", frontmatter)

    def test_scripts_and_assets_are_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory))[0]
            names = folder_names(path)
            self.assertIn("scripts/greet.py", names)
            self.assertIn("assets/template.md", names)
            text = folder_text(path, "SKILL.md")
            self.assertIn("scripts/greet.py", text)
            self.assertIn("assets/template.md", text)
            self.assertNotIn("## Documents", text)
            self.assertFalse(
                any(name.startswith("references/documents/") for name in names)
            )

    def test_rebuild_replaces_only_selected_skill_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_skills(FIXTURES, output)
            stale_zip = output / "alpha.zip"
            stale_zip.write_text("stale", encoding="utf-8")
            paths = build_skills(FIXTURES / "alpha", output)
            self.assertFalse(stale_zip.exists())
            self.assertTrue((output / "beta" / "SKILL.md").is_file())
            self.assertTrue((output / "gamma" / "SKILL.md").is_file())
            self.assertEqual({"alpha"}, {path.name for path in paths})

    def test_rebuild_replaces_existing_skill_folder_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = build_skills(FIXTURES / "alpha", output)[0]
            stray = path / "stray.md"
            stray.write_text("stray", encoding="utf-8")
            build_skills(FIXTURES / "alpha", output)
            self.assertFalse(stray.exists())
