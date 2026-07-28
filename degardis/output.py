from __future__ import annotations

from pathlib import Path
from textwrap import TextWrapper
from typing import TextIO

from .model import Profile, Skill
from .resolver import collect_skills


REPORT_WIDTH = 100
FIELD_WIDTH = 11


def _write_field(stream: TextIO, label: str, value: str) -> None:
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


def write_validation_report(
    stream: TextIO,
    results: list[tuple[Skill, list[str], list[str]]],
) -> None:
    print("Validation", file=stream)
    print(file=stream)
    failed = 0
    warning_count = 0
    for skill, errors, warnings in results:
        if not errors:
            print(f"[PASS] {skill.title} ({skill.name})", file=stream)
        else:
            failed += 1
            print(f"[FAIL] {skill.title} ({skill.name})", file=stream)
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
        f"Summary: {passed} passed, {failed} failed, {len(results)} total.",
        file=stream,
    )
    if warning_count:
        print(f"Warnings: {warning_count}.", file=stream)


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
) -> None:
    print("Build", file=stream)
    print(file=stream)
    for skill, path in zip(skills, paths):
        print(f"[BUILT] {skill.title} ({skill.name})", file=stream)
        _write_field(stream, "Artifact", str(path.resolve()))
    kind = "archive" if as_zip else "folder"
    if len(paths) != 1:
        kind += "s"
    subject = "skill" if len(paths) == 1 else "skills"
    print(file=stream)
    print(f"Summary: {len(paths)} {subject} built as {kind}.", file=stream)
