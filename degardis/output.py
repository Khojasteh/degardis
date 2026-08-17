"""Every writer: the person-facing reports, and the agent-facing line report.

Two audiences, two shapes. `list`, `validate`, and `build` are read by a person
at a terminal, so they wrap to a column width, name each field, and close with a
summary line. `inspect` is read by an AI agent running the installed CLI with no
README and no docs beside it, so it is line-oriented and terse: one fact per
line, prefixed by what the fact is about, with nothing spent on presentation.

`explain` serves whoever repairs a source, agent or author, and sits between the
two: prose fields wrap, and the examples are indented verbatim because YAML
indentation is meaning.
"""

from __future__ import annotations

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
        _write_field(stream, "Workflow", result["primary_workflow"] or "Not specified")
        _write_field(
            stream,
            "Constructs",
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
            "A pass means these sources compile to a complete execution graph, "
            "not that the skill guides an agent well.",
            file=stream,
        )


# --------------------------------------------------------------------------
# explain
# --------------------------------------------------------------------------


def write_check_explanations(
    stream: TextIO, rules: list[tuple[str, CheckExplanation]]
) -> None:
    """Explain each check code, with its examples left exactly as written.

    Trigger and impact are prose and wrap like every other report field. The
    examples are YAML, where indentation is meaning, so they are indented as a
    block and never rewrapped. A blank line separates one code from the next, so
    an agent asking about several codes at once can split them on the code lines.
    """
    for index, (code, explanation) in enumerate(rules):
        if index:
            print(file=stream)
        print(code, file=stream)
        print(file=stream)
        _write_field(stream, "Trigger", explanation.trigger)
        _write_field(stream, "Impact", explanation.impact)
        for label, sample in (
            ("Failing", explanation.failing),
            ("Passing", explanation.passing),
        ):
            print(file=stream)
            print(f"  {label}", file=stream)
            for line in sample.splitlines():
                print(f"    {line}".rstrip(), file=stream)


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
    sizes = [
        max(len(row[index]) for row in padded) for index in range(width)
    ]
    lines: list[str] = []
    for row in padded:
        cells = [
            value.ljust(sizes[index]) if index < width - 1 else value
            for index, value in enumerate(row)
        ]
        lines.append(" ".join(cells).rstrip())
    return lines


def _nodes(labels: list[str]) -> str:
    return ", ".join(labels) if labels else "none"


def write_inspect_report(
    stream: TextIO,
    results: list[dict],
    dimensions: tuple[str, ...],
    body: bool = False,
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
    if body:
        _write_inspect_body(stream, results)


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
    heading = f"skill {name} {result['version']} \"{result['title']}\""
    section(heading.replace('  "', ' "'), f"root  {Path(result['source'])}")
    if "identity" not in dimensions:
        section(f"desc  {len(str(result['description']))} chars")
    section(
        f"main  {result['primary_workflow'] or 'none'}",
        "count "
        + ", ".join(
            f"{counts.get(key, 0)} {key}" for key in CONTENT_KEYS if counts.get(key)
        )
        or "count none",
    )

    if "identity" in dimensions:
        digest = result["source_fingerprint"]
        section(
            "",
            f"desc  {result['description']}",
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

    if "workflows" in dimensions:
        section("", f"workflows {len(result['workflows'])}")
        for row in result["workflows"]:
            reach = row["status"]
            if row["from"]:
                reach += f" from {row['from']}"
            section(
                f"{row['id']} {reach} {row['steps']} steps {row['nodes']} nodes "
                f"{row['path']} {row['bytes']}B"
            )
            if row["entry"]:
                section(f"  entry {row['entry']} - {row['entry_command']}")
            section(
                f"  outcomes {', '.join(row['outcomes']) or 'none'}"
                f" | inputs {', '.join(row['inputs']) or 'none'}"
            )

    if "execution" in dimensions:
        section("", f"execution {len(result['execution'])} nodes")
        for row in result["execution"]:
            targets = ", ".join(
                f"{item['label']}->{item['target']}" for item in row["transitions"]
            )
            section(f"{row['label']} {row['kind']} [{targets or 'end'}]")
            section(f"  {row['command']}")

    if "lowering" in dimensions:
        section("", f"lowering {len(result['lowering'])}")
        table(
            [
                (
                    row["kind"],
                    row["id"],
                    "lowered" if row["lowered"] else "not-lowered",
                    _nodes(row["nodes"]),
                )
                for row in result["lowering"]
            ]
        )

    if "policies" in dimensions:
        section("", f"policies {len(result['policies'])}")
        for row in result["policies"]:
            section(f"{row['id']} \"{row['summary']}\"")
            for provision in row["provisions"]:
                section(
                    f"  {provision['id']} {provision['phase']} "
                    f"{provision['obligation']} match={provision['match']} "
                    f"-> {_nodes(provision['nodes'])}"
                )

    if "rules" in dimensions:
        section("", f"rules {len(result['rules'])}")
        table(
            [
                (
                    row["id"],
                    row["phase"],
                    row["obligation"],
                    f"match={row['match']}",
                    f"-> {_nodes(row['nodes'])}",
                )
                for row in result["rules"]
            ]
        )

    if "protocols" in dimensions:
        section("", f"protocols {len(result['protocols'])}")
        for row in result["protocols"]:
            section(
                f"{row['id']} states={', '.join(row['states'])} "
                f"initial={row['initial']} accepting={', '.join(row['accepting'])}"
            )
            for frame in row["frames"]:
                section(f"  frame {frame}")
            for hook in row["hooks"]:
                section(
                    f"  hook {hook['id']} {hook['phase']} "
                    f"from={', '.join(hook['from'])} to={hook['to'] or '-'} "
                    f"-> {_nodes(hook['nodes'])}"
                )

    if "patterns" in dimensions:
        section("", f"patterns {len(result['patterns'])}")
        for row in result["patterns"]:
            section(f"{row['id']} procedure={', '.join(row['procedure'])}")
            for application in row["applications"]:
                section(
                    f"  apply {application['at']} -> {_nodes(application['nodes'])}"
                )

    if "heuristics" in dimensions:
        section("", f"heuristics {len(result['heuristics'])}")
        table(
            [
                (
                    row["id"],
                    "advisory",
                    f"advice={', '.join(row['advice'])}",
                    _nodes(row["placements"]),
                )
                for row in result["heuristics"]
            ]
        )

    if "guidance" in dimensions:
        section("", f"guidance {len(result['guidance'])}")
        table(
            [
                (
                    row["id"],
                    "non-binding",
                    f"page={row['page'] or 'none'}",
                    _nodes(row["placements"]),
                )
                for row in result["guidance"]
            ]
        )

    if "profiles" in dimensions:
        section("", f"profiles {len(result['profiles'])}")
        for row in result["profiles"]:
            section(f"{row['id']} \"{row['title']}\"")
            section(
                f"  description={row['description'] or 'none'} | "
                f"points={row['points']} | guides={row['guides']}"
            )

    if "attention" in dimensions:
        attention = result["attention"]
        section(
            "",
            f"root  SKILL.md {attention['root_bytes']}B "
            f"{attention['root_lines']}L {attention['root_words']}w",
            f"exec  {attention['execution_bytes']}B in {attention['execution_modules']} modules "
            f"(max {attention['largest_execution_module_bytes']}B)",
            f"path  worst {attention['execution_path_bytes']}B "
            f"| loads {attention['execution_path_loads']}",
            f"refs  supplementary {attention['reference_bytes']}B",
            f"links execution {attention['execution_links']}"
            f" | supplementary {len(attention['optional_links'])}",
        )
        for link in attention["optional_links"]:
            section(f"  link {link['target']} at {link['node']}")

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


def _write_inspect_body(stream: TextIO, results: list[dict[str, Any]]) -> None:
    """Dump each skill's generated SKILL.md text, named and divided by skill."""
    for result in results:
        print(file=stream)
        name = result.get("name", "unknown")
        skill_text = result.get("skill_text")
        if skill_text is None:
            print(f"=== {name} unavailable", file=stream)
            continue
        print(f"=== {name}", file=stream)
        for line in str(skill_text).splitlines():
            print(f"  {line}", file=stream)
