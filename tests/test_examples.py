"""The examples the repository ships, held to the features they document."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.registry import load_profile
from degardis.validate import validate

from tests.support import CANONICAL_EXAMPLE, REPO_ROOT, copy_skills, folder_names


class StructuredProfileTests(unittest.TestCase):
    def test_external_markdown_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "profiles" / "alpha-only.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["details_files"] = ["details/extra.md"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            details = source.parent / "details" / "extra.md"
            details.parent.mkdir()
            details.write_text("## Extra\n\nResolved content.\n", encoding="utf-8")
            profile = load_profile(source, "alpha", root / "alpha")
            self.assertIn("## Extra", profile.text)
            self.assertIn("Resolved content.", profile.text)


class CanonicalExampleTests(unittest.TestCase):
    def test_repository_has_one_public_example(self):
        manifests = sorted((REPO_ROOT / "examples").glob("*/skill.yaml"))
        self.assertEqual([CANONICAL_EXAMPLE / "skill.yaml"], manifests)

    def test_example_validates_and_builds_all_documented_features(self):
        self.assertEqual([], validate(CANONICAL_EXAMPLE))
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(
                CANONICAL_EXAMPLE,
                Path(directory),
                profiles=["detailed"],
            )[0]
            names = folder_names(artifact)
            self.assertTrue(
                {
                    "SKILL.md",
                    "agents/openai.yaml",
                    "assets/icon-large.png",
                    "assets/icon-small.png",
                    "assets/template.md",
                    "references/entries/audience.md",
                    "references/entries/fidelity.md",
                    "references/profiles/detailed.md",
                    "references/workflows/inspect.md",
                    "scripts/list_headings.py",
                }.issubset(names)
            )

    def test_example_script_lists_markdown_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "material.md"
            source.write_text(
                "# Subject\n\nContext\n\n## Main point\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(CANONICAL_EXAMPLE / "scripts" / "list_headings.py"),
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                ["Subject", "Main point"],
                result.stdout.splitlines(),
            )
