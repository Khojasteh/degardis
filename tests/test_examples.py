"""The one public example the repository ships, held to what it documents."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from degardis import wording
from degardis.bundlepaths import ROOT
from degardis.build import build_skills
from degardis.inspection import validate
from tests.support import (
    CANONICAL_EXAMPLE,
    REPO_ROOT,
    codes,
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
            "tasks",
            "principles",
            "knowledge",
            "facets",
            "guides",
            "scripts",
        ):
            with self.subTest(key=key):
                self.assertGreater(counts[key], 0)
        kinds = {row["kind"] for row in inspect_one(CANONICAL_EXAMPLE)["knowledge"]}
        self.assertEqual({"concept", "fact", "constraint", "guidance"}, kinds)

    def test_the_example_selects_its_principles_at_skill_scope(self):
        """Skill-level placement is what the example teaches, so every
        principle it selects has to be owned by the root rather than a task."""
        placement = inspect_one(CANONICAL_EXAMPLE)["principles"]
        selected = set(placement["selected"])
        self.assertNotEqual(set(), selected)
        task_owned = sorted(
            f"{row['id']} from {item['owner']}"
            for row in placement["states"]
            if row["id"] in selected
            for item in row["placements"]
            if item["owner"] != ROOT
        )
        self.assertEqual([], task_owned)

    def test_the_example_shows_always_and_conditionally_active_skill_principles(self):
        result = inspect_one(CANONICAL_EXAMPLE)
        states = {row["id"]: row for row in result["principles"]["states"]}
        summarize = next(row for row in result["tasks"] if row["id"] == "summarize")
        task_principles = {
            principle["id"]: principle["activation"]
            for principle in summarize["principles"]
        }

        self.assertEqual("", states["provenance"]["activation"])
        self.assertNotEqual("", states["evidence"]["activation"])
        self.assertEqual({}, task_principles)

    def test_the_example_shows_a_requirement_expanding_a_closure(self):
        composition = {
            row["id"]: row for row in inspect_one(CANONICAL_EXAMPLE)["composition"]
        }
        self.assertIn("audience", composition["summarize"]["required"])
        self.assertNotIn("audience", composition["summarize"]["direct"])

    def test_the_example_shows_facets_in_more_than_one_category(self):
        categories = {row["category"] for row in inspect_one(CANONICAL_EXAMPLE)["facets"]}
        self.assertEqual({"Material", "Audience"}, categories)

    def test_the_example_shows_a_facet_with_and_without_a_description(self):
        described = {
            row["id"]: bool(row["description"])
            for row in inspect_one(CANONICAL_EXAMPLE)["facets"]
        }
        self.assertIn(True, described.values())
        self.assertIn(False, described.values())

    def test_the_example_builds_the_features_it_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(CANONICAL_EXAMPLE, Path(directory))[0]
            names = folder_names(artifact)
            documented = {
                "SKILL.md",
                "agents/openai.yaml",
                "assets/icon-large.png",
                "assets/icon-small.png",
                "references/facets/index.md",
                "references/principles/evidence.md",
                "references/principles/provenance.md",
                "references/principles/reporting.md",
                "references/principles/requester-questions.md",
                "references/principles/enumeration.md",
                "references/facets/engineering.md",
                "references/facets/executive.md",
                "references/facets/research-paper.md",
                "references/facets/transcript.md",
                "references/guides/summary-template.md",
                "references/guides/transcript-passes.md",
                "scripts/list_headings.py",
                "references/tasks/brief.md",
                "references/tasks/report-gaps.md",
                "references/tasks/summarize.md",
            }
            # By difference rather than `issubset`, so a feature the example
            # stops building is named in the failure instead of reported as a
            # false that gives the reader nothing to look for.
            self.assertEqual([], sorted(documented - names))

    def test_the_example_document_carries_each_section_where_it_belongs(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(CANONICAL_EXAMPLE, Path(directory))[0]
            root = folder_text(artifact, "SKILL.md")
            task = folder_text(artifact, "references/tasks/summarize.md")
            index = folder_text(artifact, "references/facets/index.md")
        for fragment in (
            f"## {wording.FACETS_HEADING}",
            f"## {wording.TASKS_HEADING}",
        ):
            with self.subTest(fragment=fragment, page="SKILL.md"):
                self.assertIn(fragment, root)
        for fragment in (
            f"## {wording.GOAL_HEADING}",
            f"## {wording.KNOWLEDGE_HEADING}",
            f"### {wording.KNOWLEDGE_KIND_HEADINGS['constraint']}",
            f"## {wording.GUIDES_HEADING}",
        ):
            with self.subTest(fragment=fragment, page="references/tasks/summarize.md"):
                self.assertIn(fragment, task)
        self.assertIn(wording.FACET_INDEX_LEAD, index)

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
