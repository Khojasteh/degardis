"""The one public example the repository ships, held to what it documents."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from degardis import wording
from degardis.build import build_skills
from degardis.validate import validate
from tests.support import (
    CANONICAL_EXAMPLE,
    REPO_ROOT,
    codes,
    compiled,
    folder_names,
    folder_text,
    inspect_one,
)


class CanonicalExampleTests(unittest.TestCase):
    def test_the_repository_has_one_public_example(self):
        manifests = sorted((REPO_ROOT / "examples").glob("*/skill.yaml"))
        self.assertEqual([CANONICAL_EXAMPLE / "skill.yaml"], manifests)

    def test_the_example_reports_no_error_and_no_warning(self):
        self.assertEqual([], validate(CANONICAL_EXAMPLE))
        self.assertEqual(set(), codes(CANONICAL_EXAMPLE, "warning"))

    def test_the_example_uses_every_construct_kind_the_format_defines(self):
        """The example is what an author reads first, so every kind it teaches
        has to be a kind it actually compiles."""
        counts = inspect_one(CANONICAL_EXAMPLE)["counts"]
        for key in (
            "policies",
            "rules",
            "patterns",
            "heuristics",
            "guidance",
            "protocols",
            "records",
            "workflows",
            "profiles",
            "references",
            "scripts",
            "assets",
        ):
            with self.subTest(key=key):
                self.assertGreater(counts[key], 0)

    def test_the_example_builds_the_features_it_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(CANONICAL_EXAMPLE, Path(directory))[0]
            names = folder_names(artifact)
            documented = {
                "SKILL.md",
                "agents/openai.yaml",
                "assets/icon-large.png",
                "assets/icon-small.png",
                "assets/template.md",
                "references/guidance/clear-reporting.md",
                "references/guidance/clear-reporting-examples.md",
                "references/heuristics/smallest-sufficient-detail.md",
                "references/patterns/outline-then-draft.md",
                "profiles/concise.md",
                "profiles/detailed.md",
                "profiles/index.md",
                "scripts/list_headings.py",
            }
            # By difference rather than `issubset`, so a feature the example
            # stops building is named in the failure instead of reported as a
            # false that gives the reader nothing to look for.
            self.assertEqual([], sorted(documented - names))

    def test_the_example_document_carries_each_construct_where_it_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(CANONICAL_EXAMPLE, Path(directory))[0]
            root = folder_text(artifact, "SKILL.md")
            modules = "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted((artifact / "execution").glob("*.md"))
            )
            text = root + "\n" + modules
        guidance = sorted(compiled(CANONICAL_EXAMPLE)[1].lowered.sources.guidance)
        self.assertTrue(guidance, "the example selects no guidance unit")
        for fragment in (
            "## Execution contract",
            f"## {wording.CONTEXT_HEADING}",
            f"## {wording.PROFILES_HEADING}",
            f"**{wording.REQUIRED}**",
            f"**{wording.PROHIBITED}**",
            f"**{wording.VERIFY}**",
            f"**{wording.STATE_UPDATE}**",
            f"**{wording.CONSIDER}**",
            wording.ON_FAILURE,
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)
        self.assertTrue(
            any(
                f"**{wording.CONTEXT_NOTE.format(id=identifier)}**" in text
                for identifier in guidance
            ),
            "no step carries a guidance note",
        )

    def test_the_example_script_lists_markdown_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "material.md"
            source.write_text(
                "# Subject\n\nContext\n\n## Main point\n", encoding="utf-8"
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
            self.assertEqual(["Subject", "Main point"], result.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
