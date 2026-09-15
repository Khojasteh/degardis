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

from collections.abc import Sequence
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
            "Profiles",
            ", ".join(profile["id"] for profile in result["profiles"]) or "None",
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


def _write_inspect_skill(
    stream: TextIO, result: dict[str, Any], dimensions: tuple[str, ...]
) -> None:
    def section(*lines: str) -> None:
        for line in lines:
            print(line, file=stream)

    def table(rows: list[tuple[str, ...]]) -> None:
        section(*_columns(rows))

    name = str(result.get("name", "unknown"))
    counts = result["counts"]
    attention = result["attention"]
    heading = f"skill {name} {result['version']} \"{result['title']}\""
    section(heading.replace('  "', ' "'), f"root  {Path(result['source'])}")
    if "identity" not in dimensions:
        section(f"desc  {len(str(result['description']))} chars")
    section(
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
        f" | profiles {attention['profile_bytes']}B"
        f" | guides {attention['guide_bytes']}B"
        f" max {attention['largest_guide_bytes']}B/"
        f"{attention['guide_budget']}B",
    )

    if "identity" in dimensions:
        digest = result["source_fingerprint"]
        section(
            "",
            f"desc  {result['description']}",
            f"why   {result['purpose']}",
            f"lic   {result['license'] or 'none'}",
            f"copy  {result['copyright'] or 'none'}",
            f"fmt   {result['format_version']}",
            f"hash  {digest['algorithm']}:{digest['digest'][:16]} "
            f"({digest['files']} files)",
        )

    if "sources" in dimensions:
        section("", f"sources {len(result['sources'])}")
        table(
            [
                (row["kind"], row["id"] or "-", row["path"], f"{row['bytes']}B")
                for row in result["sources"]
            ]
        )

    if "tasks" in dimensions:
        section("", f"tasks {len(result['tasks'])}")
        for row in result["tasks"]:
            section(
                f"{row['id']} \"{row['title']}\" {row['page']} {row['bytes']}B "
                f"{row['knowledge']} knowledge"
            )
            section(f"  goal {row['goal']}")
            for cue in row["recognize"]:
                section(f"  when {cue}")
            if row["guides"]:
                section(
                    "  guides "
                    + _listed(
                        row["guides"]
                    )
                )
            if row["principles"]:
                section(
                    "  principles "
                    + _listed(
                        [
                            item["id"]
                            + (f" when {item['activation']}" if item["activation"] else "")
                            for item in row["principles"]
                        ]
                    )
                )

    if "knowledge" in dimensions:
        section("", f"knowledge {len(result['knowledge'])}")
        table(
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

    if "principles" in dimensions:
        placement = result["principles"]
        section("", f"principles {len(placement['states'])}")
        table(
            [
                (
                    row["id"],
                    row["path"],
                    f"{row['bytes']}B",
                    f"activation={row['activation'] or 'always'}",
                    "-> "
                    + (
                        _listed(
                            [
                                item["owner"]
                                + (
                                    f" when {item['activation']}"
                                    if item["activation"]
                                    else ""
                                )
                                for item in row["placements"]
                            ]
                        )
                        if row["placements"]
                        else "-"
                    ),
                    f"page={row['page']}",
                )
                for row in placement["states"]
            ]
        )

    if "guides" in dimensions:
        section("", f"guides {len(result['guides'])}")
        table(
            [
                (
                    row["id"],
                    row["path"],
                    f"{row['bytes']}B",
                    (f"{row['activation']} " if row["activation"] else "")
                    + "-> "
                    + _listed([item["task"] for item in row["tasks"]]),
                )
                for row in result["guides"]
            ]
        )

    if "profiles" in dimensions:
        section("", f"profiles {len(result['profiles'])}")
        table(
            [
                (
                    row["id"],
                    f"\"{row['title']}\"",
                    row["category"] or "-",
                    f"{row['bytes']}B",
                    row["description"] or "-",
                )
                for row in result["profiles"]
            ]
        )

    if "composition" in dimensions:
        section("", f"composition {len(result['composition'])}")
        for row in result["composition"]:
            section(f"{row['id']} -> {row['page']}")
            section(f"  direct      {_listed(row['direct'])}")
            section(f"  required    {_listed(row['required'])}")
            for group in row["groups"]:
                section(f"  {group['kind']:<11} {_listed(group['knowledge'])}")

    if "quality" in dimensions:
        quality = result["quality"]
        section(
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
        )
        for task, read_bytes in quality["minimum_read_bytes_by_task"].items():
            section(f"  minimum_read_bytes_by_task {task} {read_bytes}B")
        for row in quality["near_duplicates"]:
            section(f"  near-duplicate {row['left']} {row['right']} {row['similarity']}")

    if "outputs" in dimensions:
        section("", f"outputs {len(result['outputs'])}")
        table(
            [
                (row["path"], f"{row['bytes']}B", row["mode"])
                for row in result["outputs"]
            ]
        )

    if "diagnostics" in dimensions:
        records = [
            record
            for record in result["diagnostics"]
            if isinstance(record, Diagnostic)
        ]
        section("", f"diagnostics {len(records)}")
        root = Path(result["source"])
        table(
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
