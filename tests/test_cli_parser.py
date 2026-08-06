"""The command-line surface itself: parsing, help, and version."""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from pathlib import Path
from unittest import mock

from degardis import __version__, cli
from degardis.cli import main, parser

# Imported from the module whose check enforces it, not from its definition, so a
# help text that drifts from what `validate` accepts fails here.
from degardis.validate import SUPPORTED_FORMAT_VERSIONS


def command_help(name: str) -> str:
    """The help one command prints, as a caller running `-h` would see it."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.suppress(SystemExit):
            main([name, "-h"])
    return stdout.getvalue()


def announced_formats(help_text: str) -> list[int]:
    """The source format versions the help announces."""
    sentence = re.search(r"Source format:(.*?)\n\n", help_text, re.DOTALL)
    if sentence is None:
        return []
    # The clause before the semicolon is the accepted set; what follows repeats
    # one of its members as the version new source should declare.
    listed = sentence.group(1).partition(";")[0]
    return [int(value) for value in re.findall(r"\d+", listed)]


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

    def test_help_announces_the_source_format_the_validator_enforces(self):
        help_text = parser().format_help()

        self.assertIn("Source format:", help_text)
        self.assertEqual(
            sorted(SUPPORTED_FORMAT_VERSIONS),
            announced_formats(help_text),
        )
        self.assertIn("skill.yaml format_version", help_text)

    def test_the_announcement_is_read_from_the_enforced_set_not_written_in(self):
        with mock.patch.object(
            cli, "SUPPORTED_FORMAT_VERSIONS", frozenset({1, 7})
        ):
            help_text = parser().format_help()

        self.assertEqual([1, 7], announced_formats(help_text))
        self.assertIn("format_version 1 or 7", help_text)

    def test_a_compiler_reading_several_formats_announces_all_of_them(self):
        # Support is a set because a release that adds a format keeps reading the
        # ones before it. New source declares the newest of them.
        for supported, announced in (
            ({4}, "format_version 4"),
            ({1, 2}, "format_version 1 or 2; declare 2 in new source"),
            ({1, 2, 3}, "format_version 1, 2 or 3; declare 3 in new source"),
        ):
            with self.subTest(supported=sorted(supported)):
                with mock.patch.object(
                    cli, "SUPPORTED_FORMAT_VERSIONS", frozenset(supported)
                ):
                    help_text = parser().format_help()

                self.assertIn(f"skill.yaml {announced}.", help_text)
                self.assertEqual(sorted(supported), announced_formats(help_text))

    def test_the_authoring_hint_appears_only_where_there_is_a_choice(self):
        # The hint is worth its tokens only when more than one format is accepted.
        self.assertEqual(
            len(SUPPORTED_FORMAT_VERSIONS) > 1,
            "in new source" in parser().format_help(),
        )

    def test_the_source_format_is_announced_once_at_the_top_level(self):
        # The supported format belongs to the compiler, not to one subcommand, and
        # two copies of one constant drift apart.
        for name in ("agent", "build", "validate", "list", "explain"):
            self.assertEqual([], announced_formats(command_help(name)), name)

    def test_route_is_not_a_command(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser().parse_args(["route", "anything"])
