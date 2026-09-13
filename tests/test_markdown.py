"""Moving authored text without editing it: heading levels, references, and wrapping."""

from __future__ import annotations

import unittest
from pathlib import Path

from degardis.markdown import (
    internal_links,
    link_destinations,
    parse_markdown,
    relative_link,
    resolve_inline_references,
    shift_headings,
    unwrap_paragraphs,
)


ROOT = Path("/skill")
SOURCE = ROOT / "knowledge" / "surface.md"


class FrontMatterTests(unittest.TestCase):
    def parse(self, text: str):
        return parse_markdown(text, SOURCE)

    def test_fields_and_body_are_split_at_the_closing_fence(self):
        source = self.parse("---\ntitle: Surface\n---\n\nBody line.\n")
        self.assertEqual({"title": "Surface"}, source.fields)
        self.assertEqual("Body line.", source.body)
        self.assertEqual("surface", source.id)

    def test_an_empty_block_loads_as_no_fields_rather_than_as_a_failure(self):
        """The field checks name each absent field; a bare refusal names none."""
        self.assertEqual({}, self.parse("---\n---\n\nBody.\n").fields)

    def test_a_body_holding_its_own_fence_keeps_it(self):
        source = self.parse("---\ntitle: Surface\n---\n\nOne\n\n---\n\nTwo\n")
        self.assertEqual("One\n\n---\n\nTwo", source.body)

    def test_the_frontmatter_text_is_kept_beside_the_fields_it_loaded(self):
        """The scalar warnings read the text: by load time the word is gone."""
        source = self.parse("---\nready: no\n---\n\nBody.\n")
        self.assertEqual("ready: no", source.frontmatter)
        self.assertEqual({"ready": False}, source.fields)


class HeadingShiftTests(unittest.TestCase):
    def test_a_document_becomes_a_section_at_the_level_it_is_given(self):
        body = "# Top\n\ntext\n\n## Under\n"
        self.assertEqual("### Top\n\ntext\n\n#### Under\n".rstrip("\n"), shift_headings(body, 3).rstrip("\n"))

    def test_relative_depth_is_preserved(self):
        body = "## One\n\n#### Deep\n"
        shifted = shift_headings(body, 2).splitlines()
        self.assertEqual(["## One", "", "#### Deep"], shifted)

    def test_a_body_with_no_heading_is_returned_unchanged(self):
        body = "Just prose.\n\n- a bullet\n"
        self.assertEqual(body, shift_headings(body, 4))

    def test_a_heading_inside_a_fence_is_left_alone(self):
        """A heading in a sample is part of the sample, not of the document."""
        body = "# Top\n\n```markdown\n# Not a heading\n```\n\n## After\n"
        shifted = shift_headings(body, 3)
        self.assertIn("# Not a heading", shifted)
        self.assertIn("### Top", shifted)
        self.assertIn("#### After", shifted)

    def test_a_shift_stops_at_the_deepest_level_markdown_has(self):
        """Markdown has no seventh level, and seven hashes render as text."""
        shifted = shift_headings("# One\n\n###### Six\n", 4)
        self.assertNotIn("#######", shifted)
        self.assertIn("###### Six", shifted)

    def test_a_body_that_is_only_whitespace_is_returned_unchanged(self):
        self.assertEqual("", shift_headings("", 3))


class LinkTests(unittest.TestCase):
    """Which destinations an authored body links to, and which of them name a path."""

    def test_every_markdown_link_form_is_found(self):
        body = (
            "[a](a.md) and ![b](b.png) and [c](c.md 'title') and [d](d.md (title))\n"
            "and [e](<e file.md>) and [f][ref] and <a href=\"g.md\">g</a>.\n\n"
            "[ref]: f.md \"title\"\n"
        )
        self.assertEqual(
            ["a.md", "b.png", "c.md", "d.md", "e file.md", "g.md", "f.md"],
            link_destinations(body),
        )

    def test_a_label_holding_brackets_still_ends_in_its_destination(self):
        self.assertEqual(["x.md"], link_destinations("[Read [[task:review]]](x.md)"))

    def test_an_external_target_names_no_path(self):
        for target in ("https://example.test/x", "#anchor", "//host/x", "mailto:a@b.c"):
            with self.subTest(target=target):
                self.assertEqual([], internal_links(f"[x]({target})"))

    def test_a_path_is_internal_whatever_it_is_relative_to(self):
        body = "[a](other.md#part) and [b](../guides/list.md) and [c](/guides/x.md)"
        self.assertEqual(
            ["other.md#part", "../guides/list.md", "/guides/x.md"], internal_links(body)
        )

    def test_a_bare_path_in_prose_is_not_a_link(self):
        """It was written to be read, so it is text rather than a destination."""
        self.assertEqual([], internal_links("The file is at guides/list.md."))

    def test_text_that_only_resembles_a_definition_is_prose(self):
        self.assertEqual([], internal_links("[note]: see the list below\n"))

    def test_a_link_in_code_is_a_sample_rather_than_a_link(self):
        body = (
            "`[a](a.md)`\n\n```markdown\n[b](b.md)\n```\n\n    [c](c.md)\n\n"
            "- item\n\n      [d](d.md)\n"
        )
        self.assertEqual([], link_destinations(body))

    def test_a_link_in_nested_list_content_is_found(self):
        body = "- outer\n  - inner\n    - see [a](a.md)\n"
        self.assertEqual(["a.md"], internal_links(body))


class InlineReferenceTests(unittest.TestCase):
    def test_tokens_in_prose_are_offered_to_the_resolver(self):
        found: list[tuple[str, str]] = []
        text = resolve_inline_references(
            "See [[task:review]] and [[asset:logo.svg]].\n",
            lambda kind, target: found.append((kind, target)) or "LINK",
        )
        self.assertEqual("See LINK and LINK.\n", text)
        self.assertEqual([("task", "review"), ("asset", "logo.svg")], found)

    def test_a_note_suffix_is_not_an_inline_reference(self):
        text = "See [[task:review|note]].\n"
        self.assertEqual(text, resolve_inline_references(text, lambda *_: "LINK"))

    def test_tokens_in_code_remain_literal(self):
        text = (
            "`[[task:review]]`\n\n```markdown\n[[task:review]]\n```\n\n"
            "    [[task:review]]\n\n- item\n\n      [[task:review]]\n"
        )
        self.assertEqual(text, resolve_inline_references(text, lambda *_: "LINK"))

    def test_tokens_in_list_content_are_prose_however_deeply_it_is_indented(self):
        """Indentation that places text in a list is the list's, not code's."""
        text = (
            "- a\n  - b\n    - see [[task:review]]\n\n"
            "10. step\n\n    see [[task:review]]\n\n> - quoted\n>   - see [[task:review]]\n"
        )
        resolved = resolve_inline_references(text, lambda *_: "LINK")
        self.assertNotIn("[[", resolved)
        self.assertEqual(3, resolved.count("see LINK"))

    def test_tokens_inside_another_link_remain_literal(self):
        text = "[Read [[task:review]]](guide.md) and [guide]([[task:review]])."
        self.assertEqual(text, resolve_inline_references(text, lambda *_: "LINK"))


class RelativeLinkTests(unittest.TestCase):
    def test_a_target_beside_the_page_is_named_directly(self):
        self.assertEqual("other.md", relative_link("facets/other.md", "facets/index.md"))

    def test_a_target_above_the_page_climbs_out_of_its_directory(self):
        self.assertEqual("../guides/x.md", relative_link("guides/x.md", "tasks/t.md"))

    def test_a_page_at_the_root_names_its_target_as_it_stands(self):
        self.assertEqual("tasks/t.md", relative_link("tasks/t.md", "SKILL.md"))


class ParagraphFoldTests(unittest.TestCase):
    """Folding a wrap is reformatting: the words survive, the column does not."""

    def fold(self, body: str) -> list[str]:
        return unwrap_paragraphs(body).splitlines()

    def test_a_wrapped_paragraph_comes_out_as_one_line(self):
        body = "The material is the only\nauthority, and nothing\nelse enters.\n"
        self.assertEqual(
            ["The material is the only authority, and nothing else enters."],
            self.fold(body),
        )

    def test_two_paragraphs_stay_two_paragraphs(self):
        body = "One line\nwrapped.\n\nA second\none.\n"
        self.assertEqual(["One line wrapped.", "", "A second one."], self.fold(body))

    def test_a_body_that_is_only_whitespace_is_returned_unchanged(self):
        self.assertEqual("\n  \n", unwrap_paragraphs("\n  \n"))

    def test_a_fenced_block_keeps_every_line_it_was_written_with(self):
        """Its contents are a sample rather than prose, and a sample folded is a
        sample edited."""
        body = "Prose\nwrapped.\n\n```python\nfirst = 1\nsecond = 2\n```\n"
        self.assertEqual(
            ["Prose wrapped.", "", "```python", "first = 1", "second = 2", "```"],
            self.fold(body),
        )

    def test_an_indented_block_keeps_every_line_it_was_written_with(self):
        body = "Prose.\n\n    first = 1\n    second = 2\n"
        self.assertEqual(
            ["Prose.", "", "    first = 1", "    second = 2"], self.fold(body)
        )

    def test_a_table_keeps_its_rows_apart(self):
        """Its rows are a grid; a grid on one line is no longer a table."""
        body = "| Limit | Value |\n| --- | --- |\n| Turnaround | one day |\n"
        self.assertEqual(body.splitlines(), self.fold(body))

    def test_a_line_of_prose_carrying_a_pipe_is_still_prose(self):
        """A pipe alone does not make a table, so this paragraph still folds."""
        body = "Read stdout | wc -l\nfor the count.\n"
        self.assertEqual(["Read stdout | wc -l for the count."], self.fold(body))

    def test_a_heading_ends_the_paragraph_above_it(self):
        body = "Lead in\nwrapped.\n## Next\nMore\ntext.\n"
        self.assertEqual(
            ["Lead in wrapped.", "## Next", "More text."], self.fold(body)
        )

    def test_a_setext_underline_is_not_folded_into_what_it_underlines(self):
        body = "A heading\nspelled this way\n---\n"
        self.assertEqual(["A heading spelled this way", "---"], self.fold(body))

    def test_a_thematic_break_is_kept_as_the_break_it_is(self):
        body = "Above.\n\n***\n\nBelow.\n"
        self.assertEqual(["Above.", "", "***", "", "Below."], self.fold(body))

    def test_a_list_item_folds_under_its_own_marker(self):
        body = "- Do not raise a hedge\n  into a statement.\n- Do not merge\n  two sources.\n"
        self.assertEqual(
            [
                "- Do not raise a hedge into a statement.",
                "- Do not merge two sources.",
            ],
            self.fold(body),
        )

    def test_an_ordered_list_keeps_its_numbering(self):
        body = "1. List what the reader\n   must tell apart.\n2. Keep every\n   sentence.\n"
        self.assertEqual(
            ["1. List what the reader must tell apart.", "2. Keep every sentence."],
            self.fold(body),
        )

    def test_a_nested_list_keeps_the_indentation_that_nests_it(self):
        body = "- Outer item\n  wrapped.\n  - Inner item\n    wrapped.\n"
        self.assertEqual(
            ["- Outer item wrapped.", "  - Inner item wrapped."], self.fold(body)
        )

    def test_a_lazy_continuation_belongs_to_the_item_above_it(self):
        body = "- An item whose\nsecond line is not indented.\n"
        self.assertEqual(["- An item whose second line is not indented."], self.fold(body))

    def test_a_blockquote_folds_under_its_marker(self):
        body = "> The team opened by\n> discussing the date.\n>\n> They also\n> talked about hiring.\n"
        self.assertEqual(
            [
                "> The team opened by discussing the date.",
                ">",
                "> They also talked about hiring.",
            ],
            self.fold(body),
        )

    def test_a_nested_blockquote_keeps_both_markers(self):
        body = "> > An inner quote\n> > wrapped.\n"
        self.assertEqual(["> > An inner quote wrapped."], self.fold(body))

    def test_a_break_written_with_two_trailing_spaces_survives_the_fold(self):
        """It renders as a break, so it is the author's own rather than a wrap."""
        body = "First line.  \nSecond line\nwrapped.\n"
        self.assertEqual(["First line.  ", "Second line wrapped."], self.fold(body))

    def test_a_break_written_with_a_trailing_backslash_survives_the_fold(self):
        body = "First line.\\\nSecond line\nwrapped.\n"
        self.assertEqual(["First line.\\", "Second line wrapped."], self.fold(body))

    def test_a_link_definition_is_not_folded_into_the_line_below_it(self):
        body = "[home]: ../index.md\n[away]: ../other.md\n"
        self.assertEqual(body.splitlines(), self.fold(body))

    def test_a_link_a_wrap_split_in_two_becomes_one_link_again(self):
        """A destination broken across lines is one no link check could find."""
        body = "See the [worked\nexample](examples/worked.md).\n"
        self.assertEqual("See the [worked example](examples/worked.md).", unwrap_paragraphs(body))
        self.assertEqual(["examples/worked.md"], internal_links(body))

    def test_no_word_is_dropped_or_reordered(self):
        """A marker a fold no longer needs is the one thing that may go; every
        word the author wrote comes out, in the order they wrote it."""
        body = (
            "# Title\n\nA paragraph wrapped\nacross lines.\n\n- an item\n  wrapped\n\n"
            "> a quote\n> wrapped\n\n```\nsample line\n```\n"
        )

        def words(text: str) -> list[str]:
            return [word for word in text.split() if word != ">"]

        self.assertEqual(words(body), words(unwrap_paragraphs(body)))

if __name__ == "__main__":
    unittest.main()
