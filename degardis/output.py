"""Every writer: the person-facing reports, and the agent-facing line report.

Two audiences, two shapes. `list`, `validate`, and `build` are read by a person
at a terminal, so they wrap to a column width, name each field, and close with a
summary line. `inspect` is read by an AI agent running the installed CLI with no
README and no docs beside it, so it is line-oriented and terse: one fact per
line, prefixed by what the fact is about, with nothing spent on presentation.

`explain` serves whoever repairs a source, agent or author, and takes the
person-facing shape: every field it prints is prose, so every field wraps.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from textwrap import TextWrapper
from typing import Any, TextIO

from .content import CONTENT_KEYS
from .explain import CheckExplanation
from .model import Diagnostic


REPORT_WIDTH = 100
FIELD_WIDTH = 11


def _wrapped(prefix: str, text: str) -> list[str]:
    """One report value laid out under its label, continuation lines aligned.

    Every wrapped line in every person-facing report is produced here, so the
    column width and the decision not to break words or hyphenated terms are one
    fact rather than one per report. A label is written once and its continuation
    lines are indented to clear it, which is what lets a reader tell a wrapped
    value from the next field.
    """
    wrapper = TextWrapper(
        width=REPORT_WIDTH,
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
    lines = _wrapped(prefix, value.strip()) or [prefix.rstrip()]
    print("\n".join(lines), file=stream)


def _write_messages(stream: TextIO, prefix: str, messages: list[str]) -> None:
    for message in messages:
        print("\n".join(_wrapped(prefix, message)), file=stream)


def _task_summary(result: dict[str, Any]) -> str:
    """The tasks a request can be routed to, in the order the router lists them."""
    tasks = result.get("tasks") or []
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
    records = [
        record
        for record in result.get("diagnostics", [])
        if isinstance(record, Diagnostic) and record.severity == severity
    ]
    if records:
        return [record.coded for record in records]
    key = "errors" if severity == "error" else "warnings"
    return [str(value) for value in result.get(key, [])]


def write_validation_report(
    stream: TextIO, results: list[dict], promoted_warnings: int = 0
) -> None:
    print("Validation", file=stream)
    print(file=stream)
    explainable = any(
        isinstance(record, Diagnostic) and record.code
        for result in results
        for record in result.get("diagnostics", [])
    )
    failed = 0
    error_count = 0
    warning_count = 0
    for result in results:
        title = str(result.get("title", result.get("name", "Skill")))
        name = str(result.get("name", "unknown"))
        errors = _reported(result, "error")
        warnings = _reported(result, "warning")
        if not errors:
            print(f"[PASS] {title} ({name})", file=stream)
        else:
            failed += 1
            error_count += len(errors)
            print(f"[FAIL] {title} ({name})", file=stream)
            for index, error in enumerate(errors, start=1):
                print("\n".join(_wrapped(f"       {index}. ", error)), file=stream)
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
        print(f"{note}.", file=stream)
    if explainable:
        print(
            "Run `degardis explain CODE [CODE ...]` for the checks behind the "
            "codes above.",
            file=stream,
        )
    elif not error_count and not warning_count:
        # A run with nothing to report is where a reader decides they are done,
        # and it is the one place the checks state what they did not cover.
        print(
            "A pass means these sources compile to a complete bundle whose links "
            "resolve, not that the skill guides an agent well.",
            file=stream,
        )


# --------------------------------------------------------------------------
# explain
# --------------------------------------------------------------------------


def write_check_explanations(
    stream: TextIO, rules: list[tuple[str, CheckExplanation]]
) -> None:
    """Explain each check code, in the same three fields wherever it has them.

    Every field is prose, so all three wrap like any other report value. A code
    whose impact already names the repair carries no resolution, and the field
    is then absent rather than empty: a heading over nothing reads as an
    explanation that was cut off. A blank line separates one code from the next.
    """
    for index, (code, explanation) in enumerate(rules):
        if index:
            print(file=stream)
        print(code, file=stream)
        print(file=stream)
        _write_field(stream, "Trigger", explanation.trigger)
        _write_field(stream, "Impact", explanation.impact)
        if explanation.resolution is not None:
            _write_field(stream, "Resolution", explanation.resolution)


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


def _columns(rows: list[tuple[str, ...]]) -> list[str]:
    """Align listing columns, leaving the last one ragged so nothing is padded."""
    if not rows:
        return []
    width = max(len(row) for row in rows)
    padded = [(*row, *([""] * (width - len(row)))) for row in rows]
    sizes = [max(len(row[index]) for row in padded) for index in range(width)]
    lines: list[str] = []
    for row in padded:
        cells = [
            value.ljust(sizes[index]) if index < width - 1 else value
            for index, value in enumerate(row)
        ]
        lines.append(" ".join(cells).rstrip())
    return lines


def _listed(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def _activated(items: list[dict[str, str]], name: str) -> list[str]:
    """Name each item, and the condition under which it applies where it has one.

    A task's principles and a principle's placements both read this way, so the
    suffix is written once: an agent that has learned to read `x when y` in one
    dimension reads it the same in the other.
    """
    return [
        item[name] + (f" when {item['activation']}" if item["activation"] else "")
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
    errors = sum(len(result.get("errors", [])) for result in results)
    warnings = sum(len(result.get("warnings", [])) for result in results)
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

    A dimension prints a heading, some free-form lines, or an aligned table, and
    nothing else. Holding those three operations here is what keeps a new
    dimension from inventing a fourth shape for the same report.
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
        self.rows(*_columns(rows))


def _write_skill_dimension(
    out: _Lines, result: dict[str, Any], dimensions: tuple[str, ...]
) -> None:
    """Identity, counts, and page sizes: the header every inspect run prints.

    The description is measured here rather than quoted, unless `identity` was
    asked for and is about to print it in full. An agent choosing what to read
    next needs to know a description is 400 characters long more often than it
    needs the characters.
    """
    counts = result["counts"]
    attention = result["attention"]
    heading = f"skill {result.get('name', 'unknown')} {result['version']} \"{result['title']}\""
    out.rows(heading.replace('  "', ' "'), f"root  {Path(result['source'])}")
    if "identity" not in dimensions:
        out.rows(f"desc  {len(str(result['description']))} chars")
    out.rows(
        f"tasks {_task_summary(result)}",
        "count "
        + ", ".join(
            f"{counts.get(key, 0)} {key}" for key in CONTENT_KEYS if counts.get(key)
        )
        or "count none",
        f"size  SKILL.md {attention['root_bytes']}B/{attention['root_budget']}B"
        f" | task pages {attention['task_pages']}"
        f" avg {attention['average_task_bytes']}B"
        f" max {attention['largest_task_bytes']}B/{attention['task_budget']}B"
        f" | principles {attention['principle_bytes']}B"
        f" max {attention['largest_principle_bytes']}B/{attention['principle_budget']}B"
        f" | guides {attention['guide_bytes']}B"
        f" max {attention['largest_guide_bytes']}B/{attention['guide_budget']}B"
        f" | facets {attention['facet_bytes']}B"
        f" max {attention['largest_facet_bytes']}B/"
        f"{attention['facet_budget']}B",
    )


def _write_identity_dimension(out: _Lines, result: dict[str, Any]) -> None:
    digest = result["source_fingerprint"]
    out.rows(
        "",
        f"desc  {result['description']}",
        f"why   {result['purpose']}",
        f"lic   {result['license'] or 'none'}",
        f"copy  {result['copyright'] or 'none'}",
        f"fmt   {result['format_version']}",
        f"hash  {digest['algorithm']}:{digest['digest'][:16]} "
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
            f"{row['id']} \"{row['title']}\" {row['page']} {row['bytes']}B "
            f"{row['knowledge']} knowledge",
            f"  goal {row['goal']}",
            *(f"  when {cue}" for cue in row["recognize"]),
        )
        if row["guides"]:
            out.rows("  guides " + _listed(row["guides"]))
        if row["principles"]:
            out.rows("  principles " + _listed(_activated(row["principles"], "id")))


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
                f"activation={row['activation'] or 'always'}",
                "-> "
                + (
                    _listed(_activated(row["placements"], "owner"))
                    if row["placements"]
                    else "-"
                ),
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
                (f"{row['activation']} " if row["activation"] else "")
                + "-> "
                + _listed([item["owner"] for item in row["owners"]]),
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
                f"\"{row['title']}\"",
                row["category"] or "-",
                f"{row['bytes']}B",
                row["description"] or "-",
            )
            for row in result["facets"]
        ]
    )


def _write_composition_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"composition {len(result['composition'])}")
    for row in result["composition"]:
        out.rows(
            f"{row['id']} -> {row['page']}",
            f"  direct      {_listed(row['direct'])}",
            f"  required    {_listed(row['required'])}",
            *(
                f"  {group['kind']:<11} {_listed(group['knowledge'])}"
                for group in row["groups"]
            ),
        )


def _write_quality_dimension(out: _Lines, result: dict[str, Any]) -> None:
    quality = result["quality"]
    out.rows(
        "",
        "quality",
        f"tasks {quality['tasks']} | knowledge {quality['knowledge_units']}",
        f"principles {quality['principles']}",
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
            f"  near-duplicate {row['left']} {row['right']} {row['similarity']}"
            for row in quality["near_duplicates"]
        ),
    )


def _write_outputs_dimension(out: _Lines, result: dict[str, Any]) -> None:
    out.section(f"outputs {len(result['outputs'])}")
    out.table(
        [(row["path"], f"{row['bytes']}B", row["mode"]) for row in result["outputs"]]
    )


def _write_diagnostics_dimension(out: _Lines, result: dict[str, Any]) -> None:
    records = [
        record for record in result["diagnostics"] if isinstance(record, Diagnostic)
    ]
    out.section(f"diagnostics {len(records)}")
    root = Path(result["source"])
    out.table(
        [
            (
                record.severity,
                record.code or "-",
                record.location(root),
                record.summary(str(result["name"])),
            )
            for record in records
        ]
    )


# One writer per dimension, so adding a dimension adds a function rather than a
# branch in a report that already writes eleven of them. This table is
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
        name = result.get("name", "unknown")
        texts = result.get("page_text") or {}
        for page in pages:
            print(file=stream)
            if page not in texts:
                print(f"=== {name} {page} unavailable", file=stream)
                continue
            print(f"=== {name} {page}", file=stream)
            for line in str(texts[page]).splitlines():
                print(f"  {line}", file=stream)
