"""The command-line surface: the parser, each command's report, and exit status.

Report rows, summary lines, and help text are contract — a row's columns and
their order are as much an interface as the options are — so this file asserts
them exactly as they are written, which is the one place in the suite where a
literal is the expected value rather than a record of where a string lives.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from degardis.cli import main, parser
from degardis.model import CURRENT_FORMAT_VERSION
from degardis.validate import DEFAULT_INSPECT_DIMENSIONS, INSPECT_DIMENSIONS

from tests.support import (
    CANONICAL_EXAMPLE,
    FIXTURES,
    copy_skills,
    edit_workflow,
    edit_yaml,
)


COMMANDS = ("list", "validate", "build", "inspect", "explain")


def run(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(list(argv))
    return status, stdout.getvalue(), stderr.getvalue()


def help_text(*argv: str) -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.suppress(SystemExit):
            parser().parse_args([*argv, "--help"])
    return stdout.getvalue()


class ParserTests(unittest.TestCase):
    def test_the_command_set_is_the_one_the_format_defines(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.suppress(SystemExit):
                parser().parse_args(["--help"])
        text = stdout.getvalue()
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)

    def test_a_command_is_required(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args([])
        self.assertEqual(2, raised.exception.code)

    def test_help_works_on_either_side_of_the_command_name(self):
        before = io.StringIO()
        after = io.StringIO()
        for stream, argv in ((before, ["-h", "build"]), (after, ["build", "-h"])):
            with contextlib.redirect_stdout(stream):
                with contextlib.suppress(SystemExit):
                    main(argv)
        self.assertEqual(after.getvalue(), before.getvalue())
        self.assertNotEqual("", after.getvalue())

    def test_every_help_text_naming_the_format_reads_the_current_version(self):
        """The version each help states and the version `validate` accepts are
        one fact, so neither can drift from the other."""
        for argv in ([], ["validate"], ["inspect"]):
            with self.subTest(argv=argv or ["degardis"]):
                text = help_text(*argv)
                self.assertIn(f"format {CURRENT_FORMAT_VERSION}", text)

    def test_the_inspect_help_names_every_dimension(self):
        text = help_text("inspect")
        for dimension in INSPECT_DIMENSIONS:
            with self.subTest(dimension=dimension):
                self.assertIn(dimension, text)
        for default in DEFAULT_INSPECT_DIMENSIONS:
            self.assertIn(default, text)

    def test_the_inspect_help_names_the_commands_an_agent_needs_next(self):
        text = help_text("inspect")
        for command in ("degardis explain", "degardis validate", "degardis build"):
            with self.subTest(command=command):
                self.assertIn(command, text)

    def test_an_unknown_dimension_is_refused_with_the_choices(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parser().parse_args(["inspect", "x", "--only", "nonsense"])
        report = stderr.getvalue()
        self.assertIn("invalid dimension", report)
        self.assertIn("diagnostics", report)

    def test_build_requires_an_output_directory(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["build", "some-skill"])
        self.assertEqual(2, raised.exception.code)
        self.assertIn("--output", stderr.getvalue())


class ListTests(unittest.TestCase):
    def test_list_reports_identity_constructs_profiles_and_source(self):
        status, report, _ = run("list", str(FIXTURES))
        self.assertEqual(0, status)
        self.assertIn("Skills (2)", report)
        self.assertIn("Alpha (alpha)  v1.2.3", report)
        for label in (
            "Description",
            "Workflow",
            "Constructs",
            "Profiles",
            "Scripts",
            "License",
            "Copyright",
            "Source",
        ):
            with self.subTest(label=label):
                self.assertIn(label, report)
        self.assertIn("thorough", report)

    def test_list_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            before = sorted(path.name for path in root.rglob("*"))
            run("list", str(root))
            self.assertEqual(before, sorted(path.name for path in root.rglob("*")))


class ValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_a_clean_source_passes_and_says_what_a_pass_does_not_establish(self):
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(0, status)
        self.assertIn("[PASS] Alpha (alpha)", report)
        self.assertIn("Summary: 2 passed, 0 failed, 0 errors, 0 warnings, 2 total.", report)
        self.assertIn("not that the skill guides an agent well", report)

    def test_a_failing_source_is_numbered_and_carries_its_check_code(self):
        with edit_workflow(self.root, "alpha", "run") as data:
            data["entry"] = "absent"
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(1, status)
        self.assertIn("[FAIL] Alpha (alpha)", report)
        self.assertIn("1. ", report)
        self.assertIn("(workflow.invalid-edge)", report)
        self.assertIn("degardis explain CODE", report)

    def test_a_warning_does_not_fail_the_run(self):
        with edit_yaml(self.root / "alpha" / "rules" / "name-the-gap.yaml") as data:
            data["match"] = {"outcomes": ["never-returned"]}
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(0, status)
        self.assertIn("Warning: ", report)
        self.assertIn("(rule.unmatched)", report)

    def test_fail_on_warning_promotes_and_says_how_many_it_moved(self):
        with edit_yaml(self.root / "alpha" / "rules" / "name-the-gap.yaml") as data:
            data["match"] = {"outcomes": ["never-returned"]}
        status, report, _ = run("validate", str(self.root), "--fail-on-warning")
        self.assertEqual(1, status)
        self.assertIn("--fail-on-warning reported 1 warning as an error", report)
        self.assertIn("the sources still build", report)


class InspectTests(unittest.TestCase):
    def test_the_default_dimensions_are_reported(self):
        status, report, _ = run("inspect", str(FIXTURES / "alpha"))
        self.assertEqual(0, status)
        self.assertIn("skill alpha 1.2.3", report)
        self.assertIn("workflows 2", report)
        self.assertIn("diagnostics 0", report)
        self.assertIn("links execution 0", report)

    def test_only_selects_dimensions_without_changing_the_checks(self):
        _, narrow, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "diagnostics")
        _, wide, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        self.assertNotIn("workflows 2", narrow)
        self.assertIn("workflows 2", wide)
        for report in (narrow, wide):
            self.assertIn("1 skill, 0 errors, 0 warnings", report)

    def test_dimensions_combine_by_repetition_and_by_comma(self):
        _, comma, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "rules,policies"
        )
        _, repeated, _ = run(
            "inspect",
            str(FIXTURES / "alpha"),
            "--only",
            "rules",
            "--only",
            "policies",
        )
        self.assertEqual(comma, repeated)
        # Equal reports prove the two spellings agree, not that either selected
        # what was asked for, so the selection itself is asserted as well.
        self.assertIn("rules ", comma)
        self.assertIn("policies ", comma)
        self.assertNotIn("protocols ", comma)

    def test_all_reports_every_dimension(self):
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        for heading in (
            "sources ",
            "workflows ",
            "execution ",
            "lowering ",
            "policies ",
            "rules ",
            "protocols ",
            "patterns ",
            "heuristics ",
            "guidance ",
            "profiles ",
            "outputs ",
            "diagnostics ",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, report)

    def test_a_profile_row_states_its_description_or_none(self):
        """The description is the only field an author may leave out, so the row
        says which of the two it is rather than printing an empty value."""
        _, described, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "profiles"
        )
        self.assertIn('quick "Quick"', described)
        self.assertIn(
            "description=Apply where a partial answer now is worth more than a "
            "whole answer later.",
            described,
        )
        self.assertIn('thorough "Thorough"', described)
        self.assertIn("description=none", described)

    def test_a_profile_row_counts_what_it_contributes(self):
        """The counts name the fields the schema declares, so the row and the
        source use one vocabulary: `points` for the prose, `guides` for files."""
        _, described, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "profiles"
        )
        self.assertIn("points=2 | guides=1", described)

    def test_body_text_appends_the_generated_document(self):
        _, report, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "diagnostics", "--body-text"
        )
        self.assertIn("=== alpha", report)
        self.assertIn("  ## Execution contract", report)

    def test_attention_reports_worst_execution_path_bytes_and_loads(self):
        from tests.support import compiled
        from tests.test_planning import branching_skill, loaded_cost

        with tempfile.TemporaryDirectory() as directory:
            path = branching_skill(Path(directory), calls=True)
            _, result, _ = compiled(path)
            worst, loads, _, _ = loaded_cost(result)
            status, report, _ = run("inspect", str(path), "--only", "attention")
        self.assertEqual(0, status)
        self.assertIn(f"path  worst {worst}B | loads {loads}", report)

    def test_the_exit_status_gates_on_errors_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with edit_workflow(root, "alpha", "run") as data:
                data["entry"] = "absent"
            status, report, _ = run(
                "inspect", str(root / "alpha"), "--only", "diagnostics"
            )
        self.assertEqual(1, status)
        self.assertIn("workflow.invalid-edge", report)

    def test_inspect_and_validate_report_the_same_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with edit_workflow(root, "alpha", "run") as data:
                data["steps"]["report"]["next"] = "absent"
            _, inspected, _ = run(
                "inspect", str(root / "alpha"), "--only", "diagnostics"
            )
            _, validated, _ = run("validate", str(root / "alpha"))
        self.assertIn("workflow.invalid-edge", inspected)
        self.assertIn("(workflow.invalid-edge)", validated)


class BuildCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def test_build_reports_each_artifact_and_a_summary(self):
        status, report, _ = run(
            "build", str(self.root), "--output", str(self.output)
        )
        self.assertEqual(0, status)
        self.assertIn("[BUILT] Alpha (alpha)", report)
        self.assertIn("Artifact", report)
        self.assertIn("Summary: 2 skills built as folders, 0 warnings.", report)

    def test_build_writes_an_archive_when_asked(self):
        status, report, _ = run(
            "build", str(self.root), "--output", str(self.output), "--zip"
        )
        self.assertEqual(0, status)
        self.assertIn("built as archives", report)
        self.assertTrue((self.output / "alpha.zip").is_file())

    def test_a_failing_source_stops_the_build_before_anything_is_written(self):
        with edit_workflow(self.root, "alpha", "run") as data:
            data["entry"] = "absent"
        status, _, errors = run(
            "build", str(self.root), "--output", str(self.output)
        )
        self.assertEqual(1, status)
        self.assertIn("workflow.invalid-edge", errors)
        self.assertFalse(self.output.exists())

    def test_an_output_overlapping_a_source_is_refused(self):
        status, _, errors = run(
            "build", str(self.root), "--output", str(self.root / "alpha" / "out")
        )
        self.assertEqual(1, status)
        self.assertIn("output.source-overlap", errors)

    def test_the_example_builds_from_the_repository(self):
        status, _, _ = run(
            "build", str(CANONICAL_EXAMPLE), "--output", str(self.output)
        )
        self.assertEqual(0, status)
        self.assertTrue((self.output / "structured-summary" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
