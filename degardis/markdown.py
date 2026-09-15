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
written as its own document becomes a section of a task page, a link written
beside its author's file has to still resolve from wherever the text landed, and
a paragraph the author hard-wrapped to their own column has to stop imposing that
column on a reader who is not in that editor. All three are pure text transforms
with no judgement in them, which is what makes them safe to do to prose nobody
reviewed afterwards.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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

# An inline link or image, which is the only form whose target this module
# rewrites. A bare path in prose is left alone: it was written as text, and
# rewriting text a reader was meant to read would change the author's words.
MARKDOWN_LINK = re.compile(r"(?P<bang>!?)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)(?P<tail>(?:\s+\"[^\"]*\")?)\)")

# This is deliberately not Markdown syntax.  It stays visible in source, so an
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

    @property
    def directory(self) -> str:
        """The relative directory the file sits in, which is what names its type."""
        return self.path.parent.name


def read_markdown(path: Path) -> MarkdownSource:
    """Split one source file on disk into its frontmatter fields and its body."""
    return parse_markdown(read_source_text(path), path)


def parse_optional_frontmatter(text: str, path: Path) -> MarkdownSource | None:
    """Read a frontmatter block only when one opens the Markdown document.

    Guides are ordinary Markdown unless they opt into frontmatter. Opting in
    still has to mean valid source YAML, but the compiler consumes none of its
    fields and removes the block before shipping the guide.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != FRONT_MATTER_FENCE:
        return None
    return parse_markdown(text, path)


def parse_markdown(text: str, path: Path) -> MarkdownSource:
    """Split Markdown text into its frontmatter fields and its Markdown body.

    A file with no frontmatter is refused rather than read as a body with no
    fields. Every construct this format defines requires at least a title, so a
    source without the block would fail on the first field anyway — and reporting
    the block is one repair, where reporting each absent field in turn is a list
    of repairs that all have the same fix.

    The text is taken from the caller rather than read here, because the shipped
    principles are package data rather than files on a source tree, and they have
    to be read under exactly the same rules as an author's own sources.
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


def _unwrap_lines(lines: list[str]) -> list[str]:
    """Fold one container's worth of lines, recursing into the containers in it."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            out.append(line)
            index += 1
        elif CODE_FENCE.match(line):
            index = _copy_fenced(lines, index, out)
        elif line.startswith(CODE_INDENT):
            index = _copy_indented(lines, index, out)
        elif _opens_table(lines, index):
            index = _copy_table(lines, index, out)
        elif (
            ATX_HEADING.match(line)
            or THEMATIC_BREAK.match(line)
            or LINK_DEFINITION.match(line)
        ):
            out.append(line)
            index += 1
        elif HTML_BLOCK.match(line):
            index = _copy_html(lines, index, out)
        elif BLOCK_QUOTE.match(line):
            index = _fold_quote(lines, index, out)
        elif LIST_ITEM.match(line):
            index = _fold_item(lines, index, out)
        else:
            index = _fold_paragraph(lines, index, out)
    return out


def _copy_fenced(lines: list[str], index: int, out: list[str]) -> int:
    """Copy a fenced block through its closing fence, its contents untouched."""
    match = CODE_FENCE.match(lines[index])
    assert match is not None
    fence = match.group("fence")
    out.append(lines[index])
    index += 1
    while index < len(lines):
        out.append(lines[index])
        index += 1
        if not _fence_state(out[-1], fence):
            break
    return index


def _copy_indented(lines: list[str], index: int, out: list[str]) -> int:
    while index < len(lines) and (
        not lines[index].strip() or lines[index].startswith(CODE_INDENT)
    ):
        out.append(lines[index])
        index += 1
    return index


def _copy_table(lines: list[str], index: int, out: list[str]) -> int:
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        out.append(lines[index])
        index += 1
    return index


def _copy_html(lines: list[str], index: int, out: list[str]) -> int:
    while index < len(lines) and lines[index].strip():
        out.append(lines[index])
        index += 1
    return index


def _fold_quote(lines: list[str], index: int, out: list[str]) -> int:
    """Fold what a blockquote holds under these same rules, then re-mark it.

    The marker comes off, what it held is folded as a document of its own, and
    the marker goes back on every line that comes out. Nesting therefore costs
    nothing here: an inner quote is the same call one level down.
    """
    held: list[str] = []
    while index < len(lines):
        line = lines[index]
        marker = BLOCK_QUOTE.match(line)
        if marker is not None:
            held.append(line[marker.end() :])
        elif not line.strip() or _opens_block(lines, index):
            break
        else:
            held.append(line.strip())
        index += 1
    out.extend(f"> {folded}" if folded else ">" for folded in _unwrap_lines(held))
    return index


def _fold_item(lines: list[str], index: int, out: list[str]) -> int:
    """Fold one list item, its marker kept and its continuation lines folded in.

    The item's content is dedented to its marker, folded as a document of its
    own, and re-indented under it, so a nested list or a second paragraph inside
    the item is handled by these same rules rather than by a case of its own.
    """
    match = LIST_ITEM.match(lines[index])
    assert match is not None
    marker = match.group(0)
    width = len(marker)
    held = [lines[index][match.end() :]]
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
            index = ahead
            continue
        if _indent_width(line) >= width:
            held.append(line[width:])
        elif LIST_ITEM.match(line) or _opens_block(lines, index):
            break
        else:
            held.append(line.strip())
        index += 1
    folded = _unwrap_lines(held)
    out.append(marker + folded[0] if folded and folded[0] else marker.rstrip())
    padding = " " * width
    out.extend(padding + line if line else "" for line in folded[1:])
    return index


def _fold_paragraph(lines: list[str], index: int, out: list[str]) -> int:
    """Fold one run of prose into one line, keeping the breaks its author wrote."""
    held: list[str] = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if held and (_opens_block(lines, index) or SETEXT_UNDERLINE.match(line)):
            break
        content = line.strip()
        held.append(content if held else " " * _indent_width(line) + content)
        index += 1
        if line.endswith(HARD_BREAK_SPACES):
            out.append(" ".join(held) + HARD_BREAK_SPACES)
            held = []
        elif content.endswith(HARD_BREAK_SLASH):
            out.append(" ".join(held))
            held = []
    if held:
        out.append(" ".join(held))
    return index


def first_heading(text: str) -> str | None:
    """The text of a Markdown document's first heading, or None where it has none.

    A generated link names the document it points at by the heading its author
    wrote, so a reader deciding whether to open it reads what it is rather than
    where it sits. The compiler invents no title for a file that states none,
    which is why this reports absence instead of falling back to something.

    Only an ATX heading counts, and only outside a leading frontmatter block and
    a fenced one: a `#` in the first is a YAML comment and in the second part of
    a sample, and neither is the document's name.
    """
    lines = text.splitlines()
    start = 0
    if lines and lines[0].rstrip() == FRONT_MATTER_FENCE:
        closing = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.rstrip() == FRONT_MATTER_FENCE
            ),
            None,
        )
        if closing is not None:
            start = closing + 1
    fence = ""
    for line in lines[start:]:
        fence = _fence_state(line, fence)
        if fence:
            continue
        match = ATX_HEADING.match(line)
        if match is None:
            continue
        title = match.group("rest").strip().rstrip("#").strip()
        if title:
            return title
    return None


def rewrite_links(
    body: str,
    source: Path,
    root: Path,
    page: str,
    targets: dict[str, str] | None = None,
) -> str:
    """Re-address every relative link so it still resolves from the rendered page.

    An author writes a link the way their editor resolves it: relative to the
    file they are writing. The compiler then moves that text to a page at a
    different depth, and every such link would break. Re-addressing is
    mechanical — resolve against the source file's directory, then express the
    same destination from the page's directory — and it changes only the target,
    never the link text a reader sees.

    A target that names a scheme, a network path, or an anchor is left exactly
    as written: none of them is a path into this bundle, so none of them moved.
    """
    try:
        here = PurePosixPath(source.relative_to(root).as_posix()).parent
    except ValueError:
        return body

    def resolved(match: re.Match[str]) -> str:
        target = match.group("target")
        if EXTERNAL_TARGET.match(target) or target.startswith("<"):
            return match.group(0)
        address, _, anchor = target.partition("#")
        if not address:
            return match.group(0)
        absolute = posixpath.normpath(posixpath.join(str(here), address))
        relative = relative_link((targets or {}).get(absolute, absolute), page)
        suffix = f"#{anchor}" if anchor else ""
        return (
            f"{match.group('bang')}[{match.group('text')}]"
            f"({relative}{suffix}{match.group('tail')})"
        )

    return MARKDOWN_LINK.sub(resolved, body)


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
    inline code are never candidates.  The caller owns target lookup because
    it knows which authored files will actually be present in this bundle.
    ``None`` keeps an unresolved token visible while validation reports it.
    """
    lines: list[str] = []
    fence = ""
    for line in body.splitlines(keepends=True):
        next_fence = _fence_state(line.rstrip("\r\n"), fence)
        if fence or next_fence or line.startswith(CODE_INDENT):
            lines.append(line)
            fence = next_fence
            continue
        lines.append(_resolve_inline_line(line, resolve))
        fence = next_fence
    return "".join(lines)


def inline_reference_targets(body: str) -> list[tuple[str, str]]:
    """List source tokens in prose for guide-consumption checks."""
    found: list[tuple[str, str]] = []
    resolve_inline_references(
        body,
        lambda kind, target: found.append((kind, target)) or None,
    )
    return found


def _resolve_inline_line(
    line: str, resolve: Callable[[str, str], str | None]
) -> str:
    """Replace tokens outside inline-code spans on one ordinary Markdown line."""
    spans: list[tuple[int, int]] = []
    opening: tuple[int, int] | None = None
    for match in re.finditer(r"`+", line):
        if opening is None:
            opening = (match.start(), len(match.group()))
        elif len(match.group()) == opening[1]:
            spans.append((opening[0], match.end()))
            opening = None

    def replacement(match: re.Match[str]) -> str:
        if any(start <= match.start() < end for start, end in spans) or _inside_link(
            line, match.start()
        ):
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


def link_targets(
    body: str,
    source: Path,
    root: Path,
    targets: dict[str, str] | None = None,
) -> list[str]:
    """Every bundle-relative path one body links to, for the checks that resolve them.

    A link is read from the author's file and reported as the bundle path it
    names, so a check can compare it against what the build actually ships
    without repeating how a relative path is resolved.
    """
    try:
        here = PurePosixPath(source.relative_to(root).as_posix()).parent
    except ValueError:
        return []
    found: list[str] = []
    for match in MARKDOWN_LINK.finditer(body):
        target = match.group("target")
        if EXTERNAL_TARGET.match(target) or target.startswith("<"):
            continue
        address = target.partition("#")[0]
        if not address:
            continue
        absolute = posixpath.normpath(posixpath.join(str(here), address))
        found.append((targets or {}).get(absolute, absolute))
    return found
