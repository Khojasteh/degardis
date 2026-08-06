"""The explain command, and its table's coverage of every reported code."""

from __future__ import annotations

import contextlib
import io
import unittest

from degardis.cli import main, parser
from degardis.explain import CHECKS
from degardis.registry import PROFILE_FIELDS
from degardis.resolver import (
    ALLOWED_CONTENT_KEYS,
    ALLOWED_ENTRY_FIELDS,
    ALLOWED_WORKFLOW_FIELDS,
    ALLOWED_WORKFLOW_STEP_FIELDS,
)
from degardis.validate import INTERFACE_FIELDS, MANIFEST_FIELDS

from tests.checkcodes import computed_code_arguments, emitted_check_codes


SOURCE_FIELDS = frozenset().union(
    ALLOWED_CONTENT_KEYS,
    ALLOWED_ENTRY_FIELDS,
    ALLOWED_WORKFLOW_FIELDS,
    ALLOWED_WORKFLOW_STEP_FIELDS,
    INTERFACE_FIELDS,
    MANIFEST_FIELDS,
    PROFILE_FIELDS,
)


class ExplainTests(unittest.TestCase):
    def test_every_reported_check_code_has_an_explain_entry(self):
        emitted = emitted_check_codes()

        self.assertEqual(
            set(),
            emitted - set(CHECKS),
            "check codes reported with no `degardis explain` entry",
        )
        self.assertEqual(
            set(),
            set(CHECKS) - emitted,
            "`degardis explain` entries for check codes nothing reports",
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

    def test_every_code_naming_a_manifest_field_is_present_under_that_spelling(self):
        for code in (
            "manifest.missing-primary_workflow",
            "manifest.unsupported-format_version",
            "interface.missing-display_name",
            "interface.missing-short_description",
            "interface.short_description-length",
            "interface.missing-default_prompt",
            "interface.default_prompt-token",
        ):
            with self.subTest(code=code):
                self.assertIn(code, CHECKS)

    def test_the_code_naming_rule_is_stated_where_the_codes_are_listed(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            main(["explain", "interface.short-description-length"])

        report = " ".join(stderr.getvalue().split())
        self.assertIn("spells exactly as the key does", report)
        self.assertIn("interface.short_description-length", report)

    def test_explain_reports_one_code_without_reading_any_source(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["explain", "entry.missing-priority"])

        report = stdout.getvalue()
        self.assertEqual(0, code)
        self.assertIn("entry.missing-priority", report)
        for label in ("Trigger", "Impact", "Failing", "Passing"):
            self.assertIn(label, report)
        self.assertIn("priority: 20", report)

    def test_explain_keeps_example_indentation_unwrapped(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["explain", "entry.invalid-type"])

        self.assertIn("\n    require:\n      - Cite the source\n", stdout.getvalue())

    def test_explain_reports_every_requested_code_in_one_run(self):
        codes = ["entry.missing-priority", "yaml.altered-scalar", "icon.too-large"]
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
            status = main(
                ["explain", "entry.missing-priority", "entry.missing-priority"]
            )

        self.assertEqual(0, status)
        self.assertEqual(1, stdout.getvalue().count("  Trigger"))

    def test_explain_explains_known_codes_and_still_names_unknown_ones(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stderr):
                status = main(
                    ["explain", "entry.missing-priority", "yaml.no-such-check"]
                )

        self.assertEqual(1, status)
        self.assertIn("entry.missing-priority", stdout.getvalue())
        self.assertIn("  Trigger", stdout.getvalue())
        self.assertIn(
            "[ERROR] Unknown check code: yaml.no-such-check", stderr.getvalue()
        )

    def test_explain_names_every_unknown_code_together(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["explain", "yaml.no-such-check", "entry.no-such-check"])

        self.assertEqual(1, status)
        self.assertIn(
            "[ERROR] Unknown check codes: yaml.no-such-check, entry.no-such-check",
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
            code = main(["explain", "yaml.no-such-check"])

        report = stderr.getvalue()
        self.assertEqual(1, code)
        self.assertIn("[ERROR] Unknown check code: yaml.no-such-check", report)
        self.assertIn("Known codes:", report)
        for known in ("yaml.altered-scalar", "workflow.unreachable"):
            self.assertIn(known, report)
