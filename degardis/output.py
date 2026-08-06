from __future__ import annotations

from pathlib import Path
from textwrap import TextWrapper
from typing import TextIO

from .model import Diagnostic, Profile, Skill
from .resolver import collect_skills


REPORT_WIDTH = 100
FIELD_WIDTH = 11


def _write_field(
    stream: TextIO,
    label: str,
    value: str,
) -> None:
    prefix = f"  {label:<{FIELD_WIDTH}} "
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
    """One skill's findings of one severity, in the order they were reported.

    Results that carry only messages, as an embedded caller's can, are reported
    as they arrive.
    """
    records = [
        record
        for record in result.get("diagnostics", [])
        if isinstance(record, Diagnostic) and record.severity == severity
    ]
    if records:
        return [record.message for record in records]
    key = "errors" if severity == "error" else "warnings"
    return [str(value) for value in result.get(key, [])]


def write_validation_report(
    stream: TextIO,
    results: list[dict],
) -> None:
    print("Validation", file=stream)
    print(file=stream)
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
