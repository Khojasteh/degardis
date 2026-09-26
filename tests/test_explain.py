"""The explain command, and its table's coverage of every reported code."""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from unittest.mock import patch

import yaml

from degardis.cli import main, parser
from degardis.content import ALLOWED_CONTENT_KEYS
from degardis.model import CURRENT_FORMAT_VERSION
from degardis.explain import (
    CODES_DIR,
    WORDING,
    _read,
    _versions,
    checks,
    explanation,
    known_codes,
)
from degardis.registry import INTERFACE_FIELDS, MANIFEST_FIELDS
from degardis.render import (
    PRINCIPLE_BUDGET_BYTES,
    FACET_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
)
from degardis.sources import (
    KNOWLEDGE_FIELDS,
    PRINCIPLE_FIELDS,
    FACET_FIELDS,
    GUIDE_FIELDS,
    TASK_FIELDS,
)

from tests.checkcodes import computed_code_arguments, emitted_check_codes
from tests.support import REPO_ROOT, run


SOURCE_FIELDS = frozenset().union(
    ALLOWED_CONTENT_KEYS,
    INTERFACE_FIELDS,
    KNOWLEDGE_FIELDS,
    MANIFEST_FIELDS,
    PRINCIPLE_FIELDS,
    FACET_FIELDS,
    GUIDE_FIELDS,
    TASK_FIELDS,
)


class ExplainCoverageTests(unittest.TestCase):
    def test_every_reported_check_code_has_an_explain_entry(self):
        self.assertEqual(
            set(),
            emitted_check_codes() - set(checks()),
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
            set(checks()) - emitted_check_codes(),
            "`degardis explain` entries for codes no check reports",
        )

    def test_check_codes_are_written_out_so_coverage_can_be_checked(self):
        self.assertEqual(
            [],
            computed_code_arguments(),
            "write each check code as a string literal, not as an expression",
        )

    def test_every_trigger_and_impact_is_a_finished_sentence(self):
        """Reading the table is what establishes both fields are present, since
        a code file stating neither cannot be read at all. What is left to hold
        is that each one is prose a reader can act on rather than a fragment or
        a placeholder that was never filled in."""
        unfinished = sorted(
            f"{code}.{field}"
            for code, entry in checks().items()
            for field in ("trigger", "impact")
            if not getattr(entry, field).endswith(".")
        )
        self.assertEqual([], unfinished, "these fields state no whole sentence")

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


class ExplainDataTests(unittest.TestCase):
    """The table is data, so these hold the data to what a reader is owed."""

    def codes_dir(self):
        return REPO_ROOT / "degardis" / CODES_DIR

    def test_the_directory_listing_is_the_vocabulary(self):
        """No catalog sits between a code and the file that explains it."""
        self.assertEqual(
            sorted(path.name.removesuffix(".yaml") for path in self.codes_dir().glob("*.yaml")),
            known_codes(),
        )
        self.assertEqual(
            [],
            [path.name for path in self.codes_dir().iterdir() if path.is_file() and path.suffix != ".yaml"],
            "the codes directory carries files that explain no code",
        )

    def test_extension_field_warnings_share_one_explanation(self):
        expected = {
            "task.unknown-field": "task",
            "knowledge.unknown-field": "knowledge unit",
            "principle.unknown-field": "principle",
            "facet.unknown-field": "facet",
            "guide.unknown-field": "guide",
        }
        for code, owner in expected.items():
            with self.subTest(code=code):
                data = yaml.safe_load(
                    (self.codes_dir() / f"{code}.yaml").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    {"wording": "extension-unknown-field", "owner": owner},
                    data,
                )

    def test_a_name_that_is_not_a_known_code_reads_no_file(self):
        """A code reaches the filesystem only after the listing recognizes it."""
        for name in ("../cli", "explain_wording", "manifest.invalid-type", ""):
            with self.subTest(name=name):
                self.assertIsNone(explanation(name))

    def test_an_explanation_may_have_no_resolution(self):
        """A check with no actionable repair should not invent one."""
        _read.cache_clear()
        self.addCleanup(_read.cache_clear)
        with patch(
            "degardis.explain._resource",
            return_value="trigger: The condition holds.\nimpact: It matters.\n",
        ):
            self.assertIsNone(_read("test.no-resolution").resolution)

    def test_no_explanation_reaches_a_reader_with_a_placeholder_unfilled(self):
        """An unfilled placeholder tells a reader to read what nothing states."""
        for code, entry in checks().items():
            for label in ("trigger", "impact", "resolution"):
                with self.subTest(code=code, label=label):
                    self.assertNotIn("{{", getattr(entry, label) or "")

    def test_a_resolution_is_a_sentence_or_two_of_prose(self):
        """The table is printed beside a report, not read as a document.

        A resolution that runs to a worked example is longer than the finding it
        repairs and outweighs the impact above it, so it is held to prose: one
        paragraph, ending as a sentence does.
        """
        stated = 0
        for code, entry in checks().items():
            if entry.resolution is None:
                continue
            stated += 1
            with self.subTest(code=code):
                self.assertNotIn("\n", entry.resolution)
                self.assertTrue(entry.resolution.endswith("."), entry.resolution)
                self.assertLessEqual(
                    len(re.findall(r"[.;] ", entry.resolution)), 1, entry.resolution
                )
        self.assertTrue(stated, "no code states a resolution")

    def test_a_shared_wording_carries_the_values_its_code_file_supplies(self):
        wording = yaml.safe_load((REPO_ROOT / "degardis" / WORDING).read_text(encoding="utf-8"))
        supplied = 0
        for path in sorted(self.codes_dir().glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if "wording" not in data:
                continue
            supplied += 1
            self.assertIn(data["wording"], wording, path.name)
            entry = _read(path.name.removesuffix(".yaml"))
            for name, value in data.items():
                if name in ("wording", "resolution"):
                    continue
                with self.subTest(code=path.name, value=name):
                    self.assertIn(value, entry.trigger + entry.impact)
        self.assertTrue(supplied, "no code file names a shared wording")

    def test_every_shared_wording_is_named_by_some_code(self):
        """An unused wording is prose no `degardis explain` run can print."""
        wording = yaml.safe_load((REPO_ROOT / "degardis" / WORDING).read_text(encoding="utf-8"))
        named = {
            yaml.safe_load(path.read_text(encoding="utf-8")).get("wording")
            for path in self.codes_dir().glob("*.yaml")
        }
        self.assertEqual(set(), set(wording) - named)

    def test_a_resolution_naming_the_format_version_tracks_the_one_enforced(self):
        """A printed resolution must not drift from the accepted format."""
        for entry in (_read, _versions):
            entry.cache_clear()
        self.addCleanup(_read.cache_clear)
        self.addCleanup(_versions.cache_clear)
        with patch("degardis.explain.CURRENT_FORMAT_VERSION", 999):
            obsolete = _read("manifest.obsolete-format_version")
            unsupported = _read("manifest.unsupported-format_version")
        for text in (obsolete.trigger, obsolete.resolution, unsupported.resolution):
            with self.subTest(text=text):
                self.assertIn("999", text)
                self.assertNotIn(str(CURRENT_FORMAT_VERSION), text)

    def test_budget_explanations_name_the_limits_the_compiler_enforces(self):
        budgets = {
            "render.root-budget": ROOT_BUDGET_BYTES,
            "render.task-budget": TASK_BUDGET_BYTES,
            "render.principle-budget": PRINCIPLE_BUDGET_BYTES,
            "render.guide-budget": GUIDE_BUDGET_BYTES,
            "render.facet-budget": FACET_BUDGET_BYTES,
        }
        for code, budget in budgets.items():
            with self.subTest(code=code):
                self.assertIn(f"{budget // 1024} KiB", _read(code).trigger)


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
                    [code for code in checks() if hyphenated in code],
                    f"a code hyphenates the source key {field}",
                )

    def test_the_code_naming_rule_is_stated_where_the_codes_are_listed(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            main(["explain", "interface.short-description-length"])

        report = " ".join(stderr.getvalue().split())
        self.assertIn("interface.short_description-length", report)


class ExplainCommandTests(unittest.TestCase):
    def test_explain_reports_one_code_without_reading_any_source(self):
        """An author looking a code up may have no readable source to point at,
        which is when they most need the explanation."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), patch(
            "degardis.cli.discover_skill_paths",
            side_effect=AssertionError("source read"),
        ):
            status = main(["explain", "manifest.unknown-principle"])

        report = stdout.getvalue()
        self.assertEqual(0, status)
        self.assertIn("manifest.unknown-principle", report)
        for label in ("Trigger", "Impact"):
            self.assertIn(label, report)

    def test_explain_prints_each_field_as_one_line_whatever_the_terminal(self):
        """A field is prose for the reader's window to wrap, so it is one line
        under its label at any width, and it states exactly what the table does.
        """
        code = "manifest.description-length"
        entry = checks()[code]
        _, piped, _ = run("explain", code)
        _, narrow, _ = run("explain", code, columns=60)
        self.assertEqual(piped, narrow)
        self.assertEqual(
            [
                code,
                "",
                f"  Trigger     {' '.join(entry.trigger.split())}",
                f"  Impact      {' '.join(entry.impact.split())}",
                f"  Resolution  {' '.join(entry.resolution.split())}",
            ],
            piped.splitlines(),
        )

    def test_the_list_of_known_codes_is_one_rule_and_one_line_per_namespace(self):
        _, _, piped = run("explain", "yaml.no-such-check")
        _, _, narrow = run("explain", "yaml.no-such-check", columns=60)
        self.assertEqual(piped, narrow)
        lines = piped.splitlines()
        self.assertTrue(lines[1].startswith("A code is"))
        self.assertTrue(lines[1].endswith("interface.short_description-length."))
        listing = lines[lines.index("Known check codes:") + 1 :]
        namespaces = [line.split(".", 1)[0].strip() for line in listing]
        self.assertEqual(sorted(set(namespaces)), namespaces)
        self.assertEqual(
            sorted(known_codes()),
            sorted(code for line in listing for code in line.strip().split(", ")),
        )

    def test_explain_omits_the_resolution_of_a_code_that_states_none(self):
        """An empty heading reads as an explanation that was cut off."""
        code = "content.unknown-field"
        self.assertIsNone(checks()[code].resolution)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["explain", code])

        self.assertNotIn("Resolution", stdout.getvalue())

    def test_explain_reports_every_requested_code_in_one_run(self):
        codes = ["manifest.unknown-principle", "yaml.ambiguous-scalar", "icon.too-large"]
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
            status = main(["explain", "manifest.unknown-principle", "manifest.unknown-principle"])

        self.assertEqual(0, status)
        self.assertEqual(1, stdout.getvalue().count("  Trigger"))

    def test_explain_explains_known_codes_and_still_names_unknown_ones(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["explain", "manifest.unknown-principle", "yaml.no-such-check"])

        self.assertEqual(1, status)
        self.assertIn("manifest.unknown-principle", stdout.getvalue())
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
        for known in ("ambiguous-scalar", "unknown-principle"):
            self.assertIn(known, report)


if __name__ == "__main__":
    unittest.main()
