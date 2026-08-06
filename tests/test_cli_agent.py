"""The agent command and the sections it measures."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.cli import main

from tests.support import FIXTURES, copy_skills


def with_an_unreached_workflow(root: Path) -> None:
    """Give one fixture skill a workflow no step reaches."""
    source = root / "gamma" / "workflows" / "run.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    (source.parent / "orphan.yaml").write_text(
        yaml.safe_dump(dict(data, id="gamma.orphan", title="Orphan"), sort_keys=False),
        encoding="utf-8",
    )


class AgentCommandTests(unittest.TestCase):
    def test_agent_reports_the_default_sections_only(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["agent", str(FIXTURES / "alpha")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn('skill alpha 1.0.0 "Alpha"', report)
        self.assertIn("ids   alpha.*", report)
        self.assertIn("main  run", report)
        self.assertIn("1 entries, 1 workflows, 2 profiles", report)
        self.assertIn("body  SKILL.md ", report)
        self.assertIn("workflows 1", report)
        self.assertIn("run primary", report)
        self.assertIn("1 skill, 0 errors, 0 warnings", report)
        # Listings and the full description stay behind an explicit request.
        self.assertNotIn("entries 1 ", report)
        self.assertNotIn("outputs ", report)
        self.assertNotIn("lic   ", report)

    def test_agent_all_reports_every_section_with_paths_and_sizes(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["agent", str(FIXTURES / "alpha"), "--all"])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("entries 1  rule 1", report)
        self.assertIn("entries/rule-one.yaml", report)
        self.assertIn("profiles 2  0 selected", report)
        self.assertIn("profiles/alpha-only.yaml", report)
        self.assertIn("scripts/greet.py", report)
        self.assertIn("references/entries/rule-one.md", report)
        self.assertIn("agents/openai.yaml", report)
        self.assertIn("lic   ", report)

    def test_agent_only_selects_sections_and_always_names_the_skill(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["agent", str(FIXTURES / "alpha"), "--only", "entries"])
        report = stdout.getvalue()

        self.assertEqual(0, code)
        self.assertIn("skill alpha", report)
        self.assertIn("entries 1  rule 1", report)
        self.assertNotIn("workflows 1", report)
        self.assertNotIn("body  SKILL.md", report)

    def test_agent_measures_the_profiles_a_build_would_include(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = Path(directory) / "out"
            build_skills(root / "alpha", output, ["shared"])
            built = (output / "alpha" / "SKILL.md").read_bytes()

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "agent",
                        str(root / "alpha"),
                        "--only",
                        "budget",
                        "--profile",
                        "shared",
                    ]
                )
            report = stdout.getvalue()

        self.assertIn(f"SKILL.md {len(built)}B", report)
        self.assertIn("profiles shared", report)

    def test_agent_lists_the_outputs_a_build_would_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = Path(directory) / "out"
            build_skills(root / "alpha", output, ["all"])
            built = sorted(
                (
                    path.relative_to(output / "alpha").as_posix(),
                    path.stat().st_size,
                )
                for path in (output / "alpha").rglob("*")
                if path.is_file()
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "agent",
                        str(root / "alpha"),
                        "--only",
                        "outputs",
                        "--profile",
                        "all",
                    ]
                )
            rows = [
                line.split()
                for line in stdout.getvalue().splitlines()
                if line.startswith("  ")
            ]

        claimed = sorted((row[0], int(row[1].removesuffix("B"))) for row in rows)
        modes = {row[0]: row[2] for row in rows}
        self.assertEqual(built, claimed)
        self.assertEqual("755", modes["scripts/greet.py"])
        self.assertEqual("644", modes["SKILL.md"])

    def test_agent_rejects_an_unknown_dimension(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["agent", str(FIXTURES / "alpha"), "--only", "bogus"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("invalid dimension: bogus", stderr.getvalue())

    def test_agent_reports_diagnostics_with_a_code_and_a_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
            data["priority"] = "high"
            entry.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["agent", str(root / "alpha")])

        report = stdout.getvalue()
        self.assertEqual(1, code)
        self.assertIn(
            "error entries/rule-one.yaml entry.invalid-type "
            "priority must be an integer",
            report,
        )
        self.assertIn("1 skill, 1 error,", report)

    def test_agent_exits_with_status_one_when_a_section_hides_the_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["primary_workflow"] = "alpha.missing"
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["agent", str(root / "alpha"), "--only", "entries"])

        self.assertEqual(1, code)
        self.assertNotIn("error ", stdout.getvalue())
