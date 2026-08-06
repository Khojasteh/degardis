"""How YAML problems reach the author.

Covers a file that does not parse at all, and text that parses but which YAML
silently rewrote into something other than what was written.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from degardis.cli import main

from tests.support import copy_skills


class YamlReportingTests(unittest.TestCase):
    def test_invalid_yaml_is_reported_in_the_compiler_s_own_voice(self):
        shapes = {
            "colon in a plain value": (
                "rule: Report the outcome: pass or fail\n",
                "a colon followed by a space",
            ),
            "unclosed quote": (
                'rule: "Report the outcome\n',
                "a quoted value is never closed",
            ),
            "tab indentation": ("rule:\n\tReport the outcome\n", "a tab character"),
            "reserved first character": (
                "rule: @outcome first\n",
                "a value cannot begin with '@'",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            for label, (source, expected) in shapes.items():
                with self.subTest(shape=label):
                    entry.write_text(f"id: alpha.rule-one\n{source}", encoding="utf-8")

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = main(["validate", str(root / "alpha")])

                    report = " ".join(stdout.getvalue().split())
                    self.assertEqual(1, code)
                    self.assertIn(f"{entry}:", report)
                    self.assertIn(expected, report)
                    for internal in (
                        "while scanning",
                        "while parsing",
                        "expected <block end>",
                        "could not find expected",
                    ):
                        self.assertNotIn(internal, report)

    def test_an_unquoted_exclusion_pattern_reads_as_a_tag_not_a_traceback(self):
        """The failure the ! exclusion marker invites, in the compiler's voice."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            text = manifest.read_text(encoding="utf-8").replace(
                "  - assets/**/*",
                "  - assets/**/*\n  - !assets/drafts/**/*",
            )
            manifest.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertEqual(1, code)
        self.assertIn("read as a YAML type tag rather than as text", report)
        self.assertIn("!assets/drafts/**/* is not the value", report)
        self.assertIn("quote the value", report)
        self.assertNotIn("could not determine a constructor", report)
        self.assertNotIn("<unicode string>", report)

    def test_unrecognized_yaml_failure_keeps_the_parser_s_own_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            entry.write_text(
                "id: alpha.rule-one\nrule: *undefined\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertEqual(1, code)
        self.assertIn("invalid YAML", report)
        self.assertIn("found undefined alias", report)

    def test_malformed_yaml_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            manifest.write_text("name: alpha\ninterface: [\n", encoding="utf-8")

            for command in ("list", "build"):
                with self.subTest(command=command):
                    stderr = io.StringIO()
                    arguments = [command, str(root / "alpha")]
                    if command == "build":
                        arguments.extend(["--output", str(root / "output")])
                    with contextlib.redirect_stderr(stderr):
                        code = main(arguments)

                    self.assertEqual(1, code)
                    self.assertIn("[ERROR]", stderr.getvalue())
                    self.assertIn("invalid YAML", stderr.getvalue())

    def test_a_manifest_that_does_not_parse_is_reported_inside_the_report(self):
        """The one failure that stops every check still belongs to the report.

        A skill whose manifest does not load is the most likely single point of
        failure there is, and it used to be the one case the report shape could
        not carry: no result line, no check code, and nothing for an agent
        reading the fixed line shape to match.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            manifest.write_text("name: alpha\ntitle: Probe: x\n", encoding="utf-8")

            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout):
                with contextlib.redirect_stderr(stderr):
                    validated = main(["validate", str(root / "alpha")])
            report = " ".join(stdout.getvalue().split())

            agent_out = io.StringIO()
            with contextlib.redirect_stdout(agent_out):
                reported = main(
                    ["agent", str(root / "alpha"), "--only", "diagnostics"]
                )
            lines = agent_out.getvalue().splitlines()

        self.assertEqual(1, validated)
        self.assertEqual("", stderr.getvalue())
        self.assertIn("[FAIL] alpha (alpha)", report)
        self.assertIn("a colon followed by a space", report)
        self.assertIn("(source.invalid-yaml)", report)
        self.assertIn("Summary: 0 passed, 1 failed, 1 error", report)
        self.assertIn("Run `degardis explain CODE", report)

        self.assertEqual(1, reported)
        failure = next(line for line in lines if line.startswith("error "))
        _, location, code, _ = failure.split(" ", 3)
        self.assertEqual("skill.yaml:2", location)
        self.assertEqual("source.invalid-yaml", code)

    def test_validate_warns_for_yaml_values_that_change_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            text = manifest.read_text(encoding="utf-8")
            text += "\nversion: 1.10\n"
            manifest.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertIn("key 'version' silently overrides the earlier value", report)
        self.assertIn("'1.10' parses as the number", report)

    def test_validate_warns_for_an_inline_comment_inside_a_list_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            text = entry.read_text(encoding="utf-8")
            text += "require:\n- Keep this text #but not this trailing part\n"
            entry.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertIn("inline comment marker", report)

    def test_validate_warns_for_a_leading_anchor_or_alias_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            text = entry.read_text(encoding="utf-8")
            text += (
                "scope: &Shared text meant to start with an ampersand\n"
                "require:\n"
                "- *Shared\n"
            )
            entry.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertIn("consumed as an anchor name", report)
        self.assertIn("resolved as an alias reference", report)

    def test_validate_warns_for_a_value_a_type_tag_consumed(self):
        """A construct no check names, caught by the one general comparison."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            text = entry.read_text(encoding="utf-8")
            text += "scope: !!str Applies to every request\n"
            entry.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

        report = " ".join(stdout.getvalue().split())
        self.assertEqual(0, code)
        self.assertIn("plain scalar begins with '!!str'", report)
        self.assertIn("consumed as a type tag instead of the value", report)

    def test_altered_value_warnings_share_one_check_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entry = root / "alpha" / "entries" / "rule-one.yaml"
            text = entry.read_text(encoding="utf-8")
            text += (
                "scope: &Shared applies to every request\n"
                "constraint: !!str tagged text\n"
                "rationale: text #and a lost comment\n"
                "require:\n"
                "- *Shared\n"
            )
            entry.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["agent", str(root / "alpha"), "--only", "diagnostics"])

        codes = [
            line.split()[2]
            for line in stdout.getvalue().splitlines()
            if line.startswith("warn ")
        ]
        self.assertEqual(4, codes.count("yaml.altered-scalar"))

    def test_validate_accepts_quoted_and_block_multiline_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            text = manifest.read_text(encoding="utf-8")
            text += (
                '\nquoted: "First line of the value\n'
                "  Second line: it holds a colon\n"
                '  Third line mentions bug #42 and 1.10"\n'
                "block: |\n"
                "  Block line: yes\n"
                "  1.10\n"
            )
            manifest.write_text(text, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["validate", str(root / "alpha")])

        report = stdout.getvalue()
        self.assertNotIn("quote the value", report)
