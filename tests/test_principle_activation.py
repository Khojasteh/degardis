from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.model import Diagnostics
from degardis.registry import load_skill_path
from degardis.validate import compile_skill


MANIFEST = """\
name: demo
format_version: 2
version: 1.0.0
description: Demo principle activation skill.
purpose: Exercise principle activation placement.
principles:
- always
- root-conditional
tasks:
- review
content:
  tasks:
  - tasks/*.md
  principles:
  - principles/*.md
interface:
  display_name: Demo
  short_description: Demo principle activation
  default_prompt: Use demo for this request.
"""

TASK = """\
---
title: Review
recognize:
- the requester asks for a review
goal: Return a reviewed result.
principles:
- tasky
- actiony
- root-conditional
---

Review the supplied material.
"""

PRINCIPLES = {
    "always.md": """---\ntitle: Always\n---\n\nAlways guidance.\n""",
    "root-conditional.md": """---\ntitle: Root conditional\nactivation: the request concerns regulated work\n---\n\nConditional root guidance.\n""",
    "tasky.md": """---\ntitle: Tasky\n---\n\nTask guidance.\n""",
    "actiony.md": """---\ntitle: Actiony\nactivation: immediately before delegating work\n---\n\nAction guidance.\n""",
}


class PrincipleActivationHarness(unittest.TestCase):
    """A skill whose principles are selected at both levels, with and without
    an activation, which is the overlap the demo fixture does not carry."""

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


class PlacementTests(PrincipleActivationHarness):
    def setUp(self) -> None:
        self.compiled, diagnostics = self.compile(self.make_skill())
        self.assertFalse(diagnostics.errors)
        self.task_plan = self.compiled.plan.tasks[0]
        self.root_principles = {
            item.id: item for item in self.compiled.plan.root_principles
        }
        self.task_principles = {item.id: item for item in self.task_plan.principles}

    def test_each_level_selects_its_own_principles(self):
        self.assertEqual({"always", "root-conditional"}, set(self.root_principles))
        self.assertEqual(
            {"tasky", "actiony", "root-conditional"}, set(self.task_principles)
        )

    def test_a_principle_both_levels_select_states_one_activation(self):
        """Two placements of one principle cannot state two conditions, or an
        agent that read the root would be told to apply it at another moment
        than an agent that reached the task."""
        self.assertNotEqual("", self.root_principles["root-conditional"].activation)
        self.assertEqual(
            self.root_principles["root-conditional"].activation,
            self.task_principles["root-conditional"].activation,
        )

    def test_a_principle_stating_no_activation_is_read_as_always(self):
        self.assertEqual("", self.root_principles["always"].activation)

    def test_the_root_links_every_skill_principle_and_states_its_condition(self):
        root = self.compiled.rendered.skill_text
        for principle in self.root_principles.values():
            with self.subTest(principle=principle.id):
                self.assertIn(
                    f"[{principle.title}](references/principles/{principle.id}.md)",
                    root,
                )
                if principle.activation:
                    self.assertIn(principle.activation, root)

    def test_a_principle_only_a_task_selects_is_not_stated_on_the_root(self):
        self.assertNotIn(
            self.task_principles["tasky"].title, self.compiled.rendered.skill_text
        )

    def test_a_task_links_its_own_principles_and_states_their_conditions(self):
        task = self.compiled.rendered.pages[self.task_plan.page]
        for principle in self.task_principles.values():
            with self.subTest(principle=principle.id):
                self.assertIn(
                    f"[{principle.title}](../principles/{principle.id}.md)", task
                )
                if principle.activation:
                    self.assertIn(principle.activation, task)

    def test_a_task_links_a_principle_rather_than_carrying_its_body(self):
        """The page an agent opens for one class of work is not where skill-wide
        guidance is restated; the link is what keeps one statement of it."""
        task = self.compiled.rendered.pages[self.task_plan.page]
        self.assertNotIn(self.task_principles["actiony"].body, task)


class ActivationSchemaTests(PrincipleActivationHarness):
    def test_a_task_principle_without_a_local_file_is_an_error(self):
        task = TASK.replace("- tasky\n", "- missing\n")
        _, diagnostics = self.compile(self.make_skill(task_text=task))
        codes = {record.code for record in diagnostics.records}
        self.assertIn("task.unknown-principle", codes)

    def test_invalid_principle_activation_is_an_error(self):
        root = self.make_skill()
        path = root / "principles" / "actiony.md"
        path.write_text(path.read_text().replace("activation: immediately before delegating work", "activation: ''"))
        _, diagnostics = self.compile(root)
        codes = {record.code for record in diagnostics.records}
        self.assertIn("principle.invalid-activation", codes)


if __name__ == "__main__":
    unittest.main()
