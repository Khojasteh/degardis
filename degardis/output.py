from __future__ import annotations

from pathlib import Path
from textwrap import TextWrapper
from typing import Any, TextIO

from .explain import CheckExplanation
from .model import Diagnostic, Profile, Skill
from .resolver import collect_skills


REPORT_WIDTH = 100
FIELD_WIDTH = 11


def _write_field(
    stream: TextIO,
    label: str,
    value: str,
    width: int = FIELD_WIDTH,
) -> None:
    prefix = f"  {label:<{width}} "
    wrapper = TextWrapper(
        width=REPORT_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines = wrapper.wrap(value.strip()) or [prefix.rstrip()]
    print("\n".join(lines), file=stream)


def _write_messages(stream: TextIO, prefix: str, messages: list[str]) -> None:
    wrapper = TextWrapper(
        width=REPORT_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )
    for message in messages:
        print("\n".join(wrapper.wrap(message)), file=stream)


def _counted(count: int, noun: str) -> str:
    """Render a summary count so a single item does not read as a plural."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _markdown_summary(metrics: dict) -> str:
    return (
        f"{metrics.get('bytes', 0)} bytes, {metrics.get('lines', 0)} lines; "
        f"body {metrics.get('body_bytes', 0)} bytes, "
        f"{metrics.get('body_lines', 0)} lines, "
        f"{metrics.get('body_words', 0)} words"
    )


def write_skill_list(
    stream: TextIO,
    skills: list[tuple[Skill, list[Profile]]],
) -> None:
    print(f"Skills ({len(skills)})", file=stream)
    for skill, profiles in skills:
        print(file=stream)
        print(f"{skill.title} ({skill.name})  v{skill.version}", file=stream)
        bundle = collect_skills([skill.root], profiles=None)[0]
        has_scripts = bool(bundle.contents[0].scripts)
        _write_field(stream, "Description", skill.description or "Not specified")
        _write_field(
            stream,
            "Profiles",
            ", ".join(profile.name for profile in profiles) or "None",
        )
        _write_field(
            stream,
            "Scripts",
            "Yes" if has_scripts else "No",
        )
        _write_field(stream, "License", skill.license or "Not specified")
        _write_field(stream, "Copyright", skill.copyright or "Not specified")
        _write_field(stream, "Source", str(skill.root.resolve()))


def _reported(result: dict, severity: str) -> list[str]:
    """One skill's findings of one severity, each naming the check that found it.

    The check code is what `degardis explain` takes, so a reader can ask why a
    finding matters without leaving the report. Results that carry only messages,
    as an embedded caller's can, are reported as they arrive.
    """
    records = [
        record
        for record in result.get("diagnostics", [])
        if isinstance(record, Diagnostic) and record.severity == severity
    ]
    if records:
        return [
            f"{record.message} ({record.code})" if record.code else record.message
            for record in records
        ]
    key = "errors" if severity == "error" else "warnings"
    return [str(value) for value in result.get(key, [])]


def write_validation_report(
    stream: TextIO,
    results: list[dict],
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
                prefix = f"       {index}. "
                wrapper = TextWrapper(
                    width=REPORT_WIDTH,
                    initial_indent=prefix,
                    subsequent_indent=" " * len(prefix),
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                print("\n".join(wrapper.wrap(error)), file=stream)
        for warning in warnings:
            warning_count += 1
            prefix = "       Warning: "
            wrapper = TextWrapper(
                width=REPORT_WIDTH,
                initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
                break_long_words=False,
                break_on_hyphens=False,
            )
            print("\n".join(wrapper.wrap(warning)), file=stream)
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
            "A pass means these sources are well-formed, not that the skill "
            "guides an agent well.",
            file=stream,
        )


def write_check_explanations(
    stream: TextIO,
    entries: list[tuple[str, CheckExplanation]],
) -> None:
    """Explain each check code, with its examples left exactly as written.

    Trigger and impact are prose and wrap like every other report field. The
    examples are YAML, where indentation is meaning, so they are indented as a
    block and never rewrapped. A blank line separates one code from the next, so
    an agent asking about several codes at once can split them on the code lines.
    """
    for index, (code, explanation) in enumerate(entries):
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


def _columns(rows: list[tuple[str, ...]]) -> list[str]:
    """Align listing columns, leaving the last one ragged so nothing is padded."""
    if not rows:
        return []
    widths = [
        max(len(row[index]) for row in rows) for index in range(len(rows[0]) - 1)
    ]
    lines = []
    for row in rows:
        cells = [value.ljust(widths[index]) for index, value in enumerate(row[:-1])]
        lines.append("  " + " ".join([*cells, row[-1]]).rstrip())
    return lines


def _budget_sizes(result: dict[str, Any]) -> tuple[int, ...]:
    """The budget numbers of one measurement, in the order body and refs print them."""
    markdown = result.get("skill_markdown", {})
    weight = result.get("reference_bytes", {})
    return (
        markdown.get("bytes", 0),
        markdown.get("lines", 0),
        markdown.get("body_bytes", 0),
        markdown.get("body_lines", 0),
        markdown.get("body_words", 0),
        weight.get("entries", 0),
        weight.get("workflows", 0),
        weight.get("profiles", 0),
    )


def _budget_line(label: str, sizes: tuple[int, ...], signed: bool = False) -> str:
    """Lay the budget numbers out in the field order the `body` and `refs` lines use.

    A delta always carries its sign, including on zero, so an unchanged size reads
    as a measured comparison rather than as a size that happens to be small.
    """
    show = (lambda size: f"{size:+d}") if signed else str
    return (
        f"{label} SKILL.md {show(sizes[0])}B {show(sizes[1])}L"
        f" | text {show(sizes[2])}B {show(sizes[3])}L {show(sizes[4])}w"
        f" | entries {show(sizes[5])}B | workflows {show(sizes[6])}B"
        f" | profiles {show(sizes[7])}B"
    )


def _write_agent_baseline(
    stream: TextIO,
    baseline: dict[str, Any],
    sizes: tuple[int, ...],
) -> None:
    """Report the revision's own sizes and, where both were measured, the change."""
    ref = str(baseline.get("ref", ""))
    if baseline.get("state") != "measured":
        print(f"base  {ref} {baseline.get('state', 'unmeasured')}", file=stream)
        return
    was = _budget_sizes(baseline)
    print(_budget_line(f"base  {ref}", was), file=stream)
    print(
        _budget_line(
            "delta",
            tuple(now - before for now, before in zip(sizes, was)),
            signed=True,
        ),
        file=stream,
    )


def _write_agent_skill(
    stream: TextIO,
    result: dict[str, Any],
    dimensions: tuple[str, ...],
    baseline: dict[str, Any] | None = None,
) -> None:
    name = str(result.get("name", "unknown"))
    root = result.get("source")
    root_path = root if isinstance(root, Path) else Path(str(root))
    counts = result.get("counts", {})
    entries = result.get("entries", [])
    workflows = result.get("workflows", [])
    profiles = result.get("profiles", [])
    selected = list(result.get("selected_profiles", []))

    def section(*lines: str) -> None:
        for line in lines:
            print(line, file=stream)

    version = str(result.get("version", ""))
    title = str(result.get("title", name))
    heading = f"skill {name} {version} \"{title}\"".replace('  "', ' "')
    if result.get("title_derived"):
        heading += " (derived title)"
    section(heading, f"root  {root_path}", f"ids   {name}.*")
    if "identity" not in dimensions:
        section(f"desc  {len(str(result.get('description', '')))} chars")
    primary = str(result.get("primary_workflow", ""))
    prefix = f"{name}."
    section(
        f"main  {primary[len(prefix):] if primary.startswith(prefix) else primary or 'none'}",
        "count "
        + ", ".join(
            f"{counts.get(label, 0)} {label}"
            for label in ("entries", "workflows", "profiles", "scripts", "assets")
        ),
    )

    if "identity" in dimensions:
        section("", f"desc  {result.get('description', '')}")
        section(f"lic   {result.get('license') or 'none'}")
        section(f"copy  {result.get('copyright') or 'none'}")

    if "budget" in dimensions:
        markdown = result.get("skill_markdown", {})
        weight = result.get("reference_bytes", {})
        included = (
            ", ".join(selected)
            if 0 < len(selected) <= 4
            else f"{len(selected)} selected"
            if selected
            else "none"
        )
        section(
            "",
            f"body  SKILL.md {markdown.get('bytes', 0)}B {markdown.get('lines', 0)}L"
            f" | text {markdown.get('body_bytes', 0)}B"
            f" {markdown.get('body_lines', 0)}L {markdown.get('body_words', 0)}w"
            f" | profiles {included}",
            f"refs  entries {weight.get('entries', 0)}B"
            f" | workflows {weight.get('workflows', 0)}B"
            f" | profiles {weight.get('profiles', 0)}B",
        )
        if baseline:
            _write_agent_baseline(stream, baseline, _budget_sizes(result))

    if "workflows" in dimensions:
        section("", f"workflows {len(workflows)}")
        section(
            *_columns(
                [
                    (
                        str(item["id"]),
                        item["reached_by"] or "unreached",
                        f"{item['steps']} steps",
                        item["path"],
                        f"{item['bytes']}B",
                    )
                    for item in workflows
                ]
            )
        )

    if "entries" in dimensions:
        kinds = result.get("entry_kind_counts", {})
        spread = ", ".join(f"{kind} {count}" for kind, count in kinds.items())
        section("", f"entries {len(entries)}" + (f"  {spread}" if spread else ""))
        section(
            *_columns(
                [
                    (
                        str(item["id"]),
                        f"{item['kind']}/{item['priority']}",
                        item["path"],
                        f"{item['bytes']}B",
                    )
                    for item in entries
                ]
            )
        )

    if "profiles" in dimensions:
        section("", f"profiles {len(profiles)}  {len(selected)} selected")
        section(
            *_columns(
                [
                    (
                        item["name"],
                        "*" if item["selected"] else "-",
                        item["path"],
                        f"{item['bytes']}B",
                    )
                    for item in profiles
                ]
            )
        )

    for label in ("scripts", "assets"):
        if label not in dimensions:
            continue
        items = result.get(label, [])
        section("", f"{label} {len(items)}")
        section(
            *_columns([(item["path"], f"{item['bytes']}B") for item in items])
        )

    if "outputs" in dimensions:
        outputs = result.get("outputs", [])
        total = sum(item["bytes"] for item in outputs)
        section("", f"outputs {len(outputs)}  {total}B")
        section(
            *_columns(
                [
                    (item["path"], f"{item['bytes']}B", item["mode"])
                    for item in outputs
                ]
            )
        )

    if "diagnostics" in dimensions:
        records: list[Diagnostic] = list(result.get("diagnostics", []))
        if records:
            print(file=stream)
        for record in records:
            label = "error" if record.severity == "error" else "warn "
            location = record.location(root_path)
            print(
                f"{label} {location} {record.code} {record.summary(name)}".rstrip(),
                file=stream,
            )


def write_agent_report(
    stream: TextIO,
    results: list[dict],
    dimensions: tuple[str, ...],
    baselines: list[dict] | None = None,
) -> None:
    """Report source intelligence for an AI agent, in as few tokens as it takes."""
    measured = baselines or [None] * len(results)
    for index, result in enumerate(results):
        if index:
            print(file=stream)
        _write_agent_skill(stream, result, dimensions, measured[index])
    errors = sum(len(result.get("errors", [])) for result in results)
    warnings = sum(len(result.get("warnings", [])) for result in results)
    print(file=stream)
    print(
        f"{_counted(len(results), 'skill')}, {_counted(errors, 'error')}, "
        f"{_counted(warnings, 'warning')}",
        file=stream,
    )


def write_profile_matches(
    stream: TextIO,
    matches: dict[str, list[str]],
) -> None:
    visible = [(selector, owners) for selector, owners in matches.items() if owners]
    if not visible:
        return
    print("Profiles", file=stream)
    for selector, owners in visible:
        print(f"  {selector}: {', '.join(owners)}", file=stream)
    print(file=stream)


def write_build_report(
    stream: TextIO,
    skills: list[Skill],
    paths: list[Path],
    *,
    as_zip: bool,
    warnings: list[str] | None = None,
    metrics: dict[str, dict[str, int]] | None = None,
) -> None:
    print("Build", file=stream)
    print(file=stream)
    for skill, path in zip(skills, paths):
        print(f"[BUILT] {skill.title} ({skill.name})", file=stream)
        _write_field(stream, "Artifact", str(path.resolve()))
        measured = (metrics or {}).get(skill.name)
        if measured:
            _write_field(stream, "SKILL.md", _markdown_summary(measured))
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
