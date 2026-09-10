from __future__ import annotations

import contextlib
import io
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from degardis.cli import main
from degardis.model import CURRENT_FORMAT_VERSION
from degardis.manual import (
    CATALOG,
    TOPICS,
    TOPICS_PLACEHOLDER,
    Topic,
    read_topic,
    render_manual,
    render_topic,
    topic_anchor,
)
from tests.test_cli import run
from tools.generate_manual import TARGET, TEMPLATE, render


ROOT = Path(__file__).resolve().parents[1]


class ManualCommandTests(unittest.TestCase):
    def test_no_arguments_lists_topics_without_reading_a_skill(self):
        with patch("degardis.cli.discover_skill_paths", side_effect=AssertionError("source read")):
            status, stdout, stderr = run("manual")
        self.assertEqual((0, ""), (status, stderr))
        self.assertIn(f"format {CURRENT_FORMAT_VERSION}", stdout)
        for topic in TOPICS:
            self.assertIn(f"  {topic.name} ", stdout)
            self.assertIn(topic.summary, stdout)
        self.assertNotIn("| Field |", stdout)

    def test_multiple_topics_print_once_in_request_order(self):
        status, stdout, stderr = run("manual", "protocol", "yaml", "protocol")
        self.assertEqual((0, ""), (status, stderr))
        self.assertEqual(1, stdout.count("# Protocols\n"))
        self.assertLess(stdout.index("# Protocols\n"), stdout.index("# YAML"))
        self.assertIn("| `hooks` | Yes |", stdout)
        self.assertNotIn("# Workflows\n", stdout)

    def test_known_topics_survive_and_all_unknown_names_are_reported(self):
        status, stdout, stderr = run("manual", "missing-one", "protocol", "missing-two", "missing-one")
        self.assertEqual(1, status)
        self.assertIn("# Protocols\n", stdout)
        self.assertIn("Unknown manual topics: missing-one, missing-two\n", stderr)
        self.assertIn("Available topics:", stderr)
        self.assertIn("  content ", stderr)

    def test_topic_names_cannot_read_arbitrary_paths(self):
        status, stdout, stderr = run("manual", "../cli", "manual")
        self.assertEqual((1, ""), (status, stdout))
        self.assertIn("Unknown manual topics: ../cli, manual", stderr)

    def test_all_option_is_not_supported(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["manual", "--all"])
        self.assertEqual(2, raised.exception.code)

    def test_help_works_before_and_after_command(self):
        outputs = []
        for argv in (["-h", "manual"], ["manual", "-h"]):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
            self.assertEqual(0, raised.exception.code)
            outputs.append(stdout.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("TOPIC", outputs[0])
        self.assertNotIn("--all", outputs[0])

    def test_every_topic_is_readable_and_every_cross_reference_names_a_topic(self):
        for topic in TOPICS:
            with self.subTest(topic=topic.name):
                status, stdout, stderr = run("manual", topic.name)
                self.assertEqual((0, ""), (status, stderr))
                self.assertTrue(stdout.startswith("# "))
                self.assertNotIn("](#", stdout)
                self.assertNotIn("{{format_version}}", stdout)
                also = re.findall(r"^See also: (.+)\.$", stdout, re.M)
                self.assertEqual(", ".join(topic.related), also[0] if also else "")
                for name in re.findall(r"\(see ([\w-]+)\)", stdout) + list(topic.related):
                    self.assertIn(name, {item.name for item in TOPICS})

    def test_manifest_links_become_topic_names(self):
        status, stdout, _ = run("manual", "manifest")
        self.assertEqual(0, status)
        self.assertIn("Entrypoints (see entrypoints)", stdout)
        self.assertIn("Patterns (see content)", stdout)

    def test_yaml_examples_keep_their_indentation_and_content(self):
        for topic in TOPICS:
            with self.subTest(topic=topic.name):
                blocks = re.findall(r"```[^\n]*\n(.*?)\n```", read_topic(topic.name), re.S)
                _, stdout, _ = run("manual", topic.name)
                self.assertEqual(blocks, re.findall(r"```[^\n]*\n(.*?)\n```", stdout, re.S))

    def test_link_like_text_inside_fences_is_preserved(self):
        for marker in ("```", "~~~~"):
            body = f"## Example\n\n{marker}yaml\nvalue: '[link](#example)'\n{marker}\n\nRead [link](#example)."
            with self.subTest(marker=marker), patch("degardis.manual.TOPICS", (Topic("example", "Example"),)), patch("degardis.manual.read_topic", return_value=body):
                text = render_topic(Topic("example", "Example"))
            self.assertIn("value: '[link](#example)'", text)
            self.assertIn("Read link (see example).", text)

    def test_resource_read_failure_uses_the_cli_error_boundary(self):
        with patch("degardis.manual.read_topic", side_effect=OSError("missing resource")):
            status, stdout, stderr = run("manual", "protocol")
        self.assertEqual((1, ""), (status, stdout))
        self.assertIn("[ERROR] missing resource", stderr)


class ManualDocumentTests(unittest.TestCase):
    def test_document_is_generated_from_the_installed_topics(self):
        self.assertEqual(
            TARGET.read_text(encoding="utf-8"),
            render(),
            "Run: python -m tools.generate_manual",
        )

    def test_the_catalog_lists_each_topic_file_once(self):
        names = [topic.name for topic in TOPICS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            set(names),
            {path.stem for path in (ROOT / "degardis/manual_topics").glob("*.md")},
        )
        anchors = [topic_anchor(topic) for topic in TOPICS]
        self.assertEqual(len(anchors), len(set(anchors)))
        for topic in TOPICS:
            self.assertTrue(set(topic.related) <= set(names))

    def test_document_links_resolve_in_the_generated_manual(self):
        text = render()
        headings = re.findall(r"^#{1,3} (.+)$", text, re.M)
        anchors = {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}
        for anchor in re.findall(r"\]\(#([\w-]+)\)", text):
            self.assertIn(anchor, anchors)

    def test_the_catalog_carries_topics_and_no_document_prose(self):
        """A catalog entry names a topic the CLI prints, so prose cannot hide there."""
        catalog = yaml.safe_load((ROOT / "degardis/manual_topics" / CATALOG).read_text(encoding="utf-8"))
        self.assertEqual({"topics"}, set(catalog))

    def test_the_document_is_the_template_with_the_topics_substituted(self):
        """Front matter in the module would be prose no manual file could correct."""
        template = f"# Title\n\nWritten for format {{{{format_version}}}}.\n\n{TOPICS_PLACEHOLDER}\n\nTail.\n"
        document = render_manual(template)
        self.assertTrue(document.startswith(f"# Title\n\nWritten for format {CURRENT_FORMAT_VERSION}.\n\n"))
        self.assertTrue(document.endswith("\n\nTail.\n"))
        self.assertIn(read_topic(TOPICS[0].name), document)
        self.assertNotIn(TOPICS_PLACEHOLDER, document)

    def test_a_template_without_the_placeholder_is_refused(self):
        """Substituting nothing would generate a manual that states no topic."""
        with self.assertRaises(ValueError):
            render_manual("# Manual\n\nNothing to substitute.\n")

    def test_the_document_carries_the_sections_the_template_supplies(self):
        front = TEMPLATE.read_text(encoding="utf-8").partition(TOPICS_PLACEHOLDER)[0]
        document = TARGET.read_text(encoding="utf-8")
        topics = "".join(read_topic(topic.name) for topic in TOPICS)
        headings = [line for line in front.splitlines() if line.startswith("#")]
        self.assertTrue(document.startswith(headings[0] + "\n"))
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertIn(heading + "\n", document)
                self.assertNotIn(heading + "\n", topics)

    def test_a_withdrawn_topic_name_is_reported_like_any_other_unknown_one(self):
        """The authoring guide covers the smallest source; no topic repeats it."""
        status, stdout, stderr = run("manual", "minimal")
        self.assertEqual((1, ""), (status, stdout))
        self.assertIn("Unknown manual topics: minimal", stderr)
        self.assertNotIn("minimal", {topic.name for topic in TOPICS})

    def test_format_version_is_substituted_in_prose_and_examples(self):
        with patch("degardis.manual.CURRENT_FORMAT_VERSION", 999):
            document = render()
            _, stdout, _ = run("manual", "manifest")
        self.assertIn("source format 999", document)
        self.assertIn("format_version: 999", stdout)
        self.assertIn("The source format version: `999`", stdout)
