"""The explain command, and its table's coverage of every reported code."""

from __future__ import annotations

import contextlib
import io
import textwrap
import unittest

from degardis.cli import main, parser
from degardis.content import ALLOWED_CONTENT_KEYS
from degardis.explain import CHECKS
from degardis.registry import INTERFACE_FIELDS, MANIFEST_FIELDS
from degardis.sources import (
    COMMON_STEP_FIELDS,
    GUIDANCE_FIELDS,
    PATTERN_FIELDS,
    POLICY_FIELDS,
    PROFILE_FIELDS,
    PROTOCOL_FIELDS,
    PROVISION_FIELDS,
    RECORD_FIELDS,
    RULE_FIELDS,
    WORKFLOW_FIELDS,
)

from tests.checkcodes import computed_code_arguments, emitted_check_codes
from tests.support import REPO_ROOT


SOURCE_FIELDS = frozenset().union(
    ALLOWED_CONTENT_KEYS,
    COMMON_STEP_FIELDS,
    GUIDANCE_FIELDS,
    INTERFACE_FIELDS,
    MANIFEST_FIELDS,
    PATTERN_FIELDS,
    POLICY_FIELDS,
    PROFILE_FIELDS,
    PROTOCOL_FIELDS,
    PROVISION_FIELDS,
    RECORD_FIELDS,
    RULE_FIELDS,
    WORKFLOW_FIELDS,
)


class ExplainCoverageTests(unittest.TestCase):
    def test_every_reported_check_code_has_an_explain_entry(self):
        self.assertEqual(
            set(),
            emitted_check_codes() - set(CHECKS),
            "check codes reported with no `degardis explain` entry",
        )

    def test_every_explain_entry_names_a_code_some_check_reports(self):
        """The other direction, which an entry with no emitter slips through.

        An explained code no check can report reads to an author as a check the
        compiler runs, and `degardis explain` prints its trigger and repair.
        Nothing tells them the compiler will never say it.
        """
        self.assertEqual(
            set(),
            set(CHECKS) - emitted_check_codes(),
            "`degardis explain` entries for codes no check reports",
        )

    def test_check_codes_are_written_out_so_coverage_can_be_checked(self):
        self.assertEqual(
            [],
            computed_code_arguments(),
            "write each check code as a string literal, not as an expression",
        )

    def test_every_explain_entry_states_a_trigger_an_impact_and_both_examples(self):
        for code, entry in CHECKS.items():
            with self.subTest(code=code):
                self.assertTrue(entry.trigger.endswith("."), entry.trigger)
                self.assertTrue(entry.impact.endswith("."), entry.impact)
                self.assertTrue(entry.failing.strip())
                self.assertTrue(entry.passing.strip())
                self.assertNotEqual(entry.failing.strip(), entry.passing.strip())

    def test_every_check_code_is_named_by_some_test(self):
        """An explained check nothing exercises is a check nobody has run.

        The two coverage cases above prove a code has an explanation and an
        emitter. Neither proves the check fires, so a check could be broken
        while both pass. This holds the third direction: some case in this
        suite names the code, so breaking the check breaks a test.

        Satisfy it with a case that makes the check fire and asserts the code.
        Never park a code in a list of codes: this scan reads any occurrence as
        coverage, so a list would leave the check itself still never run while
        every case here passes.
        """
        source = "".join(
            path.read_text(encoding="utf-8")
            for path in sorted((REPO_ROOT / "tests").glob("*.py"))
        )
        self.assertEqual(
            [],
            sorted(code for code in emitted_check_codes() if code not in source),
            "check codes no test names; add a case that reports each",
        )


class CodeSpellingTests(unittest.TestCase):
    def test_a_code_naming_a_source_field_spells_it_as_the_key_does(self):
        """One rule for the whole vocabulary, so a code can be built not looked up.

        A check code reads as hyphenated words, except where it names a field of
        the source: there it reproduces the key. An author who knows the key
        knows the code, and never has to remember which of the two spellings a
        particular check chose.
        """
        for field in sorted(name for name in SOURCE_FIELDS if "_" in name):
            with self.subTest(field=field):
                hyphenated = field.replace("_", "-")
                self.assertEqual(
                    [],
                    [code for code in CHECKS if hyphenated in code],
                    f"a code hyphenates the source key {field}",
                )

    def test_the_code_naming_rule_is_stated_where_the_codes_are_listed(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            main(["explain", "interface.short-description-length"])

        report = " ".join(stderr.getvalue().split())
        self.assertIn("spells exactly as the key does", report)
        self.assertIn("short_description-length", report)


class ExplainCommandTests(unittest.TestCase):
    def test_explain_reports_one_code_without_reading_any_source(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["explain", "rule.unmatched"])

        report = stdout.getvalue()
        self.assertEqual(0, status)
        self.assertIn("rule.unmatched", report)
        for label in ("Trigger", "Impact", "Failing", "Passing"):
            self.assertIn(label, report)

    def test_explain_keeps_example_indentation_unwrapped(self):
        """An example is source an author copies, so its lines are not reflowed.

        The expectation is the table's own entry rather than a transcript of
        one, so rewording the example cannot leave this passing while the
        report has started wrapping the lines it prints.
        """
        code = "value.invalid-binding"
        entry = textwrap.dedent(CHECKS[code].passing).strip().splitlines()
        self.assertTrue(
            any(line.startswith("  ") for line in entry),
            f"{code} has no indented example line to preserve",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["explain", code])

        block = stdout.getvalue().split("Passing", 1)[1]
        self.assertEqual(entry, textwrap.dedent(block).strip().splitlines())

    def test_explain_reports_every_requested_code_in_one_run(self):
        codes = ["rule.unmatched", "yaml.ambiguous-scalar", "icon.too-large"]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["explain", *codes])

        report = stdout.getvalue()
        self.assertEqual(0, status)
        for code in codes:
            self.assertIn(code, report)
        # One block per code, each opening on a line of its own.
        openings = [line for line in report.splitlines() if line in codes]
        self.assertEqual(codes, openings)
        self.assertEqual(3, report.count("  Trigger"))

    def test_explain_reports_a_repeated_code_once(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["explain", "rule.unmatched", "rule.unmatched"])

        self.assertEqual(0, status)
        self.assertEqual(1, stdout.getvalue().count("  Trigger"))

    def test_explain_explains_known_codes_and_still_names_unknown_ones(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["explain", "rule.unmatched", "yaml.no-such-check"])

        self.assertEqual(1, status)
        self.assertIn("rule.unmatched", stdout.getvalue())
        self.assertIn("  Trigger", stdout.getvalue())
        self.assertIn(
            "[ERROR] Unknown check code: yaml.no-such-check", stderr.getvalue()
        )

    def test_explain_names_every_unknown_code_together(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["explain", "yaml.no-such-check", "rule.no-such-check"])

        self.assertEqual(1, status)
        self.assertIn(
            "[ERROR] Unknown check codes: yaml.no-such-check, rule.no-such-check",
            stderr.getvalue(),
        )

    def test_explain_requires_at_least_one_code(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["explain"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("required: CODE", stderr.getvalue())

    def test_explain_rejects_an_unknown_code_and_lists_the_known_ones(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["explain", "yaml.no-such-check"])

        report = stderr.getvalue()
        self.assertEqual(1, status)
        self.assertIn("[ERROR] Unknown check code: yaml.no-such-check", report)
        self.assertIn("Known check codes:", report)
        for known in ("ambiguous-scalar", "unreachable"):
            self.assertIn(known, report)


if __name__ == "__main__":
    unittest.main()
