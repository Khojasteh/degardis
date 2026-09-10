"""The YAML profile Format 2 accepts, and what the loader refuses outside it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.model import SourceError
from degardis.yamlsource import load_yaml, yaml_scalar_warnings

from tests.support import write_text


class LoaderProfileTests(unittest.TestCase):
    """Format 2 accepts mappings, lists, strings, integers, finite numbers,
    booleans, and null. Everything else changes what the compiler reads from
    what the page shows, so the loader refuses it at the line that wrote it.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def load(self, text: str) -> dict:
        path = self.root / "source.yaml"
        write_text(path, text)
        return load_yaml(path)

    def refusal(self, text: str) -> SourceError:
        with self.assertRaises(SourceError) as raised:
            self.load(text)
        return raised.exception

    def test_accepts_the_profile(self):
        loaded = self.load(
            "name: alpha\ncount: 2\nratio: 1.5\nflag: true\nempty: null\n"
            "items:\n- one\n- two\nnested:\n  key: value\n"
        )
        self.assertEqual(
            {
                "name": "alpha",
                "count": 2,
                "ratio": 1.5,
                "flag": True,
                "empty": None,
                "items": ["one", "two"],
                "nested": {"key": "value"},
            },
            loaded,
        )

    def test_rejects_an_anchor(self):
        failure = self.refusal("first: &shared one\nsecond: two\n")
        self.assertEqual("source.rejected-yaml", failure.code)
        self.assertEqual(1, failure.line)

    def test_rejects_an_alias(self):
        failure = self.refusal("first: &shared one\nsecond: *shared\n")
        self.assertEqual("source.rejected-yaml", failure.code)

    def test_rejects_a_merge_key(self):
        failure = self.refusal("child:\n  <<: {a: 1}\n  b: 2\n")
        self.assertEqual("source.rejected-yaml", failure.code)
        self.assertEqual(2, failure.line)

    def test_rejects_a_custom_tag(self):
        self.assertEqual(
            "source.rejected-yaml", self.refusal("value: !!set {a, b}\n").code
        )

    def test_rejects_an_implicit_timestamp(self):
        failure = self.refusal("released: 2026-01-01\n")
        self.assertEqual("source.rejected-yaml", failure.code)

    def test_accepts_a_quoted_date(self):
        self.assertEqual({"released": "2026-01-01"}, self.load('released: "2026-01-01"\n'))

    def test_rejects_a_non_finite_number(self):
        for text in ("ratio: .inf\n", "ratio: -.inf\n", "ratio: .nan\n"):
            with self.subTest(text=text):
                self.assertEqual("source.rejected-yaml", self.refusal(text).code)

    def test_rejects_a_duplicate_key(self):
        failure = self.refusal("name: one\nname: two\n")
        self.assertEqual("source.rejected-yaml", failure.code)
        self.assertEqual(2, failure.line)

    def test_rejects_a_non_string_field_name(self):
        self.assertEqual("source.rejected-yaml", self.refusal("? [a, b]\n: value\n").code)

    def test_reads_a_field_name_as_the_text_on_the_page(self):
        """`on:` is a step form, and YAML 1.1 would read it as a boolean.

        A field name is always the text written for it, so a mapping key keeps
        its spelling whatever YAML's implicit resolver would make of the same
        characters in a value slot.
        """
        loaded = self.load("on:\n  completed: report\nno: keep\nyes: keep\n")
        self.assertEqual({"on", "no", "yes"}, set(loaded))

    def test_reports_an_unparsable_file_with_a_line(self):
        failure = self.refusal("items: [1, 2\n")
        self.assertEqual("source.invalid-yaml", failure.code)
        self.assertEqual(1, failure.line)

    def test_reports_a_file_that_is_not_a_mapping(self):
        self.assertEqual("source.invalid-yaml", self.refusal("- one\n- two\n").code)

    def test_reports_an_unreadable_file(self):
        with self.assertRaises(SourceError) as raised:
            load_yaml(self.root / "absent.yaml")
        self.assertEqual("source.unreadable", raised.exception.code)


class ScalarWarningTests(unittest.TestCase):
    """A value that loads exactly as YAML says and still surprises its author."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "source.yaml"

    def warnings(self, text: str) -> set[str]:
        write_text(self.path, text)
        return {record.code for record in yaml_scalar_warnings(self.path)}

    def test_warns_about_a_word_that_loads_as_a_boolean(self):
        for value in ("yes", "no", "on", "off"):
            with self.subTest(value=value):
                self.assertEqual(
                    {"yaml.ambiguous-scalar"}, self.warnings(f"prefer: {value}\n")
                )

    def test_leaves_the_canonical_spellings_alone(self):
        """The format accepts booleans and null, and these are how they are
        spelled, so warning about them would tell an author to quote the value
        they meant."""
        self.assertEqual(set(), self.warnings("flag: true\nother: false\nempty: null\n"))

    def test_warns_about_a_number_that_loses_its_formatting(self):
        self.assertEqual({"yaml.numeric-scalar"}, self.warnings("version: 1.10\n"))
        self.assertEqual({"yaml.numeric-scalar"}, self.warnings("code: 007\n"))

    def test_warns_about_a_sexagesimal_shape(self):
        self.assertEqual({"yaml.sexagesimal-scalar"}, self.warnings("budget: 1:30\n"))

    def test_says_nothing_about_a_quoted_value(self):
        self.assertEqual(set(), self.warnings('prefer: "no"\nversion: "1.10"\n'))


if __name__ == "__main__":
    unittest.main()
