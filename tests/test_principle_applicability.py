from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis import wording
from degardis.model import Diagnostics
from degardis.registry import load_skill_path
from degardis.validate import compile_skill


MANIFEST = """\
name: demo
format_version: 2
version: 1.0.0
description: Demo principle applicability skill.
stance: Exercise conditional principle placement.
principles:
- always
- root-conditional
- actiony
tasks:
- review
content:
  tasks:
  - tasks/*.md
  principles:
  - principles/*.md
interface:
  display_name: Demo
  short_description: Demo principle applicability
  default_prompt: Use demo for this request.
"""

TASK = """\
---
title: Review
cues:
- the requester asks for a review
goal: Return a reviewed result.
---

Review the supplied material.
"""

PRINCIPLES = {
    "always.md": """---\ntitle: Always\n---\n\nAlways guidance.\n""",
    "root-conditional.md": """---\ntitle: Root conditional\napplicability:\n- the request concerns regulated work\n---\n\nConditional root guidance.\n""",
    "actiony.md": """---\ntitle: Actiony\napplicability:\n- immediately before delegating work\n- immediately before accepting delegated work\n---\n\nAction guidance.\n""",
}


class PrincipleApplicabilityHarness(unittest.TestCase):
    """A skill whose principles state no condition, one, and several, which is
    the spread the demo fixture does not carry in one small source."""

    def make_skill(self, *, task_text: str = TASK) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "demo"
        (root / "tasks").mkdir(parents=True)
        (root / "principles").mkdir()
        (root / "skill.yaml").write_text(MANIFEST)
        (root / "tasks" / "review.md").write_text(task_text)
        for name, text in PRINCIPLES.items():
            (root / "principles" / name).write_text(text)
        return root

    def compile(self, root: Path):
        diagnostics = Diagnostics()
        compiled = compile_skill(load_skill_path(root), diagnostics)
        return compiled, diagnostics


class PlacementTests(PrincipleApplicabilityHarness):
    def setUp(self) -> None:
        self.compiled, diagnostics = self.compile(self.make_skill())
        self.assertFalse(diagnostics.errors)
        self.principles = {item.id: item for item in self.compiled.plan.principles}

    def test_the_skill_places_every_principle_it_names(self):
        self.assertEqual({"always", "root-conditional", "actiony"}, set(self.principles))

    def test_a_principle_stating_no_conditions_is_read_as_always(self):
        self.assertEqual((), self.principles["always"].applicability)

    def test_the_root_links_every_skill_principle_and_states_its_condition(self):
        root = self.compiled.rendered.skill_text
        for principle in self.principles.values():
            with self.subTest(principle=principle.id):
                self.assertIn(
                    f"[{principle.title}](references/principles/{principle.id}.md)",
                    root,
                )
                for condition in principle.applicability:
                    self.assertIn(condition, root)

    def test_a_task_page_lists_no_principle_even_when_the_task_names_one(self):
        """A principle holds across every task, so the root states it once and
        no task page restates it, conditional or not: a second list would be a
        second place for its conditions to disagree. A task naming one is
        warned of a field its schema does not define."""
        named = TASK.replace("goal:", "principles:\n- actiony\ngoal:")
        compiled, diagnostics = self.compile(self.make_skill(task_text=named))
        task = compiled.rendered.pages[compiled.plan.tasks[0].page]
        self.assertNotIn(f"## {wording.PRINCIPLES_HEADING}", task)
        self.assertNotIn("../principles/", task)
        self.assertEqual(
            ["task.unknown-field"], [record.code for record in diagnostics.records]
        )


class ApplicabilitySchemaTests(PrincipleApplicabilityHarness):
    def test_invalid_principle_conditions_are_an_error(self):
        root = self.make_skill()
        path = root / "principles" / "actiony.md"
        path.write_text(
            path.read_text().replace(
                "- immediately before accepting delegated work", "- ''"
            )
        )
        _, diagnostics = self.compile(root)
        codes = {record.code for record in diagnostics.records}
        self.assertIn("principle.invalid-applicability", codes)


if __name__ == "__main__":
    unittest.main()
