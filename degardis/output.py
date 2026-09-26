"""Every writer: the person-facing reports, and the agent-facing line report.

Two audiences, two shapes. `list`, `validate`, and `build` are read by a person
at a terminal, so they wrap to a column width, name each field, and close with a
summary line. `inspect` is read by an AI agent running the installed CLI with no
README and no docs beside it, so it is line-oriented and terse: one fact per
line, prefixed by what the fact is about, with nothing spent on presentation.

`explain` and `manual` print prose and nothing else, so neither wraps it: each
field and each paragraph is one line. A person's console, viewer, or editor
then wraps it to its own width, and an agent reads no whitespace that exists
only for a column neither of them has.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from textwrap import TextWrapper
from typing import Any, TextIO

from .content import CONTENT_KEYS
from .explain import CheckExplanation
from .markdown import unwrap_paragraphs


REPORT_WIDTH = 100
FIELD_WIDTH = 11

# Below this a label and its value no longer share a line in any useful way, so a
# narrower terminal gets this width and wraps what is left over itself.
MIN_REPORT_WIDTH = 40


def _is_terminal(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def encode_as_utf8(stream: TextIO) -> None:
    """Make redirected output UTF-8 on every host, leaving a terminal as it is.

    Python encodes a redirected stream in the locale's encoding, which on
    Windows is an ANSI code page such as cp1252, so an em dash in a manual topic
    or an authored field reaches a pipe as a byte a UTF-8 reader cannot decode.
    An agent reads `inspect` through a pipe, so those bytes are its interface,
    and like the report width they must not depend on the host that ran the
    command. A terminal keeps its encoding, because the terminal is what decodes
    it: Python already writes a Windows console as Unicode, and elsewhere the
    locale is the terminal's own. The error handler is kept, so only the
    encoding changes.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None or _is_terminal(stream):
        return
    reconfigure(encoding="utf-8", errors=stream.errors)


def report_width(stream: TextIO) -> int:
    """The column person-facing text on this stream wraps at.

    A terminal narrower than the report would break every long line a second
    time, mid-word, wherever its own edge fell, so a terminal gets its own width
    less one column (a line that fills the last column makes some consoles
    advance a row of their own). Anything that is not a terminal gets
    `REPORT_WIDTH`, so redirected output is the same bytes whatever window the
    command happened to run in.
    """
    if not _is_terminal(stream):
        return REPORT_WIDTH
    columns = shutil.get_terminal_size((REPORT_WIDTH + 1, 24)).columns - 1
    return max(MIN_REPORT_WIDTH, min(REPORT_WIDTH, columns))


def _wrapped(prefix: str, text: str, width: int) -> list[str]:
    """One report value laid out under its label, continuation lines aligned.

    Every wrapped line in every person-facing report is produced here, so the
    decision not to break words or hyphenated terms is one fact rather than one
    per report. A label is written once and its continuation lines are indented
    to clear it, which is what lets a reader tell a wrapped value from the next
    field.
    """
    wrapper = TextWrapper(
        width=width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapper.wrap(text)


def _write_field(
    stream: TextIO, label: str, value: str, width: int = FIELD_WIDTH
) -> None:
    prefix = f"  {label:<{width}} "
    lines = _wrapped(prefix, value.strip(), report_width(stream)) or [prefix.rstrip()]
    print("\n".join(lines), file=stream)


def _write_messages(stream: TextIO, prefix: str, messages: list[str]) -> None:
    for message in messages:
        print("\n".join(_wrapped(prefix, message, report_width(stream))), file=stream)


def _write_prose(stream: TextIO, text: str) -> None:
    """One sentence or paragraph of a report's own, wrapped like its fields."""
    print("\n".join(_wrapped("", text, report_width(stream))), file=stream)


def _task_summary(result: dict[str, Any]) -> str:
    """The tasks a request can be routed to, in the order the router lists them."""
    tasks = result["tasks"]
    if not tasks:
        return "None"
    return ", ".join(str(task["id"]) for task in tasks)


def _counted(count: int, noun: str) -> str:
    """Render a summary count so a single item does not read as a plural."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------


def write_skill_list(stream: TextIO, results: list[dict[str, Any]]) -> None:
    print(f"Skills ({len(results)})", file=stream)
    for result in results:
        counts = result["counts"]
        print(file=stream)
        print(
            f"{result['title']} ({result['name']})  v{result['version']}",
            file=stream,
        )
        _write_field(stream, "Description", result["description"] or "Not specified")
        _write_field(stream, "Tasks", _task_summary(result))
        _write_field(
            stream,
            "Sources",
            ", ".join(
                f"{counts.get(key, 0)} {key}"
                for key in CONTENT_KEYS
                if counts.get(key, 0)
            )
            or "None",
        )
        _write_field(
            stream,
            "Facets",
            ", ".join(facet["id"] for facet in result["facets"]) or "None",
        )
        _write_field(stream, "Scripts", "Yes" if counts.get("scripts") else "No")
        _write_field(stream, "License", result["license"] or "Not specified")
        _write_field(stream, "Copyright", result["copyright"] or "Not specified")
        _write_field(stream, "Source", str(Path(result["source"]).resolve()))


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def _reported(result: dict, severity: str) -> list[str]:
    """One skill's findings of one severity, each naming the check that found it.

    The check code is what `degardis explain` takes, so a reader can ask why a
    finding matters without leaving the report.
    """
    return [
        record.coded
        for record in result["diagnostics"]
        if record.severity == severity
    ]


def write_validation_report(
    stream: TextIO, results: list[dict], promoted_warnings: int = 0
) -> None:
    print("Validation", file=stream)
    print(file=stream)
    explainable = any(
        record.code for result in results for record in result["diagnostics"]
    )
    failed = 0
    error_count = 0
    warning_count = 0
    for result in results:
        title = result["title"]
        name = result["name"]
        errors = _reported(result, "error")
        warnings = _reported(result, "warning")
        if not errors:
            print(f"[PASS] {title} ({name})", file=stream)
        else:
            failed += 1
            error_count += len(errors)
            print(f"[FAIL] {title} ({name})", file=stream)
            for index, error in enumerate(errors, start=1):
                _write_messages(stream, f"       {index}. ", [error])
        warning_count += len(warnings)
        _write_messages(stream, "       Warning: ", warnings)
    passed = len(results) - failed
    print(file=stream)
    print(
        (
            f"Summary: {passed} passed, {failed} failed, "
            f"{_counted(error_count, 'error')}, "
            f"{_counted(warning_count, 'warning')}, {len(results)} total."
        ),
        file=stream,
    )
    if promoted_warnings:
        note = (
            f"--fail-on-warning reported {_counted(promoted_warnings, 'warning')} as "
            + ("an error" if promoted_warnings == 1 else "errors")
        )
        if error_count <= promoted_warnings:
            note += "; the sources still build"
        _write_prose(stream, f"{note}.")
    if explainable:
        _write_prose(
            stream,
            "Run `degardis explain CODE [CODE ...]` for the checks behind the "
            "codes above.",
        )
    elif not error_count and not warning_count:
        # A run with nothing to report is where a reader decides they are done,
        # and it is the one place the checks state what they did not cover.
        _write_prose(
            stream,
            "A pass means these sources compile to a complete bundle whose links "
            "resolve, not that the skill guides an agent well.",
        )


# --------------------------------------------------------------------------
# explain
# --------------------------------------------------------------------------


def write_check_explanations(
    stream: TextIO, rules: list[tuple[str, CheckExplanation]]
) -> None:
    """Explain each check code, in the same three fields wherever it has them.

    Each field is one line under its label, left for the reader's window to
    wrap. A code whose impact already names the repair carries no resolution,
    and the field is then absent rather than empty: a heading over nothing reads
    as an explanation that was cut off. A blank line separates one code from the
    next.
    """
    fields = (("Trigger", "trigger"), ("Impact", "impact"), ("Resolution", "resolution"))
    for index, (code, explanation) in enumerate(rules):
        if index:
            print(file=stream)
        print(code, file=stream)
        print(file=stream)
        for label, name in fields:
            value = getattr(explanation, name)
            if value is not None:
                print(f"  {label:<{FIELD_WIDTH}} {' '.join(value.split())}", file=stream)


# --------------------------------------------------------------------------
# manual
# --------------------------------------------------------------------------


def write_markdown(stream: TextIO, text: str) -> None:
    """Print Markdown with each paragraph, list item, and quote on one line.

    The topics are hard-wrapped to the column their author's editor used, which
    is no reader's: a window of another width breaks those lines a second time,
    and an agent reads the breaks as whitespace. Folding leaves the wrapping to
    whatever displays the text. Code, tables, and headings, whose line breaks
    are part of what they say, are printed as written.
    """
    print(unwrap_paragraphs(text), file=stream)


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def write_build_report(
    stream: TextIO,
    skills: list,
    paths: list[Path],
    *,
    as_zip: bool,
    warnings: list[str] | None = None,
) -> None:
    print("Build", file=stream)
    print(file=stream)
    for skill, path in zip(skills, paths):
        print(f"[BUILT] {skill.title} ({skill.name})", file=stream)
        _write_field(stream, "Artifact", str(path.resolve()))
    messages = warnings or []
    if messages:
        print(file=stream)
        _write_messages(stream, "  Warning: ", messages)
    kind = "archive" if as_zip else "folder"
    if len(paths) != 1:
        kind += "s"
    subject = "skill" if len(paths) == 1 else "skills"
    print(file=stream)
    print(
        f"Summary: {len(paths)} {subject} built as {kind}, "
        f"{_counted(len(messages), 'warning')}.",
        file=stream,
    )


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------


def _listed(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def _scalar(value: object) -> str:
    """One value on one line, or `-` where the source states none.

    A value an author wrote may span lines, and an inspect row ends at the first
    newline, so its whitespace is folded rather than letting the rest of it read
    as rows of their own.
    """
    text = " ".join(str(value).split()) if value is not None else ""
    return text or "-"


def _activated(items: list[dict[str, str]]) -> list[str]:
    """Name each principle, with the condition it applies under where it has one."""
    return [
        item["id"] + (f" when {_scalar(item['activation'])}" if item["activation"] else "")
        for item in items
    ]


def write_inspect_report(
    stream: TextIO,
    results: list[dict],
    dimensions: tuple[str, ...],
    pages: Sequence[str] = (),
) -> None:
    """Report source intelligence for an AI agent, in as few tokens as it takes."""
    for index, result in enumerate(results):
        if index:
            print(file=stream)
        _write_inspect_skill(stream, result, dimensions)
    errors = sum(len(result["errors"]) for result in results)
    warnings = sum(len(result["warnings"]) for result in results)
    print(file=stream)
    print(
        f"{_counted(len(results), 'skill')}, {_counted(errors, 'error')}, "
        f"{_counted(warnings, 'warning')}",
        file=stream,
    )
    if pages:
        _write_inspect_pages(stream, results, pages)


class _Lines:
    """The writer every dimension prints through, so none of them holds a stream.

    A dimension prints a heading, some free-form lines, or a table, and nothing
    else. Holding those three operations here is what keeps a new dimension from
    inventing a fourth shape for the same report.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def rows(self, *lines: str) -> None:
        for line in lines:
            print(line, file=self._stream)

    def section(self, heading: str) -> None:
        """Open a dimension's block: a blank line, then what it is and how many."""
        self.rows("", heading)

    def table(self, rows: list[tuple[str, ...]]) -> None:
        """One row per line, its cells one space apart and never aligned.

        The reader pays for every space and has no eye for a column, so padding
        a cell to the widest one above it would be cost with no reader: each
        cell already says what it is by its position or its key.
        """
        self.rows(*(" ".join(row) for row in rows))


def _write_skill_dimension(
    out: _Lines, result: dict[str, Any], dimensions: tuple[str, ...]
) -> None:
    """Identity, counts, and page sizes: the header every inspect run prints.

    The description is measured here rather than quoted, unless `identity` was
    asked for and is about to print it in full. An agent choosing what to read
    next needs to know a description is 400 characters long more often than it
    needs the characters.

    A manifest too broken to load has no version, and the heading then leaves
    the field out rather than printing a gap where it would be.
    """
    counts = result["counts"]
    attention = result["attention"]
    identity = (result["name"], result["version"], f"\"{_scalar(result['title'])}\"")
    out.rows(
        "skill " + " ".join(part for part in identity if part),
        f"root {Path(result['source'])}",
    )
    if "identity" not in dimensions:
        out.rows(f"desc {len(str(result['description']))} chars")
    out.rows(
        "tasks " + _listed([str(task["id"]) for task in result["tasks"]]),
        "count "
        + _listed([f"{counts[key]} {key}" for key in CONTENT_KEYS if counts[key]]),
        f"size SKILL.md {attention['root_bytes']}B/{attention['root_budget']}B"
        f" {attention['root_lines']} lines"
        f" | register {attention['register_bytes']}B"
        f" | task pages {attention['task_pages']} {attention['task_bytes']}B"
        f" avg {attention['average_task_bytes']}B"
        f" max {attention['largest_task_bytes']}B/{attention['task_budget']}B"
        f" | principles {attention['principle_bytes']}B"
        f" max {attention['largest_principle_bytes']}B/{attention['principle_budget']}B"
        f" | guides {attention['guide_bytes']}B"
        f" max {attention['largest_guide_bytes']}B/{attention['guide_budget']}B"
        f" | facets {attention['facet_bytes']}B"
        f" index {attention['facet_index_bytes']}B"
        f" max {attention['largest_facet_bytes']}B/"
        f"{attention['facet_budget']}B",
    )


def _write_identity_dimension(out: _Lines, result: dict[str, Any]) -> None:
    digest = result["source_fingerprint"]
    out.rows(
        "",
        f"desc {_scalar(result['description'])}",
        f"why {_scalar(result['purpose'])}",
        f"lic {_scalar(result['license'])}",
        f"copy {_scalar(result['copyright'])}",
        f"fmt {_scalar(result['format_version'])}",
        f"hash {digest['algorithm']}:{digest['digest'][:16]} "
        f"({digest['files']} files)",
    )


def _write_sources_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"sources {len(result['sources'])}")
    out.table(
        [
            (row["kind"], row["id"] or "-", row["path"], f"{row['bytes']}B")
            for row in result["sources"]
        ]
    )


def _write_tasks_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"tasks {len(result['tasks'])}")
    for row in result["tasks"]:
        out.rows(
            f"{row['id']} \"{_scalar(row['title'])}\" {row['page']} {row['bytes']}B "
            f"{row['knowledge']} knowledge",
            f"  goal {_scalar(row['goal'])}",
            *(f"  when {_scalar(cue)}" for cue in row["recognize"]),
        )
        if row["guides"]:
            out.rows("  guides " + _listed(row["guides"]))
        if row["principles"]:
            out.rows("  principles " + _listed(_activated(row["principles"])))
        if row["linked"]:
            out.rows("  linked " + _listed(row["linked"]))


def _write_knowledge_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"knowledge {len(result['knowledge'])}")
    out.table(
        [
            (
                row["id"],
                f"kind={row['kind']}",
                f"{row['bytes']}B",
                f"requires={_listed(row['requires'])}",
                f"tasks={_listed(row['tasks'])}",
            )
            for row in result["knowledge"]
        ]
    )


def _write_principles_dimension(out: _Lines, result: dict[str, Any]) -> None:
    states = result["principles"]["states"]
    out.section(f"principles {len(states)}")
    out.table(
        [
            (
                row["id"],
                row["path"],
                f"{row['bytes']}B",
                f"activation={_scalar(row['activation'] or 'always')}",
                "-> "
                + (
                    _listed([item["owner"] for item in row["placements"]])
                    if row["placements"]
                    else "-"
                ),
                f"linked={_listed(row['linked'])}",
                f"page={row['page']}",
            )
            for row in states
        ]
    )


def _write_guides_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"guides {len(result['guides'])}")
    out.table(
        [
            (
                row["id"],
                row["path"],
                f"{row['bytes']}B",
                (f"{_scalar(row['activation'])} " if row["activation"] else "")
                + "-> "
                + _listed([item["owner"] for item in row["owners"]])
                + f" linked={_listed(row['linked'])}",
            )
            for row in result["guides"]
        ]
    )


def _write_facets_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"facets {len(result['facets'])}")
    out.table(
        [
            (
                row["id"],
                f"\"{_scalar(row['title'])}\"",
                _scalar(row["category"]),
                f"{row['bytes']}B",
                f"linked={_listed(row['linked'])}",
                _scalar(row["description"]),
            )
            for row in result["facets"]
        ]
    )


def _write_copied_dimension(out: _Lines, result: dict[str, Any], key: str) -> None:
    rows = result[key]
    out.section(f"{key} {len(rows)}")
    out.table(
        [
            (
                row["id"],
                row["path"],
                f"{row['bytes']}B",
                f"linked={_listed(row['linked'])}",
            )
            for row in rows
        ]
    )


def _write_scripts_dimension(out: _Lines, result: dict[str, Any]) -> None:
    _write_copied_dimension(out, result, "scripts")


def _write_assets_dimension(out: _Lines, result: dict[str, Any]) -> None:
    _write_copied_dimension(out, result, "assets")


def _write_composition_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"composition {len(result['composition'])}")
    for row in result["composition"]:
        out.rows(
            f"{row['id']} -> {row['page']}",
            f"  direct {_listed(row['direct'])}",
            f"  required {_listed(row['required'])}",
            *(
                f"  {group['kind']} {_listed(group['knowledge'])}"
                for group in row["groups"]
            ),
        )


def _write_quality_dimension(out: _Lines, result: dict[str, Any]) -> None:
    quality = result["quality"]
    out.rows(
        "",
        "quality",
        f"tasks {quality['tasks']} | knowledge {quality['knowledge_units']}"
        f" | principles {quality['principles']}",
        f"closure duplicated {quality['duplicated_bytes']}B"
        f" of {quality['unique_bytes']}B unique",
        f"constraint-ratio {quality['constraint_ratio']}",
        f"startup_bytes {quality['startup_bytes']}B"
        f" | headroom {quality['headroom']}B",
        f"orphan {_listed(quality['orphan_knowledge'])}",
        *(
            f"  minimum_read_bytes_by_task {task} {read_bytes}B"
            for task, read_bytes in quality["minimum_read_bytes_by_task"].items()
        ),
        *(
            f"  maximum_read_bytes_by_task {task} {read_bytes}B"
            for task, read_bytes in quality["maximum_read_bytes_by_task"].items()
        ),
        *(
            f"  near-duplicate {row['left']} {row['right']} {row['similarity']}"
            for row in quality["near_duplicates"]
        ),
    )


def _write_outputs_dimension(out: _Lines, result: dict[str, Any]) -> None:
    total = sum(row["bytes"] for row in result["outputs"])
    out.section(f"outputs {len(result['outputs'])} {total}B")
    out.table(
        [(row["path"], f"{row['bytes']}B", row["mode"]) for row in result["outputs"]]
    )


def _write_diagnostics_dimension(out: _Lines, result: dict[str, Any]) -> None:
    records = result["diagnostics"]
    out.section(f"diagnostics {len(records)}")
    root = Path(result["source"])
    out.table(
        [
            (
                record.severity,
                record.code or "-",
                record.location(root),
                _scalar(record.summary(str(result["name"]))),
            )
            for record in records
        ]
    )


# One writer per dimension, so adding a dimension adds a function rather than a
# branch in a report that already writes a dozen of them. This table is
# `INSPECT_DIMENSIONS` less `skill`, in that order and no other, which is the
# order the bundle is read in: the root, the task it routes to, then the pages
# that task opens. `skill` is not in the table because it reads the selection
# rather than a row: it prints the description's length only when `identity` is
# not about to print the description itself.
_INSPECT_WRITERS: dict[str, Callable[[_Lines, dict[str, Any]], None]] = {
    "identity": _write_identity_dimension,
    "sources": _write_sources_dimension,
    "tasks": _write_tasks_dimension,
    "knowledge": _write_knowledge_dimension,
    "principles": _write_principles_dimension,
    "guides": _write_guides_dimension,
    "facets": _write_facets_dimension,
    "scripts": _write_scripts_dimension,
    "assets": _write_assets_dimension,
    "composition": _write_composition_dimension,
    "quality": _write_quality_dimension,
    "outputs": _write_outputs_dimension,
    "diagnostics": _write_diagnostics_dimension,
}


def _write_inspect_skill(
    stream: TextIO, result: dict[str, Any], dimensions: tuple[str, ...]
) -> None:
    """Write one skill's selected dimensions, in this module's fixed block order.

    The order is the writer table's rather than the request's, so two runs
    asking for the same dimensions in different words print the same report.
    """
    out = _Lines(stream)
    _write_skill_dimension(out, result, dimensions)
    for name, writer in _INSPECT_WRITERS.items():
        if name in dimensions:
            writer(out, result)


def _write_inspect_pages(
    stream: TextIO, results: list[dict[str, Any]], pages: Sequence[str]
) -> None:
    """Dump the requested generated pages, each named by its skill and path.

    A page is printed per skill rather than once, because two skills generate
    different text at the same bundle path, and an agent reading this asked for
    the page of a source rather than for a path. A skill that generates no such
    page says so, so a silence cannot be read as an empty page.
    """
    for result in results:
        name = result["name"]
        texts = result["page_text"]
        for page in pages:
            print(file=stream)
            if page not in texts:
                print(f"=== {name} {page} unavailable", file=stream)
                continue
            print(f"=== {name} {page}", file=stream)
            for line in str(texts[page]).splitlines():
                print(f"  {line}", file=stream)
