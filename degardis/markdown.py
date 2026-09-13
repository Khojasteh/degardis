"""Read one directory-backed Markdown source, and move its text without editing it.

Every source construct in this format is one Markdown file, and four facts about
it are settled by where it sits and how it opens rather than by anything it
declares:

    Type is directory. Identity is file stem. Metadata is frontmatter.
    Content is Markdown body.

So nothing here reads an `id` field, and the readers above refuse one: an id in
frontmatter is a second spelling of a name the filename already carries, and two
spellings can disagree. The stem is the identity, and it is the only one.

The rest of this module is the mechanical part of assembling a page out of files
the author wrote separately. A body keeps its own words — the compiler never
paraphrases, merges, or summarizes authored material — but it does move: a unit
written as its own document becomes a section of a task page, a reference to
another part of the skill becomes a link from wherever the text landed, and a
paragraph the author hard-wrapped to their own column has to stop imposing that
column on a reader who is not in that editor. All three are pure text transforms
with no judgment in them, which is what makes them safe to do to prose nobody
reviewed afterwards.

An authored Markdown link is never rewritten. One written by path would name a
file from where the author saved it, not from the page it lands on, so this
module finds those links for the check that refuses them, and bundle content is
linked by inline reference instead.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import SourceError
from .yamlsource import load_yaml_text, read_source_text


# The source format accepts both common filename spellings for a Markdown
# document. Every reader and renderer shares this set, so accepting a document
# also means treating it as Markdown after it is selected.
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

# The fence that opens and closes frontmatter. It has to be the first line of the
# file: a source whose fields begin three paragraphs down is a source whose
# fields a reader scrolling the directory cannot find.
FRONT_MATTER_FENCE = "---"

# A fenced code block, whose contents are text rather than Markdown structure. A
# heading inside one is part of a sample, and shifting it would edit the sample.
CODE_FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
ATX_HEADING = re.compile(r"^(?P<hashes>#{1,6})(?P<rest>[ \t].*|)$")

MAX_HEADING_LEVEL = 6

# The three ways Markdown gives a link a destination: the tail of an inline link
# or image, a reference definition standing on its own line, and an `href` or
# `src` in raw HTML. A destination is bare or in angle brackets and may hold one
# level of balanced parentheses; a title is quoted or parenthesized. A bare path
# in prose is none of these: it was written as text for a reader to read.
_DESTINATION = r"<[^<>\n]*>|(?:[^\s()<>\\]|\\.|\((?:[^\s()\\]|\\.)*\))*"
_TITLE = r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)"
INLINE_LINK_TAIL = re.compile(
    rf"\]\(\s*(?P<destination>{_DESTINATION})(?:\s+(?:{_TITLE}))?\s*\)"
)
REFERENCE_DEFINITION = re.compile(
    rf"^\s*(?:>\s*)*\[(?:[^\[\]\\]|\\.)+\]:\s*(?P<destination>{_DESTINATION})"
    rf"(?:\s+(?:{_TITLE}))?\s*$"
)
HTML_LINK = re.compile(
    r"<[A-Za-z][^<>]*?\s(?:href|src)\s*=\s*"
    r"(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s\"'<>`=]+))",
    re.IGNORECASE,
)

# This is deliberately not Markdown syntax. It stays visible in source, so an
# author can tell a compiler-owned reference from a link whose wording they
# supplied, while `[[` is unlikely to collide with prose or a host template.
INLINE_REFERENCE = re.compile(
    r"\[\[(?P<kind>[a-z][a-z-]*):"
    r"(?P<target>[^\]|]+)\]\]"
)

# A target nothing on disk answers for: another document's own address, a page
# anchor, or a scheme the bundle does not resolve.
EXTERNAL_TARGET = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")


@dataclass(frozen=True)
class MarkdownSource:
    """One Markdown source file, split into the two halves the format defines.

    `frontmatter` is kept beside the fields it loaded into, because the checks
    that warn about a value YAML quietly reinterprets read the text rather than
    the loaded value: by the time `yes` is a boolean, the word the author wrote
    is gone.
    """

    path: Path
    id: str
    fields: dict[str, Any]
    body: str
    frontmatter: str = ""


def read_markdown(path: Path) -> MarkdownSource:
    """Split one source file on disk into its frontmatter fields and its body."""
    return parse_markdown(read_source_text(path), path)


def parse_markdown(text: str, path: Path) -> MarkdownSource:
    """Split Markdown text into its frontmatter fields and its Markdown body.

    A file with no frontmatter is refused rather than read as a body with no
    fields. Every construct this format defines requires at least a title, so a
    source without the block would fail on the first field anyway — and reporting
    the block is one repair, where reporting each absent field in turn is a list
    of repairs that all have the same fix.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != FRONT_MATTER_FENCE:
        raise SourceError(
            f"{path}: the file does not open with a {FRONT_MATTER_FENCE} "
            "frontmatter block, which is where a source states its fields",
            "source.missing-frontmatter",
            path,
        )
    closing = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip() == FRONT_MATTER_FENCE
        ),
        None,
    )
    if closing is None:
        raise SourceError(
            f"{path}: the frontmatter block opened on line 1 is never closed; "
            f"end it with {FRONT_MATTER_FENCE} on its own line",
            "source.missing-frontmatter",
            path,
            1,
        )
    frontmatter = "\n".join(lines[1:closing])
    fields = load_yaml_text(frontmatter, path, line_offset=1)
    body = "\n".join(lines[closing + 1 :]).strip("\n")
    return MarkdownSource(
        path=path,
        id=path.stem,
        fields=fields,
        body=body,
        frontmatter=frontmatter,
    )


def _fence_state(line: str, fence: str) -> str:
    """Track whether a line opens or closes a fenced block, given the open fence."""
    match = CODE_FENCE.match(line)
    if match is None:
        return fence
    run = match.group("fence")
    if not fence:
        return run
    if run[0] == fence[0] and len(run) >= len(fence) and not match.group("info").strip():
        return ""
    return fence


def shift_headings(body: str, base: int) -> str:
    """Re-level a body's headings so its highest one sits at `base`.

    A unit is authored as a document of its own and rendered as a section of a
    page, so its headings have to sit under the heading the page gave it.
    Shifting is the whole of the change: the relative depth the author wrote is
    preserved, no heading text is touched, and a body with no heading at all is
    returned unchanged.

    A shift that would run past level six stops there. Markdown has no seventh
    level, so the alternative to flattening the deepest headings together is
    emitting `#######`, which renders as literal text rather than as a heading.
    """
    if not body.strip():
        return body
    lines = body.splitlines()
    fence = ""
    levels: list[int] = []
    for line in lines:
        fence = _fence_state(line, fence)
        if fence:
            continue
        match = ATX_HEADING.match(line)
        if match is not None:
            levels.append(len(match.group("hashes")))
    if not levels:
        return body
    delta = base - min(levels)
    if delta == 0:
        return body
    fence = ""
    shifted: list[str] = []
    for line in lines:
        fence = _fence_state(line, fence)
        match = None if fence else ATX_HEADING.match(line)
        if match is None:
            shifted.append(line)
            continue
        level = min(len(match.group("hashes")) + delta, MAX_HEADING_LEVEL)
        shifted.append("#" * max(level, 1) + match.group("rest"))
    return "\n".join(shifted)


# The block openers a paragraph may not be folded into. A line matching one of
# these starts something of its own, so the line before it ends its paragraph
# and the line itself is never appended to the one above.
BLOCK_QUOTE = re.compile(r"^ {0,3}> ?")
LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]+|$)")
THEMATIC_BREAK = re.compile(r"^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$")
LINK_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:")
HTML_BLOCK = re.compile(r"^ {0,3}<")

# The underline that makes the paragraph above it a heading. It ends that
# paragraph without being part of it, and a row of dashes reads as this here and
# as a thematic break elsewhere, which is why the two are told apart by what
# precedes them rather than by the line alone.
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")

# A table's alignment row. It is what tells a table header from a line of prose
# that happens to carry a pipe, and a table is emitted exactly as written: its
# rows are a grid, and a grid folded into one line is no longer a table.
TABLE_DELIMITER = re.compile(
    r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$"
)

# Indented code: four spaces or a tab, where a block begins. Inside a paragraph
# the same indent is a continuation line, which is why this is only ever tested
# at the start of a block.
CODE_INDENT = ("    ", "\t")

# The two ways a line break is the author's own rather than their editor's. Both
# render as a break, so both survive the fold and close the line they end.
HARD_BREAK_SPACES = "  "
HARD_BREAK_SLASH = "\\"


def unwrap_paragraphs(body: str) -> str:
    """Fold each hard-wrapped paragraph back into one line.

    An author wraps prose to whatever column their editor is set to, and without
    this that column travels with the text: a generated page carries breaks at
    eighty characters to a reader whose window is not eighty characters wide, and
    a reflowed paragraph shows up in a diff as every line changed. Folding is
    reformatting rather than editing. The words, their order, and the blocks they
    sit in all come out as the author wrote them; the only thing that moves is
    where the newlines inside a paragraph fall.

    What is not folded is the larger half of this function. A line break carries
    meaning nearly everywhere else in Markdown, so anything that is not running
    prose is emitted exactly as written: fenced and indented code, tables,
    headings, thematic breaks, link definitions, and raw HTML. A blockquote and a
    list item are containers rather than leaves, so what they hold is folded
    under these same rules and put back under its own marker. A break the author
    asked for - two trailing spaces, or a trailing backslash - is a break they
    wrote rather than a column they wrapped to, and it ends its line.
    """
    if not body.strip():
        return body
    return "\n".join(_unwrap_lines(body.splitlines()))


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip())


def _opens_block(lines: list[str], index: int) -> bool:
    """Whether the line at `index` begins a block rather than continuing prose.

    A paragraph ends before it, and it is never folded into the line above.
    """
    line = lines[index]
    return bool(
        ATX_HEADING.match(line)
        or CODE_FENCE.match(line)
        or THEMATIC_BREAK.match(line)
        or BLOCK_QUOTE.match(line)
        or LIST_ITEM.match(line)
        or LINK_DEFINITION.match(line)
        or HTML_BLOCK.match(line)
        or _opens_table(lines, index)
    )


def _opens_table(lines: list[str], index: int) -> bool:
    """Whether a table begins at `index`, read from its alignment row.

    A pipe alone does not make a table, and a row of dashes alone is a thematic
    break or a setext underline, so the two facts are required together: a line
    carrying a pipe whose next line aligns the columns, or the alignment row
    itself.
    """
    line = lines[index]
    if "|" not in line:
        return False
    if TABLE_DELIMITER.match(line):
        return True
    return index + 1 < len(lines) and TABLE_DELIMITER.match(lines[index + 1]) is not None


# The blocks whose lines are samples rather than prose.
_CODE_BLOCKS = frozenset({"fenced", "indented"})


@dataclass(frozen=True)
class _Block:
    """One block of a container's lines, from `start` up to `end`.

    A blockquote or a list item also carries what it holds: `held` is its
    content with the marker or the item's indentation taken off, and `origin`
    is the line of the container each held line came from, so a caller that
    reads the content as a document of its own can still say where in the
    container a finding sits. `marker` is a list item's marker as written.
    """

    kind: str
    start: int
    end: int
    held: tuple[str, ...] = ()
    origin: tuple[int, ...] = ()
    marker: str = ""


def _blocks(lines: list[str]) -> Iterator[_Block]:
    """Read one container's lines as the blocks they form, in order.

    This is the one reading of block structure in the compiler. Folding a
    paragraph and telling a sample from prose both depend on where each block
    begins and ends, and the same four spaces are an indented code block at the
    start of a document but a list item's own content inside one, so both
    answers come from this walk rather than from a line's prefix.
    """
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            block = _Block("blank", index, index + 1)
        elif CODE_FENCE.match(line):
            block = _Block("fenced", index, _fenced_end(lines, index))
        elif line.startswith(CODE_INDENT):
            block = _Block("indented", index, _indented_end(lines, index))
        elif _opens_table(lines, index):
            block = _Block("table", index, _table_end(lines, index))
        elif (
            ATX_HEADING.match(line)
            or THEMATIC_BREAK.match(line)
            or LINK_DEFINITION.match(line)
        ):
            block = _Block("line", index, index + 1)
        elif HTML_BLOCK.match(line):
            block = _Block("html", index, _html_end(lines, index))
        elif BLOCK_QUOTE.match(line):
            block = _quote(lines, index)
        elif LIST_ITEM.match(line):
            block = _item(lines, index)
        else:
            block = _Block("paragraph", index, _paragraph_end(lines, index))
        yield block
        index = block.end


def _fenced_end(lines: list[str], index: int) -> int:
    """The line after a fenced block's closing fence, or the end of the text."""
    match = CODE_FENCE.match(lines[index])
    assert match is not None
    fence = match.group("fence")
    end = index + 1
    while end < len(lines):
        end += 1
        if not _fence_state(lines[end - 1], fence):
            break
    return end


def _indented_end(lines: list[str], index: int) -> int:
    while index < len(lines) and (
        not lines[index].strip() or lines[index].startswith(CODE_INDENT)
    ):
        index += 1
    return index


def _table_end(lines: list[str], index: int) -> int:
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        index += 1
    return index


def _html_end(lines: list[str], index: int) -> int:
    while index < len(lines) and lines[index].strip():
        index += 1
    return index


def _paragraph_end(lines: list[str], index: int) -> int:
    """The line after one run of prose: a blank line, a block opener, or an underline."""
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip() or _opens_block(lines, end) or SETEXT_UNDERLINE.match(line):
            break
        end += 1
    return end


def _quote(lines: list[str], index: int) -> _Block:
    """One blockquote, with its markers taken off what it holds.

    A line without a marker still belongs to the quote while it continues the
    prose above it, which is Markdown's laziness rule; a blank line or a block
    opener ends the quote.
    """
    start = index
    held: list[str] = []
    origin: list[int] = []
    while index < len(lines):
        line = lines[index]
        marker = BLOCK_QUOTE.match(line)
        if marker is not None:
            held.append(line[marker.end() :])
        elif not line.strip() or _opens_block(lines, index):
            break
        else:
            held.append(line.strip())
        origin.append(index)
        index += 1
    return _Block("quote", start, index, tuple(held), tuple(origin))


def _item(lines: list[str], index: int) -> _Block:
    """One list item, its content dedented to the column its marker sets.

    A line indented to that column belongs to the item, blank lines between
    such lines included; a line that is not, and does not open a block, is a
    lazy continuation of the item's prose.
    """
    match = LIST_ITEM.match(lines[index])
    assert match is not None
    start = index
    marker = match.group(0)
    width = len(marker)
    held = [lines[index][match.end() :]]
    origin = [index]
    index += 1
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            ahead = index
            while ahead < len(lines) and not lines[ahead].strip():
                ahead += 1
            if ahead >= len(lines) or _indent_width(lines[ahead]) < width:
                break
            held.extend([""] * (ahead - index))
            origin.extend(range(index, ahead))
            index = ahead
            continue
        if _indent_width(line) >= width:
            held.append(line[width:])
        elif LIST_ITEM.match(line) or _opens_block(lines, index):
            break
        else:
            held.append(line.strip())
        origin.append(index)
        index += 1
    return _Block("item", start, index, tuple(held), tuple(origin), marker)


def _unwrap_lines(lines: list[str]) -> list[str]:
    """Fold one container's worth of lines, recursing into the containers in it.

    A blockquote's content is folded as a document of its own and the marker
    goes back on every line that comes out, so nesting costs nothing. A list
    item's content is folded the same way and re-indented under its marker, so
    a nested list or a second paragraph inside the item needs no case of its
    own.
    """
    out: list[str] = []
    for block in _blocks(lines):
        if block.kind == "quote":
            out.extend(
                f"> {folded}" if folded else ">"
                for folded in _unwrap_lines(list(block.held))
            )
        elif block.kind == "item":
            folded = _unwrap_lines(list(block.held))
            marker = block.marker
            out.append(marker + folded[0] if folded and folded[0] else marker.rstrip())
            padding = " " * len(marker)
            out.extend(padding + line if line else "" for line in folded[1:])
        elif block.kind == "paragraph":
            out.extend(_fold_paragraph(lines[block.start : block.end]))
        else:
            out.extend(lines[block.start : block.end])
    return out


def _fold_paragraph(lines: list[str]) -> list[str]:
    """Fold one run of prose into one line, keeping the breaks its author wrote."""
    out: list[str] = []
    held: list[str] = []
    for line in lines:
        content = line.strip()
        held.append(content if held else " " * _indent_width(line) + content)
        if line.endswith(HARD_BREAK_SPACES):
            out.append(" ".join(held) + HARD_BREAK_SPACES)
            held = []
        elif content.endswith(HARD_BREAK_SLASH):
            out.append(" ".join(held))
            held = []
    if held:
        out.append(" ".join(held))
    return out


def _code_lines(lines: list[str]) -> set[int]:
    """The lines of one container that belong to a code sample, by index."""
    code: set[int] = set()
    for block in _blocks(lines):
        if block.kind in _CODE_BLOCKS:
            code.update(range(block.start, block.end))
        elif block.held:
            code.update(block.origin[inner] for inner in _code_lines(list(block.held)))
    return code


def _code_spans(line: str) -> list[tuple[int, int]]:
    """Where each inline code span on one line starts and ends."""
    spans: list[tuple[int, int]] = []
    opening: tuple[int, int] | None = None
    for match in re.finditer(r"`+", line):
        if opening is None:
            opening = (match.start(), len(match.group()))
        elif len(match.group()) == opening[1]:
            spans.append((opening[0], match.end()))
            opening = None
    return spans


def link_destinations(body: str) -> list[str]:
    """Every destination a body's prose links to, in the order they appear.

    The body is read folded, so a link a hard wrap split in two is one link, and
    a link in fenced, indented, or inline code is part of a sample rather than a
    link. Angle brackets around a destination are delimiters, not part of it.
    """
    lines = unwrap_paragraphs(body).splitlines()
    code = _code_lines(lines)
    found: list[str] = []
    for index, line in enumerate(lines):
        if index in code:
            continue
        spans = _code_spans(line)
        definition = REFERENCE_DEFINITION.match(line)
        if definition is not None and not _in_spans(definition.start("destination"), spans):
            found.append(definition.group("destination"))
            continue
        for match in INLINE_LINK_TAIL.finditer(line):
            before = line[: match.start()]
            if not _in_spans(match.start(), spans) and before.count("[") > before.count("]"):
                found.append(match.group("destination"))
        for match in HTML_LINK.finditer(line):
            if not _in_spans(match.start(), spans):
                found.append(
                    match.group("double") or match.group("single") or match.group("bare")
                )
    return [target for target in map(_unbracketed, found) if target]


def _in_spans(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _unbracketed(destination: str) -> str:
    text = destination.strip()
    if text.startswith("<") and text.endswith(">"):
        return text[1:-1].strip()
    return text


def internal_links(body: str) -> list[str]:
    """Every destination in a body's prose that names a path rather than an address.

    A path is written from the author's file and read from the page the text
    lands on, so it names the wrong file there; bundle content is linked by
    inline reference, whose link the compiler writes from the page itself. A
    scheme, a network path, or an anchor on the same page is left to the author.
    """
    return [
        target for target in link_destinations(body) if not EXTERNAL_TARGET.match(target)
    ]


def relative_link(target: str, page: str) -> str:
    """Express one bundle path from the directory the page sits in.

    Every generated link is written this way, so a page that moves between
    directories needs no other part of the renderer to know it moved.
    """
    here = posixpath.dirname(page)
    if not here:
        return target
    return posixpath.relpath(target, here)


def resolve_inline_references(
    body: str, resolve: Callable[[str, str], str | None]
) -> str:
    """Expand compiler references in prose, leaving Markdown literals alone.

    A code sample often documents the token itself, so fenced, indented, and
    inline code are never candidates. What counts as indented code is read from
    the block structure, since a list item's content is indented too and is
    prose. The caller owns target lookup because it knows which authored files
    will actually be present in this bundle. `None` keeps an unresolved token
    visible while validation reports it.
    """
    code = _code_lines(body.splitlines())
    return "".join(
        line if index in code else _resolve_inline_line(line, resolve)
        for index, line in enumerate(body.splitlines(keepends=True))
    )


def inline_reference_targets(body: str) -> list[tuple[str, str]]:
    """List a body's inline references as the renderer will read them.

    The body is folded first, as the renderer folds it before resolving, so a
    reference counts here exactly where it resolves on a page.
    """
    found: list[tuple[str, str]] = []
    resolve_inline_references(
        unwrap_paragraphs(body),
        lambda kind, target: found.append((kind, target)) or None,
    )
    return found


def _resolve_inline_line(
    line: str, resolve: Callable[[str, str], str | None]
) -> str:
    """Replace tokens outside inline-code spans on one ordinary Markdown line."""
    spans = _code_spans(line)

    def replacement(match: re.Match[str]) -> str:
        if _in_spans(match.start(), spans) or _inside_link(line, match.start()):
            return match.group(0)
        resolved = resolve(match.group("kind"), match.group("target"))
        return resolved if resolved is not None else match.group(0)

    return INLINE_REFERENCE.sub(replacement, line)


def _inside_link(line: str, start: int) -> bool:
    """Whether a token sits in a Markdown link label or destination.

    Expanding there would create a nested link, which Markdown cannot represent.
    The opening bracket belonging to the token itself is excluded from the count.
    """
    prefix = line[: start - 1] if start and line[start - 1] == "[" else line[:start]
    label_depth = prefix.count("[") - prefix.count("]")
    if label_depth > 0:
        return True
    opening = prefix.rfind("](")
    return opening >= 0 and ")" not in prefix[opening + 2 :]
