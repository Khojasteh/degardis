"""The build command, and how it reports failure to a person."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis.build import SkillCompiler
from degardis.cli import main, parser

from tests.support import FIXTURES, copy_skills


class BuildCommandTests(unittest.TestCase):
    def test_build_accepts_collection_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual(3, len([p for p in output.iterdir() if p.is_dir()]))
            report = stdout.getvalue()
            self.assertIn("Build\n", report)
            self.assertIn("[BUILT] Alpha (alpha)", report)
            self.assertIn("[BUILT] Beta (beta)", report)
            self.assertIn("[BUILT] Gamma (gamma)", report)
            self.assertIn("Summary: 3 skills built as folders, 0 warnings.", report)

    def test_build_recursively_discovers_nested_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            nested = root / "teams" / "editing"
            nested.mkdir(parents=True)
            (root / "beta").rename(nested / "beta")
            (root / "gamma").rename(root / "teams" / "gamma")
            output = Path(directory) / "artifacts"

            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["build", str(root), "--output", str(output)])

            self.assertEqual(0, code)
            self.assertEqual(
                {"alpha", "beta", "gamma"},
                {path.name for path in output.iterdir()},
            )

    def test_build_requires_output(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["build", str(FIXTURES)])

        self.assertEqual(2, raised.exception.code)
        self.assertIn(
            "the following arguments are required: --output",
            stderr.getvalue(),
        )

    def test_build_accepts_zip_option(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES),
                        "--output",
                        str(output),
                        "--zip",
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual(3, len(list(output.glob("*.zip"))))
            self.assertIn(
                "Summary: 3 skills built as archives, 0 warnings.",
                stdout.getvalue(),
            )

    def test_build_allows_all_profile_when_skill_has_none(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "gamma"),
                        "--profile",
                        "all",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(0, code)
            self.assertTrue((output / "gamma" / "SKILL.md").is_file())

    def test_build_reports_domain_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "gamma"),
                        "--profile",
                        "al",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(1, code)
            self.assertEqual(
                "[ERROR] Profile selector matched no selected skill: al\n",
                stderr.getvalue(),
            )
            self.assertFalse(output.exists())

    def test_filesystem_error_is_reported_without_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(
            SkillCompiler,
            "build",
            side_effect=PermissionError("injected permission failure"),
        ):
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "alpha"),
                        "--output",
                        "unused",
                    ]
                )

        self.assertEqual(1, code)
        self.assertEqual(
            "[ERROR] injected permission failure\n",
            stderr.getvalue(),
        )
