"""The agent command and the sections it measures."""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.cli import main

from tests.support import CANONICAL_EXAMPLE, FIXTURES, copy_skills


PLACEHOLDER = re.compile(r"<[^>]+>")


def agent_help() -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.suppress(SystemExit):
            main(["agent", "-h"])
    return stdout.getvalue()


def legend_row_shapes(legend: str) -> dict[str, str]:
    """Each section's row shape, read out of the legend the command prints."""
    shapes: dict[str, str] = {}
    for line in legend.splitlines():
        label, separator, shape = line.partition(" rows: ")
        if separator:
            for name in label.split()[0].split("|"):
                shapes[name] = shape.strip()
    return shapes


def legend_summary_shape(legend: str) -> str:
    """The shape the legend gives for the line that closes a report."""
    for line in legend.splitlines():
        if line.strip().startswith("<n> skill"):
            return line.strip()
    raise AssertionError("the legend gives no summary shape")


def shape_pattern(shape: str) -> str:
    """Compile a legend shape into the pattern the line it describes must match.

    A placeholder stands for one whitespace-free field and `<n>` for a number,
    `(s)` for an optional plural, and `|` for alternatives. Everything else is
    literal, so a shape that drifts from what the renderer writes stops matching
    and the legend fails with it.
    """
    masked = PLACEHOLDER.sub(
        lambda match: "\x01" if match.group() == "<n>" else "\x02", shape
    )
    fields = []
    for field in masked.split():
        alternatives = [
            "s?".join(re.escape(part) for part in alternative.split("(s)"))
            .replace("\x01", r"\d+")
            .replace("\x02", r"\S+")
            for alternative in field.split("|")
        ]
        fields.append("(?:" + "|".join(alternatives) + ")")
    return "^" + r"\s+".join(fields) + "$"


def report_rows(*sources: str) -> tuple[dict[str, list[str]], str]:
    """The rows each section printed, keyed by section label, and the summary."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        main(["agent", *sources, "--all"])
    lines = [line for line in stdout.getvalue().splitlines() if line]
    sections: dict[str, list[str]] = {}
    label = ""
    for line in lines[:-1]:
        if line.startswith(" "):
            sections.setdefault(label, []).append(line.strip())
        else:
            label = line.split()[0]
    return sections, lines[-1]


def with_an_unreached_workflow(root: Path) -> None:
    """Give one fixture skill a workflow no step reaches."""
    source = root / "gamma" / "workflows" / "run.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    (source.parent / "orphan.yaml").write_text(
        yaml.safe_dump(dict(data, id="gamma.orphan", title="Orphan"), sort_keys=False),
        encoding="utf-8",
    )


class AgentHelpTests(unittest.TestCase):
    """The help an agent reads before, or instead of, the reference page."""

    def test_help_presents_the_report_as_machine_readable_not_unstable(self):
        help_text = agent_help()

        self.assertIn("stable and meant to be relied on", help_text)
        self.assertNotIn("not stable", help_text)
        self.assertNotIn("unstable", help_text)
        # The readable and pass-or-fail alternatives stay named.
        self.assertIn("list for a readable summary", help_text)
        self.assertIn("validate for a pass or fail gate", help_text)

    def test_the_legend_states_what_a_size_and_a_path_mean(self):
        help_text = agent_help()

        self.assertIn("bytes of the generated Markdown", help_text)
        self.assertIn("relative to the root in the header", help_text)
        self.assertIn("text is SKILL.md without its frontmatter", help_text)

    def test_the_legend_gives_the_diagnostic_line_shape(self):
        self.assertIn(
            "error|warn <path>[:<line>] <code> <message>",
            agent_help(),
        )
        self.assertIn("- for a whole-skill finding", agent_help())

    def test_the_legend_covers_every_line_a_full_report_emits(self):
        legend = agent_help()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["agent", str(FIXTURES / "alpha"), "--all"])
        lines = [
            line
            for line in stdout.getvalue().splitlines()
            if line and not line.startswith(" ")
        ]

        # The summary closes the report; the legend names its shape rather than a
        # count, so it is checked separately from the labelled lines above it.
        summary, labelled = lines[-1], lines[:-1]
        self.assertRegex(summary, r"^\d+ skills?, \d+ errors?, \d+ warnings?$")
        self.assertRegex(summary, shape_pattern(legend_summary_shape(legend)))
        undocumented = [
            line.split()[0]
            for line in labelled
            if line.split()[0] not in legend
        ]
        self.assertEqual([], undocumented)

    def test_the_legend_row_shapes_match_the_rows_the_renderer_writes(self):
        # Section labels are one line up from the rows beneath them, and a shape
        # that drifts from the renderer is exactly what a label check misses.
        shapes = legend_row_shapes(agent_help())
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with_an_unreached_workflow(root)
            sections, _ = report_rows(str(root), str(CANONICAL_EXAMPLE))

        self.assertEqual(
            [], sorted(set(sections) - set(shapes)), "rows with no legend shape"
        )
        self.assertEqual(
            [], sorted(set(shapes) - set(sections)), "shapes no report exercised"
        )
        for label, rows in sections.items():
            with self.subTest(section=label):
                pattern = shape_pattern(shapes[label])
                for row in rows:
                    self.assertRegex(row, pattern)

    def test_the_workflow_row_names_all_three_reach_values(self):
        # A `<placeholder>` alternative matches any word, so the shape check above
        # passes whether or not the legend names the fixed values a reach field
        # can hold. Every one of them has to be spelled out, the primary workflow
        # most of all: it leads every report, so it is the value an agent meets
        # first, and the step id it stands beside makes it easy to leave unnamed.
        alternatives = legend_row_shapes(agent_help())["workflows"].split()[1]
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with_an_unreached_workflow(root)
            sections, _ = report_rows(str(root), str(CANONICAL_EXAMPLE))

        reached_by = {row.split()[1] for row in sections["workflows"]}
        step_ids = {
            value for value in reached_by if re.fullmatch(r"[\w-]+\.\d+", value)
        }
        self.assertTrue(step_ids, reached_by)
        self.assertEqual(
            reached_by - step_ids,
            {name for name in alternatives.split("|") if "<" not in name},
        )

    def test_the_summary_shape_admits_the_inflection_the_report_writes(self):
        pattern = shape_pattern(legend_summary_shape(agent_help()))
        _, one = report_rows(str(FIXTURES / "alpha"))
        _, several = report_rows(str(FIXTURES))

        self.assertEqual("1 skill, 0 errors, 0 warnings", one)
        self.assertTrue(several.startswith("3 skills, "), several)
        self.assertRegex(one, pattern)
        self.assertRegex(several, pattern)


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
