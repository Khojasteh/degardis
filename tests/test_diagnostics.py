"""What the collector keeps, and what it hands a caller that cannot read a report.

`degardis build` merges every selected skill's findings into one collector and
then stops on the errors, so this is where a caller who never sees the validation
report gets its content: once per finding, and carrying the check code that makes
`degardis explain` usable from a raise.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from degardis.model import DegardisError, Diagnostic, Diagnostics, SourceError


class DiagnosticIdentityTests(unittest.TestCase):
    """`Diagnostic.key` names what makes two findings the same one."""

    def finding(self, **fields: object) -> Diagnostic:
        record: dict[str, object] = {
            "severity": "error",
            "message": "alpha: rules/scoped-change.yaml matches no reachable node",
            "code": "rule.unmatched",
            "path": Path("rules/scoped-change.yaml"),
            "line": 4,
        }
        record.update(fields)
        return Diagnostic(**record)

    def test_the_same_finding_reported_twice_is_kept_once(self):
        collector = Diagnostics()

        collector.add([self.finding(), self.finding()])

        self.assertEqual([self.finding()], collector.records)

    def test_findings_differing_in_any_identity_field_are_both_kept(self):
        # One case per field Diagnostic.key names, because a collector that
        # compared any smaller set would silently drop the second finding.
        for field, other in (
            ("severity", "warning"),
            ("message", "alpha: rules/scoped-change.yaml reached no node"),
            ("code", "rule.unlowered"),
            ("path", Path("rules/name-the-gap.yaml")),
            ("line", 9),
        ):
            with self.subTest(field=field):
                collector = Diagnostics()

                collector.add([self.finding(), self.finding(**{field: other})])

                self.assertEqual(2, len(collector.records))

    def test_a_finding_carries_its_code_when_rendered_as_one_string(self):
        finding = self.finding()
        rendered = finding.coded

        self.assertTrue(rendered.endswith("(rule.unmatched)"))
        self.assertEqual(finding.message, rendered.removesuffix(" (rule.unmatched)"))

    def test_a_finding_no_check_names_is_rendered_without_an_empty_code(self):
        finding = self.finding(code="")

        self.assertEqual(finding.message, finding.coded)


class CollectedFailureTests(unittest.TestCase):
    """A raise stands in for the report, so it owes the reader the same codes."""

    def test_a_clean_collector_raises_nothing(self):
        collector = Diagnostics()
        collector.warning("alpha: the rule matches nothing", "rule.unmatched")

        self.assertIsNone(collector.raise_if_errors())

    def test_one_collected_error_is_raised_carrying_its_check_code(self):
        collector = Diagnostics()
        collector.error("alpha: the rule reached no node", "rule.unlowered")

        with self.assertRaises(DegardisError) as raised:
            collector.raise_if_errors()

        self.assertEqual("rule.unlowered", raised.exception.code)
        self.assertEqual(collector.select("error")[0].message, str(raised.exception))

    def test_several_collected_errors_each_name_their_own_check(self):
        # One exception has room for one code, so the codes go inline instead:
        # an agent repairing the source still has every one to look up.
        collector = Diagnostics()
        collector.error("alpha: the rule reached no node", "rule.unlowered")
        collector.error("alpha: the entry names no step", "workflow.invalid-edge")

        with self.assertRaises(DegardisError) as raised:
            collector.raise_if_errors()

        lines = str(raised.exception).splitlines()
        self.assertEqual("2 errors:", lines[0])
        self.assertEqual(3, len(lines))
        for line, code in zip(lines[1:], ("rule.unlowered", "workflow.invalid-edge")):
            with self.subTest(code=code):
                self.assertTrue(line.endswith(f"({code})"))

    def test_a_collected_warning_never_becomes_a_failure(self):
        collector = Diagnostics()
        collector.warning("alpha: the rule matches nothing", "rule.unmatched")
        collector.error("alpha: the rule reached no node", "rule.unlowered")

        with self.assertRaises(DegardisError) as raised:
            collector.raise_if_errors()

        self.assertEqual("rule.unlowered", raised.exception.code)
        self.assertEqual(collector.select("error")[0].message, str(raised.exception))

class SourceFailureTests(unittest.TestCase):
    """Which check a failure raised instead of collected is reported under."""

    def test_a_source_error_keeps_its_own_check_and_line(self):
        collector = Diagnostics()
        failure = SourceError(
            "policies/a.yaml:4: summary is required",
            "policy.missing-summary",
            Path("policies/a.yaml"),
            4,
        )

        collector.source_failure(failure, Path("skill.yaml"), "manifest.unreadable")

        record = collector.select("error")[0]
        self.assertEqual("policy.missing-summary", record.code)
        self.assertEqual(Path("policies/a.yaml"), record.path)
        self.assertEqual(4, record.line)

    def test_a_failure_carrying_a_code_keeps_it_over_the_caller_fallback(self):
        """The raiser named the check that refused the source.

        Replacing it with the caller's fallback would send the reader to look
        up a check that is not the one that stopped them.
        """
        collector = Diagnostics()
        failure = DegardisError("Missing skill manifest", "manifest.missing")

        collector.source_failure(failure, Path("skill.yaml"), "manifest.unreadable")

        self.assertEqual("manifest.missing", collector.select("error")[0].code)

    def test_a_failure_no_check_named_falls_back_to_the_caller_code(self):
        collector = Diagnostics()

        collector.source_failure(
            OSError("device not ready"), Path("skill.yaml"), "manifest.unreadable"
        )

        self.assertEqual("manifest.unreadable", collector.select("error")[0].code)

