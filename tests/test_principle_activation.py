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
  default_prompt: Use {name} for this request.
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


class PrincipleActivationTests(unittest.TestCase):
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

    def test_places_each_activation_at_its_boundary(self):
        compiled, diagnostics = self.compile(self.make_skill())
        self.assertFalse(diagnostics.errors)
        root = compiled.rendered.skill_text
        task_plan = compiled.plan.tasks[0]
        task = compiled.rendered.pages[task_plan.page]
        root_principles = {item.id: item for item in compiled.plan.root_principles}
        task_principles = {item.id: item for item in task_plan.principles}

        self.assertEqual({"always", "root-conditional"}, set(root_principles))
        self.assertEqual({"tasky", "actiony", "root-conditional"}, set(task_principles))
        self.assertEqual("", root_principles["always"].activation)
        self.assertTrue(root_principles["root-conditional"].activation)
        self.assertEqual(
            root_principles["root-conditional"].activation,
            task_principles["root-conditional"].activation,
        )

        for principle in root_principles.values():
            self.assertIn(
                f"[{principle.title}](references/principles/{principle.id}.md)", root
            )
            if principle.activation:
                self.assertIn(principle.activation, root)
        self.assertNotIn(task_principles["tasky"].title, root)

        for principle in task_principles.values():
            self.assertIn(
                f"[{principle.title}](../principles/{principle.id}.md)", task
            )
            if principle.activation:
                self.assertIn(principle.activation, task)
        self.assertNotIn(task_principles["actiony"].body, task)

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

    def test_missing_principle_activation_is_always(self):
        compiled, diagnostics = self.compile(self.make_skill())
        self.assertFalse(diagnostics.errors)
        principle = next(p for p in compiled.plan.root_principles if p.id == "always")
        self.assertEqual("", principle.activation)


if __name__ == "__main__":
    unittest.main()
