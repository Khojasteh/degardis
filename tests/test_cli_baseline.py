"""Comparing a skill's budget against the revision a git reference names."""

from __future__ import annotations

import contextlib
import io
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.cli import main

from tests.support import copy_skills
from tests.test_cli_agent import agent_help


SIZE = re.compile(r"([+-]?\d+)(?:B|L|w)\b")

# Identity and signing are pinned so a fixture repository commits the same way
# whatever the machine's global git configuration happens to be.
SETTINGS = (
    "-c",
    "user.name=Degardis Tests",
    "-c",
    "user.email=tests@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *SETTINGS, *arguments],
        check=True,
        capture_output=True,
    )


def repository(directory: Path, *committed: str) -> Path:
    """A throwaway repository holding the fixture skills in one commit.

    Naming skills commits only those, leaving the rest present in the working
    tree but absent from every revision.
    """
    root = copy_skills(directory)
    git(directory, "init", "-q")
    staged = [str((root / name).relative_to(directory)) for name in committed]
    git(directory, "add", *(staged or ["-A"]))
    git(directory, "commit", "-q", "-m", "fixture skills")
    return root


def state(directory: Path) -> tuple[str, str]:
    """What the working tree and the index hold, as git itself reports them."""
    porcelain = subprocess.run(
        ["git", "-C", str(directory), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "-C", str(directory), "diff", "--cached", "--name-status"],
        check=True,
        capture_output=True,
        text=True,
    )
    return porcelain.stdout, staged.stdout


def budget_report(*arguments: str) -> dict[str, str]:
    """Run the budget section and return each of its lines, keyed by label."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = main(["agent", *arguments, "--only", "budget"])
    lines = {
        line.split()[0]: line
        for line in stdout.getvalue().splitlines()
        if line and not line.startswith(" ")
    }
    lines["status"] = str(code)
    return lines


def sizes(*lines: str) -> list[int]:
    """The numbers a budget line carries, in the order it prints them."""
    return [int(value) for line in lines for value in SIZE.findall(line)]


def lengthen(root: Path, skill: str) -> None:
    """Grow both halves of a skill's budget: its SKILL.md and its entry weight."""
    workflow = root / skill / "workflows" / "run.yaml"
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    data["steps"][0]["instruction"] = (
        "Perform the alpha fixture action, and then perform it a second time "
        "so that the generated SKILL.md carries measurably more prose than the "
        "committed revision does."
    )
    workflow.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    entry = root / skill / "entries" / "rule-one.yaml"
    record = yaml.safe_load(entry.read_text(encoding="utf-8"))
    record["rule"] = record["rule"] + " " + "It also says considerably more."
    entry.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


@unittest.skipUnless(shutil.which("git"), "git is required to read a baseline")
class BaselineComparisonTests(unittest.TestCase):
    def test_baseline_reports_the_revision_sizes_and_the_change_since(self):
        # The expected baseline numbers come from measuring a copy of the tree
        # taken before the edit, so nothing about them is derived from the code
        # that reads the revision.
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)
            before = copy_skills(Path(directory) / "before")
            expected = budget_report(str(before / "alpha"))
            lengthen(root, "alpha")

            report = budget_report(str(root / "alpha"), "--baseline", "HEAD")

        was = sizes(expected["body"], expected["refs"])
        now = sizes(report["body"], report["refs"])
        self.assertEqual(was, sizes(report["base"]))
        self.assertEqual(
            [now - was for now, was in zip(now, was)],
            sizes(report["delta"]),
        )
        # The edit has to have moved both halves, or the comparison above would
        # hold for a delta that is always zero.
        self.assertNotEqual(was[:5], now[:5], "SKILL.md size did not move")
        self.assertNotEqual(was[5:], now[5:], "reference weight did not move")

    def test_baseline_signs_every_delta_including_an_unchanged_size(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)

            report = budget_report(str(root / "alpha"), "--baseline", "HEAD")

        self.assertEqual([0] * 8, sizes(report["delta"]))
        self.assertIn("SKILL.md +0B +0L", report["delta"])
        self.assertIn("| entries +0B | workflows +0B | profiles +0B", report["delta"])

    def test_reading_a_baseline_leaves_the_working_tree_and_index_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)
            lengthen(root, "alpha")
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            workflow = root / "alpha" / "workflows" / "run.yaml"
            git(work, "add", str(entry.relative_to(work)))
            edited = workflow.read_bytes()
            before = state(work)

            budget_report(str(root / "alpha"), "--baseline", "HEAD")

            # The incident this option exists to prevent left the index staged
            # against an intact working tree, so both are checked.
            self.assertEqual(before, state(work))
            self.assertEqual(edited, workflow.read_bytes())

    def test_a_skill_the_revision_does_not_hold_is_absent_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            # gamma is a sound skill the working tree has and no revision does,
            # which is what a newly authored skill looks like.
            root = repository(work, "alpha", "beta")

            report = budget_report(str(root / "gamma"), "--baseline", "HEAD")

        self.assertEqual("base  HEAD absent", report["base"])
        self.assertNotIn("delta", report)
        self.assertEqual("0", report["status"])

    def test_a_revision_that_cannot_be_measured_is_not_reported_as_a_size(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = copy_skills(work)
            manifest = root / "alpha" / "skill.yaml"
            sound = manifest.read_text(encoding="utf-8")
            broken = yaml.safe_load(sound)
            broken["primary_workflow"] = "alpha.missing"
            manifest.write_text(
                yaml.safe_dump(broken, sort_keys=False), encoding="utf-8"
            )
            git(work, "init", "-q")
            git(work, "add", "-A")
            git(work, "commit", "-q", "-m", "a skill nothing can be generated from")
            manifest.write_text(sound, encoding="utf-8")

            report = budget_report(str(root / "alpha"), "--baseline", "HEAD")

        self.assertEqual("base  HEAD unmeasured", report["base"])
        self.assertNotIn("delta", report)
        # The revision's own errors are not the caller's question and do not
        # decide the status of a sound working tree.
        self.assertEqual("0", report["status"])


@unittest.skipUnless(shutil.which("git"), "git is required to read a baseline")
class BaselineContractTests(unittest.TestCase):
    def test_the_lines_a_report_already_printed_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)
            lengthen(root, "alpha")

            plain = budget_report(str(root / "alpha"))
            compared = budget_report(str(root / "alpha"), "--baseline", "HEAD")

        for label in ("skill", "body", "refs", "count", "main", "ids", "desc"):
            with self.subTest(line=label):
                self.assertEqual(plain[label], compared[label])
        self.assertNotIn("base", plain)
        self.assertNotIn("delta", plain)

    def test_the_legend_documents_every_line_a_comparison_emits(self):
        legend = agent_help()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)
            lengthen(root, "alpha")
            report = budget_report(str(root / "alpha"), "--baseline", "HEAD")

        emitted = set(report) - {"status"}
        self.assertLessEqual({"base", "delta"}, emitted)
        self.assertEqual([], sorted(label for label in emitted if label not in legend))


@unittest.skipUnless(shutil.which("git"), "git is required to read a baseline")
class BaselineFailureTests(unittest.TestCase):
    def report_failure(self, *arguments: str) -> tuple[int, str]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["agent", *arguments])
        return code, stderr.getvalue()

    def test_a_selection_without_budget_names_what_it_left_out(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)

            code, error = self.report_failure(
                str(root / "alpha"), "--only", "entries", "--baseline", "HEAD"
            )

        self.assertEqual(1, code)
        self.assertIn("budget", error)

    def test_a_revision_git_cannot_resolve_fails_with_gits_own_message(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)

            code, error = self.report_failure(
                str(root / "alpha"), "--baseline", "no-such-revision"
            )

        self.assertEqual(1, code)
        self.assertIn("[ERROR]", error)
        self.assertIn("no-such-revision", error)

    def test_a_source_outside_any_repository_fails_before_measuring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))

            code, error = self.report_failure(str(root / "alpha"), "--baseline", "HEAD")

        self.assertEqual(1, code)
        self.assertIn("[ERROR]", error)
        # Git says what went wrong but not what was being attempted, so every
        # --baseline failure names the option and what it needed.
        self.assertIn("--baseline", error)
        self.assertIn(str((root / "alpha").resolve()), error)
        self.assertIn("not a git repository", error)

    def test_every_baseline_failure_names_the_option(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)
            outside = copy_skills(Path(directory) / "outside")
            failures = {
                "no work tree": (str(outside / "alpha"), "--baseline", "HEAD"),
                "no such revision": (str(root / "alpha"), "--baseline", "nope"),
                "option as revision": (str(root / "alpha"), "--baseline=-X"),
                "budget deselected": (
                    str(root / "alpha"),
                    "--baseline",
                    "HEAD",
                    "--only",
                    "entries",
                ),
            }

            for case, arguments in failures.items():
                with self.subTest(failure=case):
                    code, error = self.report_failure(*arguments)
                    self.assertEqual(1, code)
                    self.assertIn("--baseline", error)

    def test_a_revision_git_would_read_as_an_option_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            root = repository(work)

            code, error = self.report_failure(
                str(root / "alpha"), "--baseline=--upload-pack=touched"
            )

        self.assertEqual(1, code)
        self.assertIn("option", error)


if __name__ == "__main__":
    unittest.main()
