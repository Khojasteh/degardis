"""The command-line surface itself: parsing, help, and version."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from degardis import __version__
from degardis.cli import parser


class CliParserTests(unittest.TestCase):
    def test_source_and_output_paths_use_the_same_normalization(self):
        args = parser().parse_args(
            [
                "build",
                "relative-source",
                "--output",
                "relative-output",
            ]
        )

        self.assertEqual(Path("relative-source").resolve(), args.paths[0])
        self.assertEqual(Path("relative-output").resolve(), args.output)

    def test_help_describes_skill_paths_without_removed_commands(self):
        help_text = parser().format_help()
        self.assertIn("self-contained agent skills", help_text)
        self.assertIn("examples/structured-summary", help_text)
        self.assertNotIn("--suite", help_text)
        self.assertNotIn("route", help_text)

    def test_version_option_displays_the_tool_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual(f"degardis {__version__}\n", stdout.getvalue())

    def test_route_is_not_a_command(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser().parse_args(["route", "anything"])
