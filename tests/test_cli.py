"""The command-line surface: the parser, each command's report, and exit status.

Report rows and summary lines are contract — a row's columns and their order are
as much an interface as the options are — so this file asserts them exactly as
they are written, which is the one place in the suite where a literal is the
expected value rather than a record of where a string lives. Help text is not
asserted: its prose carries no behavior a rewording could break.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from degardis.bundlepaths import ROOT, task_path as task_page
from degardis.cli import main, parser
from degardis.render import (
    PRINCIPLE_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
)
from degardis.validate import inspect_skills

from tests.support import (
    CANONICAL_EXAMPLE,
    FIXTURES,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    folder_text,
    task_path,
    write_source,
)


COMMANDS = (
    "init",
    "list",
    "validate",
    "build",
    "inspect",
    "explain",
    "manual",
)


def run(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(list(argv))
    return status, stdout.getvalue(), stderr.getvalue()


def page_dump(report: str, name: str, page: str) -> str:
    """The text one `=== NAME PAGE` block carries, with its indent taken off.

    Every dumped line carries the two spaces, so the block ends at the first
    line that does not: the blank line before the next block, or the end of the
    report.
    """
    lines = report.splitlines()
    body = []
    for line in lines[lines.index(f"=== {name} {page}") + 1 :]:
        if not line.startswith("  "):
            break
        body.append(line[2:])
    return "\n".join(body) + "\n"


class ParserTests(unittest.TestCase):
    def test_every_command_the_format_defines_is_accepted(self):
        for command in COMMANDS:
            with self.subTest(command=command):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main([command, "-h"])
                self.assertEqual(0, raised.exception.code)

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


class InitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_init_writes_a_source_that_validates_as_it_stands(self):
        status, report, _ = run("init", "trial", "--output", str(self.root))
        self.assertEqual(0, status)
        self.assertIn("Created", report)
        self.assertEqual(0, run("validate", str(self.root / "trial"))[0])

    def test_init_writes_no_explicit_id(self):
        """The starter teaches the rule the readers enforce."""
        run("init", "trial", "--output", str(self.root))
        text = (self.root / "trial" / "tasks" / "primary.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("\nid:", text)

    def test_init_creates_the_directories_the_format_uses_without_selecting_them(self):
        """An empty directory the manifest selected would be a pattern matching
        nothing, and a first run that fails teaches the wrong thing."""
        run("init", "trial", "--output", str(self.root))
        for name in (
            "principles",
            "knowledge",
        ):
            with self.subTest(name=name):
                self.assertTrue((self.root / "trial" / name).is_dir())
        manifest = (self.root / "trial" / "skill.yaml").read_text(encoding="utf-8")
        self.assertNotIn("\n  knowledge:", manifest)
        self.assertNotIn("\n  principles:", manifest)

    def test_init_writes_no_principle_and_names_none(self):
        """A principle is the author's to write, so the starter writes none —
        and a task naming one that does not exist would not compile."""
        run("init", "trial", "--output", str(self.root))
        self.assertEqual([], sorted((self.root / "trial" / "principles").iterdir()))
        task = (self.root / "trial" / "tasks" / "primary.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("\nprinciples:", task.split("---")[1])

    def test_init_refuses_to_write_over_an_existing_directory(self):
        (self.root / "trial").mkdir()
        status, _, errors = run("init", "trial", "--output", str(self.root))
        self.assertEqual(1, status)
        self.assertIn("already exists", errors)

    def test_init_refuses_a_name_that_is_not_a_skill_name(self):
        status, _, errors = run("init", "Trial_Skill", "--output", str(self.root))
        self.assertEqual(1, status)
        self.assertIn("manifest.invalid-name", errors)


class ListTests(unittest.TestCase):
    def test_list_reports_identity_tasks_profiles_and_source(self):
        status, report, _ = run("list", str(FIXTURES))
        self.assertEqual(0, status)
        self.assertIn("Skills (2)", report)
        self.assertIn("Alpha (alpha)  v1.0.0", report)
        for label in (
            "Description",
            "Tasks",
            "Sources",
            "Profiles",
            "Scripts",
            "License",
            "Copyright",
            "Source",
        ):
            with self.subTest(label=label):
                self.assertIn(label, report)
        self.assertIn("review, repair, document", report)
        self.assertIn("legacy, python, urgent", report)

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
        self.assertIn(
            "Summary: 2 passed, 0 failed, 0 errors, 0 warnings, 2 total.", report
        )
        self.assertIn("not that the skill guides an agent well", report)

    def test_a_failing_source_is_numbered_and_carries_its_check_code(self):
        with edit_frontmatter(task_path(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(1, status)
        self.assertIn("[FAIL] Alpha (alpha)", report)
        self.assertIn("1. ", report)
        self.assertIn("(task.unknown-knowledge)", report)
        self.assertIn("degardis explain CODE", report)

    def test_a_warning_does_not_fail_the_run(self):
        write_source(
            self.root / "alpha" / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(0, status)
        self.assertIn("Warning: ", report)
        self.assertIn("(knowledge.orphan)", report)

    def test_fail_on_warning_promotes_and_says_how_many_it_moved(self):
        write_source(
            self.root / "alpha" / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
        status, report, _ = run("validate", str(self.root), "--fail-on-warning")
        self.assertEqual(1, status)
        self.assertIn("--fail-on-warning reported 1 warning as an error", report)
        self.assertIn("the sources still build", report)


class InspectTests(unittest.TestCase):
    def test_the_default_dimensions_are_reported(self):
        status, report, _ = run("inspect", str(FIXTURES / "alpha"))
        self.assertEqual(0, status)
        self.assertIn("skill alpha 1.0.0", report)
        self.assertIn("tasks 3", report)
        self.assertIn("principles 5", report)
        self.assertIn("diagnostics 0", report)

    def test_the_size_row_states_each_page_against_its_budget(self):
        result = inspect_skills([FIXTURES / "alpha"])[0]
        attention = result["attention"]
        _, report, _ = run("inspect", str(FIXTURES / "alpha"))
        self.assertIn("size  SKILL.md ", report)
        self.assertIn(f"B/{ROOT_BUDGET_BYTES}B", report)
        self.assertIn("task pages 3", report)
        self.assertIn(
            f"principles {attention['principle_bytes']}B max "
            f"{attention['largest_principle_bytes']}B/{PRINCIPLE_BUDGET_BYTES}B",
            report,
        )
        self.assertIn(
            f"guides {attention['guide_bytes']}B max "
            f"{attention['largest_guide_bytes']}B/"
            f"{GUIDE_BUDGET_BYTES}B",
            report,
        )

    def test_the_size_row_separates_principle_and_profile_pages(self):
        result = inspect_skills([FIXTURES / "alpha"])[0]
        sizes = {row["path"]: row["bytes"] for row in result["outputs"]}
        principles = sum(
            size
            for path, size in sizes.items()
            if path.startswith("references/principles/")
        )
        profiles = sum(
            size
            for path, size in sizes.items()
            if path.startswith("references/profiles/")
        )

        _, report, _ = run("inspect", str(FIXTURES / "alpha"))

        self.assertIn(f"| principles {principles}B", report)
        self.assertIn(f"| profiles {profiles}B", report)

    def test_quality_reports_the_load_each_task_requires_and_budget_headroom(self):
        result = inspect_skills([FIXTURES / "alpha"])[0]
        quality = result["quality"]
        attention = result["attention"]
        expected_reads = {
            task["id"]: attention["root_bytes"] + task["bytes"]
            for task in result["tasks"]
        }
        expected_headroom = min(
            attention["root_budget"] - attention["root_bytes"],
            *(
                attention["task_budget"] - task["bytes"]
                for task in result["tasks"]
            ),
        )

        self.assertEqual(attention["root_bytes"], quality["startup_bytes"])
        self.assertEqual(expected_reads, quality["minimum_read_bytes_by_task"])
        self.assertEqual(expected_headroom, quality["headroom"])

        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "quality")
        self.assertIn(f"startup_bytes {quality['startup_bytes']}B", report)
        self.assertIn(f"headroom {quality['headroom']}B", report)
        for task, read_bytes in expected_reads.items():
            self.assertIn(
                f"minimum_read_bytes_by_task {task} {read_bytes}B", report
            )

    def test_only_selects_dimensions_without_changing_the_checks(self):
        _, narrow, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "diagnostics")
        _, wide, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        self.assertNotIn("composition 3", narrow)
        self.assertIn("composition 3", wide)
        for report in (narrow, wide):
            self.assertIn("1 skill, 0 errors, 0 warnings", report)

    def test_dimensions_combine_by_repetition_and_by_comma(self):
        _, comma, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "knowledge,profiles"
        )
        _, repeated, _ = run(
            "inspect",
            str(FIXTURES / "alpha"),
            "--only",
            "knowledge",
            "--only",
            "profiles",
        )
        self.assertEqual(comma, repeated)
        # Equal reports prove the two spellings agree, not that either selected
        # what was asked for, so the selection itself is asserted as well.
        self.assertIn("knowledge 5", comma)
        self.assertIn("profiles 3", comma)
        self.assertNotIn("composition 3", comma)

    def test_the_guides_dimension_reports_each_guide_condition(self):
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "guides")
        self.assertIn("guides 1", report)
        self.assertIn("checklist", report)
        self.assertIn("guides/checklist.md", report)
        self.assertIn("when the change touches a published interface -> review", report)

    def test_all_reports_every_dimension(self):
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        for heading in (
            "sources ",
            "tasks ",
            "knowledge ",
            "principles ",
            "profiles ",
            "guides ",
            "composition ",
            "quality",
            "outputs ",
            "diagnostics ",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, report)

    def test_composition_answers_why_a_page_carries_what_it_carries(self):
        _, report, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "composition"
        )
        self.assertIn("review -> references/tasks/review.md", report)
        self.assertIn("  direct      evidence-required, order-findings, house-limits", report)
        self.assertIn("  required    change-surface", report)
        self.assertIn("  concept     change-surface", report)
        self.assertIn("  fact        house-limits", report)
        self.assertIn("  constraint  evidence-required", report)
        self.assertIn("  guidance    order-findings", report)

    def test_a_profile_row_states_its_description_or_a_dash(self):
        """The description is a field an author may leave out, so the row says
        which of the two it is rather than printing an empty value."""
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "profiles")
        self.assertIn("Python language and ecosystem guidance.", report)
        self.assertIn('legacy "Legacy code" Language 124B -', report)

    def test_the_principles_dimension_shows_where_each_one_is_stated(self):
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "principles")
        self.assertIn("-> SKILL.md", report)
        self.assertIn("page=references/principles/evidence.md", report)

    def test_page_appends_the_text_a_build_would_write_to_that_page(self):
        """The root and a task page are read the same way, from the same option.

        An agent asks for a page here instead of building one, so text that
        differed from the built file would send it to work from something the
        bundle never ships.
        """
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            run("build", str(FIXTURES / "alpha"), "--output", str(output))
            for page in (ROOT, task_page("review")):
                with self.subTest(page=page):
                    status, report, _ = run(
                        "inspect",
                        str(FIXTURES / "alpha"),
                        "--only",
                        "diagnostics",
                        "--page",
                        page,
                    )
                    self.assertEqual(0, status)
                    self.assertEqual(
                        folder_text(output / "alpha", page),
                        page_dump(report, "alpha", page),
                    )

    def test_pages_combine_by_repetition_and_by_comma(self):
        _, report, _ = run(
            "inspect",
            str(FIXTURES / "alpha"),
            "--only",
            "diagnostics",
            "--page",
            f"{ROOT},{task_page('review')}",
            "--page",
            task_page("repair"),
        )
        for page in (ROOT, task_page("review"), task_page("repair")):
            with self.subTest(page=page):
                self.assertIn(f"=== alpha {page}", report)

    def test_a_page_no_skill_generates_is_refused_with_the_pages_that_exist(self):
        """A path an agent guessed wrong has to say so and say what is there.

        Printing nothing for it would read as a page that compiles to nothing,
        which is the one answer the bundle can never give.
        """
        status, report, errors = run(
            "inspect",
            str(FIXTURES / "alpha"),
            "--only",
            "diagnostics",
            "--page",
            task_page("nowhere"),
        )
        self.assertEqual(1, status)
        self.assertIn(f"=== alpha {task_page('nowhere')} unavailable", report)
        self.assertIn(task_page("review"), errors)

    def test_page_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            before = sorted(path.name for path in root.rglob("*"))
            run("inspect", str(root / "alpha"), "--page", ROOT)
            self.assertEqual(before, sorted(path.name for path in root.rglob("*")))

    def test_the_exit_status_gates_on_errors_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with edit_frontmatter(task_path(root, "alpha", "review")) as fields:
                fields["knowledge"] = ["nowhere"]
            status, report, _ = run(
                "inspect", str(root / "alpha"), "--only", "diagnostics"
            )
        self.assertEqual(1, status)
        self.assertIn("task.unknown-knowledge", report)

    def test_inspect_and_validate_report_the_same_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            from tests.support import edit_yaml

            with edit_yaml(root / "alpha" / "skill.yaml") as fields:
                fields["principles"].append("clear-reporting")
            _, inspected, _ = run(
                "inspect", str(root / "alpha"), "--only", "diagnostics"
            )
            _, validated, _ = run("validate", str(root / "alpha"))
        self.assertIn("manifest.unknown-principle", inspected)
        self.assertIn("(manifest.unknown-principle)", validated)


class BuildCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def test_build_reports_each_artifact_and_a_summary(self):
        status, report, _ = run("build", str(self.root), "--output", str(self.output))
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
        with edit_frontmatter(task_path(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        status, _, errors = run("build", str(self.root), "--output", str(self.output))
        self.assertEqual(1, status)
        self.assertIn("task.unknown-knowledge", errors)
        self.assertFalse(self.output.exists())

    def test_an_output_overlapping_a_source_is_refused(self):
        status, _, errors = run(
            "build", str(self.root), "--output", str(self.root / "alpha" / "out")
        )
        self.assertEqual(1, status)
        self.assertIn("output.source-overlap", errors)

    def test_the_example_builds_from_the_repository(self):
        status, _, _ = run("build", str(CANONICAL_EXAMPLE), "--output", str(self.output))
        self.assertEqual(0, status)
        self.assertTrue((self.output / "structured-summary" / "SKILL.md").is_file())

    def test_a_manifest_that_cannot_be_read_is_reported_with_its_code(self):
        with edit_yaml(self.root / "beta" / "skill.yaml") as data:
            data["version"] = None
        status, report, _ = run("validate", str(self.root / "beta"))
        self.assertEqual(1, status)
        self.assertIn("manifest.invalid-version", report)


if __name__ == "__main__":
    unittest.main()
