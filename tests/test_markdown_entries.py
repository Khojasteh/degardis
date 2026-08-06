"""The section order a generated entry reference presents."""

from __future__ import annotations

import unittest
from pathlib import Path

from degardis.markdown import entry_markdown
from degardis.model import Entry


def sections(text: str) -> list[str]:
    return [
        line.removeprefix("## ") for line in text.splitlines() if line.startswith("## ")
    ]


class EntrySectionOrderTests(unittest.TestCase):
    def entry(self, **fields: object) -> Entry:
        data: dict[str, object] = {
            "id": "demo.every-field",
            "title": "Every Field",
            "kind": "constraint",
            "priority": 10,
            "rule": "The central instruction.",
        }
        data.update(fields)
        return Entry(path=Path("every-field.yaml"), data=data, skill="demo")

    def test_conditions_precede_the_requirements_they_qualify(self):
        text = entry_markdown(
            self.entry(
                require=["Do the required thing."],
                reject=["Never do the rejected thing."],
                conditions=["The qualifying situation holds."],
            )
        )
        order = sections(text)
        self.assertLess(order.index("Conditions"), order.index("Require"))
        self.assertLess(order.index("Conditions"), order.index("Reject"))

    def test_every_optional_section_renders_in_reading_order(self):
        text = entry_markdown(
            self.entry(
                rationale="The failure the rule prevents.",
                scope="Where the rule applies.",
                constraint="A bound the rule respects.",
                conditions=["The qualifying situation holds."],
                require=["Do the required thing."],
                allow=["The permitted thing is allowed."],
                reject=["Never do the rejected thing."],
                exceptions=["The stated exception."],
                examples=["A short example."],
            )
        )
        self.assertEqual(
            [
                "Rule",
                "Rationale",
                "Scope",
                "Constraint",
                "Conditions",
                "Require",
                "Allow",
                "Reject",
                "Exceptions",
                "Examples",
                "Metadata",
            ],
            sections(text),
        )

    def test_absent_sections_are_omitted_rather_than_left_empty(self):
        text = entry_markdown(self.entry(conditions=[], require=["Only this."]))
        self.assertEqual(["Rule", "Require", "Metadata"], sections(text))
