"""How a profile is listed in SKILL.md, and what its description is held to."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.validate import inspect_skills

from tests.support import copy_skills, folder_text


def profile_lines(skill_markdown: str) -> list[str]:
    return [
        line
        for line in skill_markdown.splitlines()
        if line.startswith("- [") and "references/profiles/" in line
    ]


def rewrite_profile(root: Path, skill: str, profile: str, **fields: object) -> Path:
    """Set the given fields of one fixture profile, removing those given None."""
    source = root / skill / "profiles" / f"{profile}.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    for key, value in fields.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return source


class ProfileListingTests(unittest.TestCase):
    """The beta fixture ships one profile of each shape."""

    def build_beta(self, directory: str) -> Path:
        root = copy_skills(Path(directory))
        return build_skills(
            root / "beta",
            Path(directory) / "out",
            profiles=["beta:beta-only", "beta:shared"],
        )[0]

    def test_the_section_says_what_a_profile_is_and_how_to_select_one(self):
        """A label-only list is unusable unless the section states both facts.

        The per-profile descriptions used to teach the concept incidentally, once
        per line. With them optional, the one shared preamble has to carry it.
        """
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.build_beta(directory)

            text = folder_text(artifact, "SKILL.md")

            self.assertIn(
                "Profiles adapt this skill to a particular audience, format,"
                " technology, or environment. Load every profile whose label names"
                " something this request involves, and no others:",
                text,
            )

    def test_a_profile_without_a_description_is_listed_by_its_label_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.build_beta(directory)

            lines = profile_lines(folder_text(artifact, "SKILL.md"))

            self.assertIn("- [Beta Only](references/profiles/beta-only.md)", lines)

    def test_a_profile_with_a_description_keeps_it_on_the_same_line(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.build_beta(directory)

            lines = profile_lines(folder_text(artifact, "SKILL.md"))

            self.assertIn(
                "- [Shared](references/profiles/shared.md)"
                " — Shared fixture profile present on both alpha and beta skills.",
                lines,
            )

    def test_a_generated_reference_opens_with_its_heading_and_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.build_beta(directory)

            for name, heading in (
                ("beta-only", "# Beta Only"),
                ("shared", "# Shared"),
            ):
                with self.subTest(profile=name):
                    text = folder_text(artifact, f"references/profiles/{name}.md")
                    self.assertEqual(heading, text.splitlines()[0])
                    self.assertNotIn("---", text)
                    self.assertNotIn("description:", text)

    def test_a_generated_reference_still_carries_every_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.build_beta(directory)

            text = folder_text(artifact, "references/profiles/beta-only.md")

            self.assertIn("- Fixture profile content unique to beta.", text)


class ProfileDescriptionValidationTests(unittest.TestCase):
    def codes(self, skill: Path, severity: str = "error") -> list[str]:
        records = inspect_skills([skill])[0]["diagnostics"]
        return [record.code for record in records if record.severity == severity]

    def test_a_profile_that_supplies_no_description_reports_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            rewrite_profile(root, "alpha", "alpha-only", description=None)

            self.assertEqual([], self.codes(root / "alpha"))

    def test_a_blank_description_is_an_empty_condition_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            rewrite_profile(root, "alpha", "alpha-only", description="   ")

            self.assertIn("profile.description-length", self.codes(root / "alpha"))

    def test_a_description_over_the_length_limit_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            rewrite_profile(root, "alpha", "alpha-only", description="x" * 1025)

            self.assertIn("profile.description-length", self.codes(root / "alpha"))

    def test_a_description_that_is_not_a_string_is_reported_by_its_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            rewrite_profile(root, "alpha", "alpha-only", description=["a list"])

            self.assertIn("profile.invalid-type", self.codes(root / "alpha"))
