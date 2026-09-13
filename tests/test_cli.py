"""The command-line surface: the parser, each command's report, and exit status.

Report rows and summary lines are contract — a row's columns and their order are
as much an interface as the options are — so this file asserts them exactly as
they are written, which is the one place in the suite where a literal is the
expected value rather than a record of where a string lives. Help text is not
asserted: its prose carries no behavior a rewording could break.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import posixpath
import re
import tempfile
import unittest
from pathlib import Path

from degardis.build import build_skills
from degardis.bundlepaths import (
    FACET_INDEX,
    FACETS_DIRECTORY,
    GUIDES_DIRECTORY,
    PRINCIPLES_DIRECTORY,
    REGISTER,
    ROOT,
    TASKS_DIRECTORY,
    task_path as task_page,
)
from degardis.cli import main, parser
from degardis.registry import load_skill_path
from degardis.inspection import INSPECT_DIMENSIONS
from degardis.markdown import EXTERNAL_TARGET, link_destinations
from degardis.output import _INSPECT_WRITERS as INSPECT_WRITERS
from degardis.render import (
    FACET_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    PRINCIPLE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
)

from tests.support import (
    FIXTURES,
    copy_skills,
    edit_frontmatter,
    field_of,
    folder_names,
    folder_text,
    run,
    task_path,
    tree_bytes,
    visible,
    words,
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


# The alpha fixture's tasks, in its manifest's routing order.
ALPHA_TASKS = ("review", "repair", "document")


def line_of(report: str, prefix: str) -> str:
    """The one report line that starts with `prefix`, failing unless there is one."""
    found = [line for line in report.splitlines() if line.startswith(prefix)]
    if len(found) != 1:
        raise AssertionError(f"expected one line starting {prefix!r}, found {found}")
    return found[0]


def block(report: str, heading: str) -> list[str]:
    """The rows under one dimension heading, up to the blank line that ends them."""
    lines = report.splitlines()
    start = lines.index(heading) + 1
    end = lines.index("", start) if "" in lines[start:] else len(lines)
    return lines[start:end]


def row(report: str, heading: str, identifier: str) -> list[str]:
    """One row of a dimension block, split into its whitespace-separated fields."""
    return next(
        line.split()
        for line in block(report, heading)
        if line.split()[0] == identifier
    )


def with_orphan_and_missing_reference(root: Path) -> None:
    """Give the alpha copy one error and one warning, each with its own code."""
    with edit_frontmatter(task_path(root, "alpha", "document")) as fields:
        fields["knowledge"] = ["nowhere"]
    write_source(
        root / "alpha" / "knowledge" / "unused.md",
        "kind: fact\ntitle: Unused",
        "Reached by nothing.",
    )


def read_rows(report: str, measure: str) -> dict[str, int]:
    """One per-task quality measure as a mapping of task id to bytes."""
    rows: dict[str, int] = {}
    for line in report.splitlines():
        name, _, rest = line.strip().partition(" ")
        if name == measure:
            task, size = rest.split()
            rows[task] = int(size.removesuffix("B"))
    return rows


def reachable_pages(artifact: Path, source: Path, task: str) -> set[str]:
    """Every generated page a run of one task can be sent to, read off the build.

    A copied file keeps the address it has in the source, which is how it is
    told apart from a generated page here.
    """
    shipped = folder_names(artifact)
    own = task_page(task)
    pending = [ROOT, REGISTER, FACET_INDEX, own]
    reached: set[str] = set()
    while pending:
        page = pending.pop()
        if page in reached or page not in shipped or (source / page).is_file():
            continue
        if page.startswith(TASKS_DIRECTORY + "/") and page != own:
            continue
        reached.add(page)
        here = posixpath.dirname(page)
        for target in link_destinations(folder_text(artifact, page)):
            if not EXTERNAL_TARGET.match(target):
                address = posixpath.join(here, target.partition("#")[0])
                pending.append(posixpath.normpath(address))
    return reached


class ParserTests(unittest.TestCase):
    def test_the_commands_are_exactly_the_ones_the_cli_documents(self):
        """A closed set: a command left over from an earlier format, such as a
        verb of its own for principles, would read as a construct that is a
        special case, and nothing else would notice it was still there."""
        subcommands = next(
            action
            for action in parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(sorted(COMMANDS), sorted(subcommands.choices))

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
        """Every command, because an agent types the option where it thinks of
        it and a command that answers only one order sends it to read the
        parser's error instead of the help it asked for."""
        for command in COMMANDS:
            with self.subTest(command=command):
                before = io.StringIO()
                after = io.StringIO()
                for stream, argv in (
                    (before, ["-h", command]),
                    (after, [command, "-h"]),
                ):
                    with contextlib.redirect_stdout(stream):
                        with contextlib.suppress(SystemExit):
                            main(argv)
                self.assertEqual(after.getvalue(), before.getvalue())
                self.assertNotEqual("", after.getvalue())

    def test_help_prose_wraps_at_the_terminal_width_and_commands_do_not(self):
        """Descriptions and epilogs are hard-wrapped in the source, so printed as
        written they break again wherever a narrower terminal's edge falls. Every
        line fits the help's width except an example command, which is kept
        whole because a command broken across lines is one a reader cannot copy.
        """
        width = 60 - 2  # argparse leaves two columns of margin
        for command in COMMANDS:
            with self.subTest(command=command):
                _, wide, _ = run(command, "-h", columns=200)
                _, narrow, _ = run(command, "-h", columns=60)
                for line in visible(narrow).splitlines():
                    if not line.startswith("  degardis "):
                        self.assertLessEqual(len(line), width, line)
                self.assertEqual(words(wide), words(narrow))

    def test_a_help_list_row_wraps_under_its_own_text(self):
        """A continuation that returned to the margin would read as the next row."""
        _, report, _ = run("inspect", "-h", columns=60)
        lines = visible(report).splitlines()
        rows = lines[lines.index("Dimensions:") + 1 :]
        rows = rows[: rows.index("")]
        column = rows[0].index(rows[0].split()[1])
        for line in rows:
            with self.subTest(line=line):
                if line[2] == " ":
                    self.assertEqual(" " * column, line[:column])
                    self.assertNotEqual(" ", line[column])
                else:
                    self.assertIn(line.split()[0], INSPECT_DIMENSIONS)
        self.assertGreater(len(rows), len(INSPECT_DIMENSIONS))

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


class _ConsoleWrapper(io.TextIOWrapper):
    """A byte stream that claims to be a terminal, in an encoding of its own."""

    def isatty(self) -> bool:
        return True


class OutputEncodingTests(unittest.TestCase):
    """Redirected output is UTF-8 whatever encoding the host gave the stream.

    Python encodes a redirected stream in the locale's encoding, which on
    Windows is an ANSI code page, so each stream here starts in cp1252: the
    encoding that turned an em dash into a byte no UTF-8 reader can decode.
    The run prints a manual topic carrying em dashes to stdout, and names an
    unknown topic with a non-ASCII letter so an error reaches stderr as well.
    """

    ARGV = ("manual", "inspection", "naïve")

    def run_on(
        self, stdout: io.TextIOWrapper, stderr: io.TextIOWrapper
    ) -> tuple[bytes, bytes]:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(1, main(list(self.ARGV)))
        stdout.flush()
        stderr.flush()
        return stdout.buffer.getvalue(), stderr.buffer.getvalue()

    def test_redirected_output_is_utf8_on_both_streams(self):
        stdout, stderr = (
            io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="backslashreplace")
            for _ in range(2)
        )
        out, err = self.run_on(stdout, stderr)
        self.assertIn("—", out.decode("utf-8"))
        self.assertIn("naïve", err.decode("utf-8"))
        # Only the encoding changes; how the stream handles an unencodable
        # character is still what the host chose.
        self.assertEqual("backslashreplace", stdout.errors)

    def test_a_terminal_keeps_the_encoding_it_displays_in(self):
        """A terminal decodes what it is sent, so its encoding is left alone."""
        stdout, stderr = (
            _ConsoleWrapper(io.BytesIO(), encoding="cp1252") for _ in range(2)
        )
        out, err = self.run_on(stdout, stderr)
        self.assertIn("—".encode("cp1252"), out)
        self.assertIn("naïve".encode("cp1252"), err)


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

    def test_init_names_the_created_skill_in_its_next_step(self):
        """The suggested command has to run from where init ran, wherever
        --output put the skill."""
        _, report, _ = run("init", "trial", "--output", str(self.root))
        hint = report.splitlines()[-1]
        shown = hint.split("degardis validate ", 1)[1].split(", then", 1)[0]
        self.assertEqual(
            (self.root / "trial").resolve(), Path(shown.strip('"')).resolve()
        )

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
        selected = load_skill_path(self.root / "trial").manifest["content"]
        self.assertEqual({"tasks"}, set(selected))
        for name in ("principles", "knowledge", "facets", "guides"):
            with self.subTest(name=name):
                self.assertTrue((self.root / "trial" / name).is_dir())

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
    def test_list_reports_identity_tasks_facets_and_source(self):
        status, report, _ = run("list", str(FIXTURES))
        self.assertEqual(0, status)
        lines = report.splitlines()
        self.assertEqual("Skills (2)", lines[0])
        heading = lines.index("Alpha (alpha)  v1.0.0")
        self.assertEqual(
            [
                "  Description Carry every construct kind this format defines, in one source.",
                "  Tasks       review, repair, document",
                "  Sources     3 tasks, 5 principles, 5 knowledge, 2 guides, 3 facets, "
                "1 scripts, 1 assets",
                "  Facets      legacy, python, urgent",
                "  Scripts     Yes",
                "  License     MIT",
                "  Copyright   Copyright (c) 2026 Alpha",
                f"  Source      {(FIXTURES / 'alpha').resolve()}",
            ],
            lines[heading + 1 : heading + 9],
        )

    def test_list_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            before = tree_bytes(root)
            run("list", str(root))
            self.assertEqual(before, tree_bytes(root))


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
        self.assertIn(
            "not that the skill guides an agent well", " ".join(report.split())
        )

    def test_a_failing_source_is_numbered_and_carries_its_check_code(self):
        with edit_frontmatter(task_path(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["nowhere"]
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(1, status)
        lines = report.splitlines()
        failed = lines.index("[FAIL] Alpha (alpha)")
        self.assertTrue(lines[failed + 1].startswith("       1. "))
        finding = " ".join(lines[failed + 1 : lines.index("[PASS] Beta (beta)")])
        self.assertTrue(finding.endswith("(task.unknown-knowledge)"), finding)
        self.assertIn(
            "Summary: 1 passed, 1 failed, 1 error, 0 warnings, 2 total.", lines
        )
        self.assertIn(
            "Run `degardis explain CODE [CODE ...]` for the checks behind the "
            "codes above.",
            lines,
        )

    def test_a_report_wraps_at_a_narrow_terminal_and_at_a_fixed_width_elsewhere(self):
        """A terminal narrower than the report gets its own width less one
        column; redirected output keeps the fixed width, so it is the same bytes
        whatever window it ran in. Wrapping moves line breaks and nothing else."""
        with edit_frontmatter(task_path(self.root, "alpha", "document")) as fields:
            fields["knowledge"] = ["nowhere"]
        _, piped, _ = run("validate", str(self.root))
        _, narrow, _ = run("validate", str(self.root), columns=60)
        _, wide, _ = run("validate", str(self.root), columns=300)
        self.assertEqual(piped, wide)
        self.assertEqual(words(piped), words(narrow))
        self.assertNotEqual(piped, narrow)
        for line in narrow.splitlines():
            # A path is never broken, so only a label and one word may overrun.
            if len(line) >= 60:
                self.assertLessEqual(len(line.split()), 2, line)

    def test_a_warning_does_not_fail_the_run(self):
        write_source(
            self.root / "alpha" / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
        status, report, _ = run("validate", str(self.root))
        self.assertEqual(0, status)
        lines = report.splitlines()
        self.assertIn("[PASS] Alpha (alpha)", lines)
        self.assertIn(
            "Summary: 2 passed, 0 failed, 0 errors, 1 warning, 2 total.", lines
        )
        self.assertIn("(knowledge.orphan)", report)

    def test_fail_on_warning_promotes_and_says_how_many_it_moved(self):
        write_source(
            self.root / "alpha" / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
        status, report, _ = run("validate", str(self.root), "--fail-on-warning")
        self.assertEqual(1, status)
        lines = report.splitlines()
        self.assertIn(
            "Summary: 1 passed, 1 failed, 1 error, 0 warnings, 2 total.", lines
        )
        self.assertIn(
            "--fail-on-warning reported 1 warning as an error; the sources still build.",
            lines,
        )

    def test_a_promoted_run_that_also_has_errors_does_not_say_the_sources_build(self):
        """The note separates what the caller's standard refused from what the
        checks refused, so it may only claim a build where nothing else failed."""
        with_orphan_and_missing_reference(self.root)
        status, report, _ = run("validate", str(self.root), "--fail-on-warning")
        self.assertEqual(1, status)
        self.assertIn("--fail-on-warning reported 1 warning as an error.", report.splitlines())


class InspectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        artifact = build_skills(FIXTURES / "alpha", Path(directory.name))[0]
        cls.built = {
            "sizes": {
                name: (artifact / name).stat().st_size
                for name in folder_names(artifact)
            },
            "root": folder_text(artifact, ROOT),
        }

    def sized(self, prefix: str) -> list[int]:
        """The built size of every file under one bundle directory."""
        return [
            size for path, size in self.built["sizes"].items() if path.startswith(prefix)
        ]

    def test_every_dimension_the_help_offers_writes_a_block_in_that_order(self):
        """The help's list and the report's blocks are one register, ordered.

        A name the help lists and no writer answers reports nothing at all:
        `--only` would accept it, the run would exit zero, and the agent that
        asked for it would read a report missing the one thing it asked about.
        The order is asserted with the membership because the two are read
        together — an agent comparing two reports reads the blocks in sequence,
        and the help is where it learned what that sequence is.

        `skill` is excluded because it is the header every run writes rather
        than a block a selection turns on.
        """
        self.assertEqual(
            [name for name in INSPECT_DIMENSIONS if name != "skill"],
            list(INSPECT_WRITERS),
        )

    def test_the_default_dimensions_are_reported(self):
        status, report, _ = run("inspect", str(FIXTURES / "alpha"))
        self.assertEqual(0, status)
        lines = report.splitlines()
        self.assertEqual('skill alpha 1.0.0 "Alpha"', lines[0])
        for heading in ("tasks 3", "principles 5", "diagnostics 0"):
            with self.subTest(heading=heading):
                self.assertIn(heading, lines)
        for heading in ("knowledge 5", "composition 3", "quality"):
            with self.subTest(absent=heading):
                self.assertNotIn(heading, lines)
        self.assertEqual("1 skill, 0 errors, 0 warnings", lines[-1])

    def test_the_size_row_states_each_page_class_against_its_budget(self):
        """Every figure is the size of a file a build writes, so each is taken
        from the built bundle rather than from the report being checked."""
        sizes = self.built["sizes"]
        tasks = self.sized(TASKS_DIRECTORY + "/")
        principles = self.sized(PRINCIPLES_DIRECTORY + "/")
        guides = self.sized(GUIDES_DIRECTORY + "/")
        facets = [
            size
            for path, size in sizes.items()
            if path.startswith(FACETS_DIRECTORY + "/") and path != FACET_INDEX
        ]
        expected = (
            f"size SKILL.md {sizes[ROOT]}B/{ROOT_BUDGET_BYTES}B"
            f" {len(self.built['root'].splitlines())} lines"
            f" | register {sizes[REGISTER]}B"
            f" | task pages {len(tasks)} {sum(tasks)}B"
            f" avg {round(sum(tasks) / len(tasks))}B"
            f" max {max(tasks)}B/{TASK_BUDGET_BYTES}B"
            f" | principles {sum(principles)}B"
            f" max {max(principles)}B/{PRINCIPLE_BUDGET_BYTES}B"
            f" | guides {sum(guides)}B max {max(guides)}B/{GUIDE_BUDGET_BYTES}B"
            f" | facets {sizes[FACET_INDEX] + sum(facets)}B"
            f" index {sizes[FACET_INDEX]}B max {max(facets)}B/{FACET_BUDGET_BYTES}B"
        )
        _, report, _ = run("inspect", str(FIXTURES / "alpha"))
        self.assertEqual(expected, line_of(report, "size "))

    def test_a_page_class_the_bundle_does_not_ship_is_sized_at_zero(self):
        """A starter skill has no principle, guide, or facet, so its bundle
        carries no register and no facet index; the row states their absence
        as zero rather than dropping the field an agent reads by position."""
        with tempfile.TemporaryDirectory() as directory:
            run("init", "trial", "--output", directory)
            _, report, _ = run("inspect", str(Path(directory) / "trial"))
        size = line_of(report, "size ")
        self.assertIn(" | register 0B | ", size)
        self.assertIn(" | facets 0B index 0B max 0B/", size)

    def test_quality_reports_the_minimum_read_of_each_task_and_budget_headroom(self):
        sizes = self.built["sizes"]
        expected_reads = {
            task: sizes[ROOT] + sizes[task_page(task)] for task in ALPHA_TASKS
        }
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "quality")
        self.assertEqual(
            f"startup_bytes {sizes[ROOT]}B | headroom {self.headroom(sizes)}B",
            line_of(report, "startup_bytes "),
        )
        self.assertEqual(
            expected_reads, read_rows(report, "minimum_read_bytes_by_task")
        )

    @staticmethod
    def headroom(sizes: dict[str, int]) -> int:
        """The tightest one-load margin, from the sizes of the files a build wrote.

        The facet index and the register are held to no budget, so they have no
        margin; a kind of page the bundle does not ship contributes none either.
        """
        budgets = {
            TASKS_DIRECTORY + "/": TASK_BUDGET_BYTES,
            PRINCIPLES_DIRECTORY + "/": PRINCIPLE_BUDGET_BYTES,
            GUIDES_DIRECTORY + "/": GUIDE_BUDGET_BYTES,
            FACETS_DIRECTORY + "/": FACET_BUDGET_BYTES,
        }
        return min(
            ROOT_BUDGET_BYTES - sizes[ROOT],
            *(
                budget - size
                for path, size in sizes.items()
                for prefix, budget in budgets.items()
                if path.startswith(prefix) and path != FACET_INDEX
            ),
        )

    def test_headroom_reaches_a_guide_page_nearer_its_budget_than_the_root(self):
        """Every page held to a one-load budget can be the tightest one. A guide
        grown close to its limit leaves less room than the root does, so it
        decides the figure, and past its limit the figure goes negative beside
        the warning that reports it."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            guide = root / "alpha" / "guides" / "checklist.md"
            for length, over in ((GUIDE_BUDGET_BYTES - 200, False), (GUIDE_BUDGET_BYTES, True)):
                with self.subTest(over_budget=over):
                    guide.write_text(
                        "---\ntitle: Checklist\n---\n\n" + "x" * length + "\n",
                        encoding="utf-8",
                    )
                    artifact = build_skills(root / "alpha", Path(directory) / "out")[0]
                    sizes = {
                        name: (artifact / name).stat().st_size
                        for name in folder_names(artifact)
                    }
                    guide_margin = GUIDE_BUDGET_BYTES - sizes[GUIDES_DIRECTORY + "/checklist.md"]
                    self.assertLess(guide_margin, ROOT_BUDGET_BYTES - sizes[ROOT])
                    _, report, _ = run("inspect", str(root / "alpha"), "--all")
                    self.assertEqual(
                        f"startup_bytes {sizes[ROOT]}B | headroom {guide_margin}B",
                        line_of(report, "startup_bytes "),
                    )
                    self.assertEqual(over, guide_margin < 0)
                    self.assertEqual(over, "render.guide-budget" in report)

    def test_headroom_ignores_a_kind_of_page_the_bundle_does_not_ship(self):
        """A starter skill ships no principle, guide, or facet page. Their 8 KiB
        budgets are smaller than the root's, so counting them as empty pages
        would report their whole budget as the tightest margin."""
        with tempfile.TemporaryDirectory() as directory:
            run("init", "trial", "--output", directory)
            skill = Path(directory) / "trial"
            artifact = build_skills(skill, Path(directory) / "out")[0]
            sizes = {
                name: (artifact / name).stat().st_size for name in folder_names(artifact)
            }
            _, report, _ = run("inspect", str(skill), "--only", "quality")
        expected = min(
            ROOT_BUDGET_BYTES - sizes[ROOT],
            TASK_BUDGET_BYTES - sizes[task_page("primary")],
        )
        self.assertGreater(expected, PRINCIPLE_BUDGET_BYTES)
        self.assertEqual(
            f"startup_bytes {sizes[ROOT]}B | headroom {expected}B",
            line_of(report, "startup_bytes "),
        )

    def test_quality_reports_the_maximum_read_of_each_task(self):
        """The ceiling is every generated page a run of one task can be sent to.

        The expected value walks the links of the built files, starting where
        the root sends every run: its own text, the register it has the run copy,
        the chosen task page, and the facet index. Copied files keep their source
        address and are not generated guidance, so they are left out. The guide
        is given a link to another task, because a run that followed it would
        have changed task, and that page must not count against this one.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            guide = root / "alpha" / "guides" / "checklist.md"
            guide.write_text(
                guide.read_text(encoding="utf-8") + "\nThen see [[task:repair]].\n",
                encoding="utf-8",
            )
            artifact = build_skills(root / "alpha", Path(directory) / "out")[0]
            self.assertIn(
                "(../tasks/repair.md)",
                folder_text(artifact, GUIDES_DIRECTORY + "/checklist.md"),
            )
            expected = {
                task: sum(
                    (artifact / page).stat().st_size
                    for page in reachable_pages(artifact, root / "alpha", task)
                )
                for task in ALPHA_TASKS
            }
            _, report, _ = run("inspect", str(root / "alpha"), "--only", "quality")
        self.assertEqual(expected, read_rows(report, "maximum_read_bytes_by_task"))

    def test_the_outputs_heading_states_the_file_count_and_total_bytes(self):
        sizes = self.built["sizes"]
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "outputs")
        self.assertEqual(
            f"outputs {len(sizes)} {sum(sizes.values())}B", line_of(report, "outputs ")
        )

    def test_a_manifest_that_cannot_be_read_reports_every_dimension_empty(self):
        """Nothing compiled, so every block is present and says so: an absent
        block would read as a dimension the report forgot, and a crash would
        leave the agent without the finding that explains the failure."""
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "broken"
            skill.mkdir()
            (skill / "skill.yaml").write_text("name: broken\n: [\n", encoding="utf-8")
            status, report, errors = run("inspect", str(skill), "--all")
        self.assertEqual(1, status)
        self.assertEqual("", errors)
        lines = report.splitlines()
        for heading in (
            "tasks none",
            "count none",
            "fmt -",
            "sources 0",
            "tasks 0",
            "knowledge 0",
            "principles 0",
            "guides 0",
            "facets 0",
            "scripts 0",
            "assets 0",
            "composition 0",
            "outputs 0 0B",
            "diagnostics 1",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, lines)

    def test_a_finding_whose_message_spans_lines_is_one_row(self):
        """The report is one fact per line. A parser message carries newlines of
        its own, and printed as it is, its tail would read as rows no dimension
        wrote."""
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "broken"
            skill.mkdir()
            (skill / "skill.yaml").write_text("name: broken\n: [\n", encoding="utf-8")
            _, report, _ = run("inspect", str(skill), "--only", "diagnostics")
        lines = report.splitlines()
        block = lines[lines.index("diagnostics 1") + 1 : lines.index("", lines.index("diagnostics 1"))]
        self.assertEqual(1, len(block))
        self.assertTrue(block[0].startswith("error source.invalid-yaml skill.yaml "))

    def test_only_selects_dimensions_without_changing_the_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with_orphan_and_missing_reference(root)
            narrow_status, narrow, _ = run(
                "inspect", str(root / "alpha"), "--only", "tasks"
            )
            wide_status, wide, _ = run("inspect", str(root / "alpha"), "--all")
        self.assertNotIn("composition 3", narrow.splitlines())
        self.assertIn("composition 3", wide.splitlines())
        for status, report in ((narrow_status, narrow), (wide_status, wide)):
            self.assertEqual(1, status)
            self.assertEqual("1 skill, 1 error, 1 warning", report.splitlines()[-1])

    def test_dimensions_combine_by_repetition_and_by_comma(self):
        _, comma, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "knowledge,facets"
        )
        _, repeated, _ = run(
            "inspect",
            str(FIXTURES / "alpha"),
            "--only",
            "knowledge",
            "--only",
            "facets",
        )
        self.assertEqual(comma, repeated)
        # Equal reports prove the two spellings agree, not that either selected
        # what was asked for, so the selection itself is asserted as well.
        lines = comma.splitlines()
        self.assertIn("knowledge 5", lines)
        self.assertIn("facets 3", lines)
        self.assertNotIn("composition 3", lines)

    def test_all_reports_every_dimension_in_the_documented_order(self):
        """Each block opens with its name, and `--all` prints them in the
        order the help lists them, whatever order the options named them in."""
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        openings = {
            "identity": "desc ",
            "quality": "quality",
        }
        lines = report.splitlines()
        positions = []
        for name in INSPECT_WRITERS:
            opening = openings.get(name)
            with self.subTest(dimension=name):
                if opening is None:
                    pattern = re.compile(rf"{name} \d+( \d+B)?")
                    found = [i for i, line in enumerate(lines) if pattern.fullmatch(line)]
                else:
                    found = [i for i, line in enumerate(lines) if line.startswith(opening)]
                self.assertEqual(1, len(found), found)
                positions.append(found[0])
        self.assertEqual(sorted(positions), positions)

    def test_the_guides_dimension_reports_each_guide_condition_and_owners(self):
        """Owners are qualified, so a guide only a facet names still reads as
        used: an unqualified id would leave it looking like one nothing opens."""
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "guides")
        self.assertEqual(2, len(block(report, "guides 2")))
        for guide, owners in (
            ("checklist", "task:review, facet:legacy"),
            ("toolchain", "facet:python"),
        ):
            source = FIXTURES / "alpha" / "guides" / f"{guide}.md"
            with self.subTest(guide=guide):
                line = " ".join(row(report, "guides 2", guide))
                self.assertTrue(line.startswith(f"{guide} guides/{guide}.md "), line)
                self.assertTrue(
                    line.endswith(
                        f"{field_of(source, 'activation')} -> {owners} linked=none"
                    ),
                    line,
                )

    def test_a_guide_states_its_activation_once(self):
        """A guide has one activation however many tasks and facets name it, so
        its owners are listed bare: repeating the condition beside each of them
        would restate it once per owner."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            for task, guides in (("review", ["checklist", "toolchain"]), ("repair", ["toolchain"])):
                with edit_frontmatter(task_path(root, "alpha", task)) as fields:
                    fields["guides"] = guides
            _, report, _ = run("inspect", str(root / "alpha"), "--only", "guides")
        source = FIXTURES / "alpha" / "guides" / "toolchain.md"
        self.assertEqual(
            f"{field_of(source, 'activation')} -> task:review, task:repair, "
            "facet:python linked=none",
            " ".join(row(report, "guides 2", "toolchain")[3:]),
        )

    def test_a_guide_row_names_each_page_whose_authored_text_links_it(self):
        """Owners are the pages that list a guide; `linked=` adds each page whose
        authored text links it, so which pages reach a guide is one row rather
        than a join of source text with the knowledge map. A link in knowledge
        lands on every task page carrying that unit."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            knowledge = root / "alpha" / "knowledge" / "evidence-required.md"
            checklist = root / "alpha" / "guides" / "checklist.md"
            for path, link in (
                (knowledge, "[[guide:toolchain]]"),
                (checklist, "the toolchain checks in [[guide:toolchain]]"),
            ):
                path.write_text(
                    path.read_text(encoding="utf-8") + f"\nSee {link}.\n",
                    encoding="utf-8",
                )
            _, report, _ = run("inspect", str(root / "alpha"), "--only", "guides")
        line = " ".join(row(report, "guides 2", "toolchain"))
        self.assertTrue(
            line.endswith(
                "-> facet:python linked=task:review, task:repair, guide:checklist"
            ),
            line,
        )

    def test_composition_answers_why_a_page_carries_what_it_carries(self):
        _, report, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "composition"
        )
        lines = block(report, "composition 3")
        start = lines.index("review -> references/tasks/review.md")
        self.assertEqual(
            [
                "  direct evidence-required, order-findings, house-limits",
                "  required change-surface",
                "  concept change-surface",
                "  fact house-limits",
                "  constraint evidence-required",
                "  guidance order-findings",
            ],
            lines[start + 1 : start + 7],
        )
        self.assertFalse(lines[start + 7].startswith("  "))

    def test_no_report_line_is_padded(self):
        """The report is read by an agent that pays for every space, and nothing
        in it lines up for a reader's eye: fields are one space apart, and only
        the indentation that nests a line under the one above it remains."""
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--all")
        for line in report.splitlines():
            with self.subTest(line=line):
                self.assertNotIn("  ", line.lstrip(" "))

    def test_the_scripts_and_assets_dimensions_name_the_pages_linking_each_file(self):
        """A script or asset is reached only through authored links, so its row
        is keyed by the target an inline reference names and says where the
        links to it land."""
        _, report, _ = run(
            "inspect", str(FIXTURES / "alpha"), "--only", "scripts,assets"
        )
        for heading, target, path, page in (
            ("scripts 1", "greet.py", "scripts/greet.py", "task:repair"),
            ("assets 1", "template.md", "assets/template.md", "task:document"),
        ):
            size = (FIXTURES / "alpha" / path).stat().st_size
            with self.subTest(dimension=heading):
                self.assertEqual(
                    [f"{target} {path} {size}B linked={page}"], block(report, heading)
                )

    def test_task_and_facet_rows_name_each_page_whose_authored_text_links_them(self):
        """The root routes to every task and the facet index lists every facet,
        so neither counts; an authored link from another page does. A task with
        no such link carries no `linked` line, as it carries no empty `guides`
        line."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            review = task_path(root, "alpha", "review")
            review.write_text(
                review.read_text(encoding="utf-8")
                + "\nSee [[task:repair]] and [[facet:python]].\n",
                encoding="utf-8",
            )
            _, report, _ = run(
                "inspect", str(root / "alpha"), "--only", "tasks,facets"
            )
        tasks = block(report, "tasks 3")
        start = next(i for i, line in enumerate(tasks) if line.startswith("repair "))
        end = next(
            (i for i in range(start + 1, len(tasks)) if not tasks[i].startswith("  ")),
            len(tasks),
        )
        self.assertIn("  linked task:review", tasks[start + 1 : end])
        self.assertEqual(1, sum(line.startswith("  linked ") for line in tasks))
        for facet, linked in (("python", "linked=task:review"), ("urgent", "linked=none")):
            with self.subTest(facet=facet):
                fields = row(report, "facets 3", facet)
                self.assertEqual(
                    [linked], [field for field in fields if field.startswith("linked=")]
                )

    def test_an_authored_value_written_across_lines_stays_on_its_row(self):
        """An agent reads one fact per line, so a newline in a value would read
        as a row of its own."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with edit_frontmatter(task_path(root, "alpha", "review")) as fields:
                fields["title"] = "Review\na change"
                fields["goal"] = "Every risk\nis named."
                fields["recognize"] = ["the requester asks\nfor risks"]
            with edit_frontmatter(root / "alpha" / "facets" / "python.md") as fields:
                fields["description"] = "Python\nguidance."
            with edit_frontmatter(root / "alpha" / "guides" / "checklist.md") as fields:
                fields["activation"] = "When the change\ntouches an interface"
            _, report, _ = run(
                "inspect", str(root / "alpha"), "--only", "tasks,facets,guides"
            )
        lines = report.splitlines()
        self.assertTrue(any(line.startswith('review "Review a change" ') for line in lines))
        self.assertIn("  goal Every risk is named.", lines)
        self.assertIn("  when the requester asks for risks", lines)
        self.assertTrue(any(line.endswith("linked=none Python guidance.") for line in lines))
        self.assertTrue(
            any(line.startswith("checklist ") and "When the change touches" in line for line in lines)
        )

    def test_a_facet_row_states_its_description_or_a_dash(self):
        """The description is a field an author may leave out, so the row says
        which of the two it is rather than printing an empty value."""
        _, report, _ = run("inspect", str(FIXTURES / "alpha"), "--only", "facets")
        python = " ".join(row(report, "facets 3", "python"))
        description = field_of(FIXTURES / "alpha" / "facets" / "python.md", "description")
        self.assertTrue(python.endswith(f"B linked=none {description}"), python)
        self.assertEqual("-", row(report, "facets 3", "legacy")[-1])

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
            before = tree_bytes(root)
            run("inspect", str(root / "alpha"), "--page", ROOT)
            self.assertEqual(before, tree_bytes(root))

    def test_the_exit_status_gates_on_errors_alone(self):
        """A warning passes unless the caller's standard promotes it, exactly as
        `validate` decides, since the two read the same checks."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            write_source(
                root / "alpha" / "knowledge" / "unused.md",
                "kind: fact\ntitle: Unused",
                "Reached by nothing.",
            )
            warned, _, _ = run("inspect", str(root / "alpha"), "--only", "diagnostics")
            promoted, report, _ = run(
                "inspect",
                str(root / "alpha"),
                "--only",
                "diagnostics",
                "--fail-on-warning",
            )
        self.assertEqual(0, warned)
        self.assertEqual(1, promoted)
        self.assertEqual("error", row(report, "diagnostics 1", "error")[0])
        self.assertEqual("knowledge.orphan", row(report, "diagnostics 1", "error")[1])

    def test_inspect_and_validate_report_the_same_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            with_orphan_and_missing_reference(root)
            _, inspected, _ = run(
                "inspect", str(root / "alpha"), "--only", "diagnostics"
            )
            _, validated, _ = run("validate", str(root / "alpha"))
        found = {
            (fields[0], fields[1])
            for fields in (line.split() for line in block(inspected, "diagnostics 2"))
        }
        self.assertEqual(
            {("error", "task.unknown-knowledge"), ("warning", "knowledge.orphan")},
            found,
        )
        self.assertEqual(
            {code for _, code in found},
            set(re.findall(r"\(([a-z]+\.[a-z0-9_-]+)\)", validated)),
        )
        self.assertIn(
            "Summary: 0 passed, 1 failed, 1 error, 1 warning, 1 total.",
            validated.splitlines(),
        )


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
        lines = report.splitlines()
        built = lines.index("[BUILT] Alpha (alpha)")
        self.assertEqual(
            f"  Artifact    {(self.output / 'alpha').resolve()}", lines[built + 1]
        )
        self.assertEqual("Summary: 2 skills built as folders, 0 warnings.", lines[-1])

    def test_build_writes_an_archive_when_asked(self):
        status, report, _ = run(
            "build", str(self.root), "--output", str(self.output), "--zip"
        )
        self.assertEqual(0, status)
        self.assertEqual(
            "Summary: 2 skills built as archives, 0 warnings.", report.splitlines()[-1]
        )
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

if __name__ == "__main__":
    unittest.main()
