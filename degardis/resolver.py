from __future__ import annotations

import fnmatch
import stat
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator

from .markdown import entry_filename, workflow_filename
from .icons import (
    ICON_OUTPUTS,
    IconError,
    resolve_icon_sources,
    validate_icon_sources,
)
from .model import (
    DegardisError,
    Diagnostics,
    Entry,
    Profile,
    Skill,
    SkillBundle,
    SkillContent,
    ensure_within,
)
from .registry import discover_skill_paths, load_profile, load_skill_path
from .yamlsource import load_yaml, yaml_scalar_warnings


# The content keys a manifest may set. None of them has a default: a key the
# manifest leaves out says the skill ships none of that content, so the compiler
# never assumes files the author did not ask for. Profiles are found the same way
# as everything else a bundle carries; which of them a build selects is a
# separate question, and only --profile answers it.
CONTENT_KEYS: tuple[str, ...] = (
    "entries",
    "workflows",
    "profiles",
    "scripts",
    "assets",
)
ALLOWED_CONTENT_KEYS = frozenset(CONTENT_KEYS)

# The marker that turns a content pattern into an exclusion, as in .gitignore.
CONTENT_EXCLUDE_PREFIX = "!"

# What the host itself writes beside authored files, matched by name so a tree
# carried from one machine to another still builds the same bundle. Names are
# compared casefolded. AppleDouble sidecars are a prefix rather than a name,
# because the rest of each one is the name of the file it shadows.
PLATFORM_METADATA_NAMES = frozenset(
    {
        ".ds_store",
        ".spotlight-v100",
        ".trashes",
        ".fseventsd",
        ".localized",
        "__macosx",
        "thumbs.db",
        "ehthumbs.db",
        "desktop.ini",
        "icon\r",
    }
)
APPLEDOUBLE_PREFIX = "._"
ALLOWED_ENTRY_KINDS = {
    "principle",
    "policy",
    "heuristic",
    "pattern",
    "constraint",
    "rule",
}
ENTRY_TEXT_FIELDS = {
    "id",
    "title",
    "kind",
    "rule",
    "rationale",
    "scope",
    "constraint",
}
ENTRY_LIST_FIELDS = {
    "require",
    "allow",
    "reject",
    "conditions",
    "exceptions",
    "examples",
}
ALLOWED_ENTRY_FIELDS = ENTRY_TEXT_FIELDS | ENTRY_LIST_FIELDS | {"priority"}
ALLOWED_WORKFLOW_FIELDS = {"id", "title", "description", "steps"}
ALLOWED_WORKFLOW_STEP_FIELDS = {
    "id",
    "action",
    "instruction",
    "when",
    "use",
}


def _is_bytecode(relative: Path) -> bool:
    """Whether a path is Python bytecode rather than authored content.

    Python writes bytecode beside the scripts a skill ships, so a pattern such
    as `scripts/**/*` matches it once those scripts have run. It is
    generated output of the author's own source and must never reach a bundle,
    where it would be stale on the first edit and wrong on another Python.
    """
    return "__pycache__" in relative.parts or relative.suffix in (".pyc", ".pyo")


def _is_platform_metadata(relative: Path) -> bool:
    """Whether a path is bookkeeping the host wrote, rather than authored content.

    Every desktop platform drops its own files beside real ones: Finder writes
    .DS_Store and ._ sidecars, Explorer writes Thumbs.db and desktop.ini. None of
    it is content, none of it is usually visible to the author who would have to
    exclude it, and a bundle carrying it is a bundle carrying one host's habits.
    The test is by name and not by any host flag, so the same source tree yields
    the same bundle wherever it is built.
    """
    if relative.name.startswith(APPLEDOUBLE_PREFIX):
        return True
    return any(part.casefold() in PLATFORM_METADATA_NAMES for part in relative.parts)


def _has_hidden_attribute(path: Path) -> bool:
    """Whether the filesystem itself marks a path hidden or system.

    Windows keeps this in file attributes and macOS in BSD flags, and each field
    is absent from the other platform's stat result, so both are read defensively.
    Reading host state is the point rather than a compromise: a file its author
    cannot see is a file they cannot write an exclusion for.
    """
    try:
        status = path.stat()
    except OSError:
        return False
    attributes = getattr(status, "st_file_attributes", 0)
    if attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM):
        return True
    return bool(getattr(status, "st_flags", 0) & stat.UF_HIDDEN)


def _is_hidden(root: Path, relative: Path, checked: dict[Path, bool]) -> bool:
    """Whether a path is one its author cannot see, so cannot exclude by name.

    A dot-prefixed directory is where tooling keeps state of its own: .git,
    .venv, .vscode. A dot-prefixed *file* is not hidden by that convention alone,
    since .gitignore and .editorconfig are ordinary files a skill may well ship,
    so only the directories a path passes through are read that way. Directory
    answers are remembered because one pattern usually matches many files under
    the same parent.
    """
    for depth, part in enumerate(relative.parts[:-1], start=1):
        directory = root.joinpath(*relative.parts[:depth])
        hidden = checked.get(directory)
        if hidden is None:
            hidden = part.startswith(".") or _has_hidden_attribute(directory)
            checked[directory] = hidden
        if hidden:
            return True
    return _has_hidden_attribute(root / relative)


def _admits_hidden(pattern: str) -> bool:
    """Whether a pattern asks for hidden paths rather than sweeping them in.

    A wildcard is written without knowing what it will match, so it must not
    reach a file the author never sees. A pattern that spells out a dot-prefixed
    directory, or that names a path without any wildcard, was written about that
    exact path, so it selects what it names.
    """
    if not any(character in pattern for character in "*?["):
        return True
    return any(part.startswith(".") for part in PurePosixPath(pattern).parts)


def _excluded_by(matches: set[Path], path: Path) -> bool:
    """Whether an exclusion's matches cover a path, as the path or as a parent."""
    return path in matches or any(parent in matches for parent in path.parents)


def _children(directory: Path) -> list[Path]:
    """What one directory holds, or nothing where it cannot be listed."""
    try:
        return sorted(directory.iterdir())
    except OSError:
        return []


def _descend(directory: Path, segments: tuple[str, ...]) -> Iterator[Path]:
    """Walk one pattern's segments down from a directory, yielding what matches.

    `**` stands for any number of directories, including none, so it is tried
    first against the rest of the pattern and then against each subdirectory. A
    symlinked directory is never descended into, so a link that points at one of
    its own ancestors cannot make the walk run forever.
    """
    if not segments:
        yield directory
        return
    head, rest = segments[0], segments[1:]
    if head == "**":
        yield from _descend(directory, rest)
        for child in _children(directory):
            if child.is_dir() and not child.is_symlink():
                yield from _descend(child, segments)
        return
    for child in _children(directory):
        if fnmatch.fnmatchcase(child.name, head):
            yield from _descend(child, rest)


def _matching_paths(root: Path, pattern: str) -> list[Path]:
    """Every path under root one pattern names, matched the same way anywhere.

    Path.glob defers each comparison to the host filesystem, which matches names
    without regard to case on Windows and macOS and with regard to it elsewhere.
    That makes which files a skill ships a property of the machine building it:
    `!ENTRIES/one.yaml` drops `entries/one.yaml` on one host and nothing on the
    next. Comparing each segment against the names a directory actually holds,
    case included, keeps the selection a property of the source alone. `/` is
    the only separator a pattern has, for the same reason.
    """
    segments = tuple(
        part for part in PurePosixPath(pattern).parts if part not in (".", "/")
    )
    found: dict[Path, None] = {}
    for path in _descend(root, segments):
        found.setdefault(path, None)
    return sorted(found)


def _glob(
    skill: Skill,
    key: str,
    patterns: Iterable[str],
    diagnostics: Diagnostics,
) -> tuple[list[Path], bool]:
    """The files a pattern list selects, and whether every pattern found one.

    Patterns apply in sequence, as in .gitignore: one prefixed with `!` removes
    what the patterns before it selected, and a pattern after that can put a file
    back. An exclusion that matches a directory removes everything selected
    beneath it, since naming the directory is the shorter way to say the same
    thing. What no pattern can select is a file the author cannot see, or one the
    host wrote for itself.

    A pattern that names nothing present is reported rather than passed over. It
    is the only evidence of a misspelled path, a wrongly cased one, or a `!` that
    now removes nothing, none of which the resulting bundle can show.
    """
    selected: dict[Path, None] = {}
    hidden_directories: dict[Path, bool] = {}
    complete = True
    for pattern in patterns:
        excluding = pattern.startswith(CONTENT_EXCLUDE_PREFIX)
        body = pattern.removeprefix(CONTENT_EXCLUDE_PREFIX)
        try:
            ensure_within(
                skill.root / body,
                skill.root,
                f"{skill.name}: content patterns",
            )
        except DegardisError as exc:
            diagnostics.error(exc, "content.outside-skill")
            complete = False
            continue
        matches = _matching_paths(skill.root, body)
        if not matches:
            diagnostics.error(
                f"{skill.name}: content.{key} pattern {pattern} matches nothing "
                "in the skill directory",
                "content.unmatched-pattern",
                skill.root / "skill.yaml",
            )
            complete = False
            continue
        if excluding:
            covered = set(matches)
            for path in [p for p in selected if _excluded_by(covered, p)]:
                del selected[path]
            continue
        admits_hidden = _admits_hidden(body)
        for path in matches:
            relative = path.relative_to(skill.root)
            if not path.is_file() or _is_bytecode(relative):
                continue
            if _is_platform_metadata(relative):
                continue
            if not admits_hidden and _is_hidden(
                skill.root, relative, hidden_directories
            ):
                continue
            try:
                ensure_within(
                    path,
                    skill.root,
                    f"{skill.name}: content files",
                )
            except DegardisError as exc:
                diagnostics.error(exc, "content.outside-skill", path)
                continue
            selected.setdefault(path, None)
    return list(selected), complete


def _is_usable_pattern(item: object) -> bool:
    """Whether one content pattern can select or exclude anything at all.

    The exclusion marker says what to do with a pattern, so a pattern that is
    only the marker says nothing, and the matcher has no empty pattern to give it.
    """
    if not isinstance(item, str):
        return False
    return bool(item.strip().removeprefix(CONTENT_EXCLUDE_PREFIX).strip())


def _content_patterns(
    skill: Skill,
    config: dict,
    key: str,
    diagnostics: Diagnostics,
) -> list[str] | None:
    """One content key's patterns, or None where there are none to match with."""
    value = config[key]
    if not isinstance(value, list) or any(
        not _is_usable_pattern(item) for item in value
    ):
        diagnostics.error(
            f"{skill.name}: content.{key} must be a list of non-empty glob strings, "
            f"each optionally prefixed with {CONTENT_EXCLUDE_PREFIX} to exclude",
            "content.invalid-type",
            skill.root / "skill.yaml",
        )
        return None
    return value


def _content_files(
    skill: Skill,
    config: dict,
    key: str,
    diagnostics: Diagnostics,
) -> list[Path]:
    """The files one content key selects, reporting a key that ships nothing.

    A key the manifest leaves out asks for no content of that kind, so nothing is
    resolved for it and nothing is reported. A key the manifest does declare is a
    statement that the skill ships those files, and the bundle is the one place
    that statement coming out empty never shows: no other check reads an entry, a
    script, or an asset, so a group that resolves to nothing simply disappears.
    """
    if key not in config:
        return []
    patterns = _content_patterns(skill, config, key, diagnostics)
    if patterns is None:
        return []
    files, complete = _glob(skill, key, patterns, diagnostics)
    if not files and complete:
        diagnostics.error(
            f"{skill.name}: content.{key} selects no file, so the bundle would "
            f"ship none; remove the key if the skill has no {key}",
            "content.empty-selection",
            skill.root / "skill.yaml",
        )
    return files


def _load_entry(
    path: Path,
    skill: Skill,
    diagnostics: Diagnostics | None = None,
) -> Entry | None:
    collector = diagnostics if diagnostics is not None else Diagnostics()
    try:
        data = load_yaml(path)
    except DegardisError as exc:
        collector.source_failure(exc, path, "source.invalid-yaml")
        if diagnostics is None:
            collector.raise_if_errors()
        return None

    unknown = sorted(set(data) - ALLOWED_ENTRY_FIELDS)
    if unknown:
        collector.warning(
            f"{path}: unrecognized entry fields ignored: {', '.join(unknown)}",
            "entry.unknown-field",
            path,
        )
    usable = True
    for key, code in (("id", "entry.missing-id"), ("rule", "entry.missing-rule")):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            collector.error(
                f"{path}: {key} must be a non-empty string",
                code,
                path,
            )
            usable = False
    for key in sorted(ENTRY_TEXT_FIELDS - {"id", "rule"}):
        if key in data and not isinstance(data[key], str):
            collector.error(
                f"{path}: {key} must be a string", "entry.invalid-type", path
            )
    if "title" not in data:
        collector.warning(
            f"{path}: title is missing; the reference index shows the entry id",
            "entry.missing-title",
            path,
        )
    if "kind" not in data:
        collector.warning(
            f"{path}: kind is missing; the entry is compiled as rule",
            "entry.missing-kind",
            path,
        )
    elif isinstance(data["kind"], str):
        kind = data["kind"]
        if not kind.strip():
            collector.error(
                f"{path}: kind must be a non-empty string",
                "entry.invalid-type",
                path,
            )
            usable = False
        elif kind not in ALLOWED_ENTRY_KINDS:
            known = ", ".join(sorted(ALLOWED_ENTRY_KINDS))
            collector.warning(
                f"{path}: unrecognized kind {kind} compiled as declared; "
                f"kinds known to this compiler: {known}",
                "entry.unknown-kind",
                path,
            )
    priority = data.get("priority", 100)
    if not isinstance(priority, int) or isinstance(priority, bool):
        collector.error(
            f"{path}: priority must be an integer", "entry.invalid-type", path
        )
        usable = False
    for key in sorted(ENTRY_LIST_FIELDS):
        if key not in data:
            continue
        value = data[key]
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            collector.error(
                f"{path}: {key} must be a list of strings",
                "entry.invalid-type",
                path,
            )
    if diagnostics is None:
        collector.raise_if_errors()
    if not usable:
        return None
    return Entry(path=path, data=data, skill=skill.name)


def _load_workflow(
    path: Path,
    skill: Skill,
    diagnostics: Diagnostics | None = None,
) -> dict | None:
    collector = diagnostics if diagnostics is not None else Diagnostics()
    try:
        data = load_yaml(path)
    except DegardisError as exc:
        collector.source_failure(exc, path, "source.invalid-yaml")
        if diagnostics is None:
            collector.raise_if_errors()
        return None

    unknown = sorted(set(data) - ALLOWED_WORKFLOW_FIELDS)
    if unknown:
        collector.warning(
            f"{path}: unrecognized workflow fields ignored: {', '.join(unknown)}",
            "workflow.unknown-field",
            path,
        )
    usable = True
    workflow_id = data.get("id")
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        collector.error(
            f"{path}: id must be a non-empty string", "workflow.missing-id", path
        )
        usable = False
    for key in ("title", "description"):
        if key in data and not isinstance(data[key], str):
            collector.error(
                f"{path}: {key} must be a string", "workflow.invalid-type", path
            )
    if "title" not in data:
        collector.warning(
            f"{path}: title is missing; generated links show the workflow id",
            "workflow.missing-title",
            path,
        )
    steps = data.get("steps")
    if not isinstance(steps, list):
        collector.error(f"{path}: steps must be a list", "workflow.missing-steps", path)
        usable = False
        steps = []
    for index, step in enumerate(steps, start=1):
        label = f"{path}: step {index}"
        if isinstance(step, str):
            if not step.strip():
                collector.error(
                    f"{label} must be a non-empty string", "workflow.invalid-step", path
                )
                usable = False
            continue
        if not isinstance(step, dict):
            collector.error(
                f"{label} must be a string or mapping", "workflow.invalid-step", path
            )
            usable = False
            continue
        unknown_step_fields = sorted(set(step) - ALLOWED_WORKFLOW_STEP_FIELDS)
        if unknown_step_fields:
            collector.warning(
                f"{label} has unrecognized fields ignored: "
                f"{', '.join(unknown_step_fields)}",
                "workflow.unknown-step-field",
                path,
            )
        for key in sorted(set(step) & ALLOWED_WORKFLOW_STEP_FIELDS):
            value = step[key]
            if not isinstance(value, str) or not value.strip():
                collector.error(
                    f"{label} {key} must be a non-empty string",
                    "workflow.invalid-step",
                    path,
                )
                usable = False
        if "use" in step and ({"action", "instruction"} & set(step)):
            collector.error(
                f"{label} use cannot be combined with action or instruction",
                "workflow.invalid-step",
                path,
            )
        if not ({"use", "action", "id", "instruction"} & set(step)):
            collector.error(
                f"{label} must define use, action, id, or instruction",
                "workflow.invalid-step",
                path,
            )
        elif not step.get("use") and not step.get("instruction"):
            collector.warning(
                f"{label} has no instruction; it renders as a heading alone",
                "workflow.step-missing-instruction",
                path,
            )
    if diagnostics is None:
        collector.raise_if_errors()
    if not usable:
        return None
    return data


def _validate_output_paths(
    content: SkillContent,
    diagnostics: Diagnostics | None = None,
) -> None:
    collector = diagnostics if diagnostics is not None else Diagnostics()
    claimed: dict[str, Path] = {}

    def claim(relative: str, source: Path) -> None:
        key = relative.casefold()
        previous = claimed.get(key)
        if previous is not None and previous != source:
            collector.error(
                f"{content.skill.name}: output path collision at {relative}: "
                f"{previous} and {source}",
                "output.path-collision",
                source,
            )
            return
        claimed[key] = source

    claim("SKILL.md", content.skill.root / "skill.yaml")
    claim("agents/openai.yaml", content.skill.root / "skill.yaml")
    for entry in content.entries:
        filename = entry_filename(entry)
        if filename == ".md":
            collector.error(
                f"{entry.path}: entry id does not produce a valid filename",
                "output.invalid-filename",
                entry.path,
            )
            continue
        claim(f"references/entries/{filename}", entry.path)
    for workflow in content.workflows:
        if workflow.get("id") == content.skill.primary_workflow:
            continue
        filename = workflow_filename(workflow, content.skill.name)
        if filename == ".md":
            collector.error(
                f"{workflow.get('_path')}: workflow id does not produce "
                "a valid filename",
                "output.invalid-filename",
                workflow.get("_path"),
            )
            continue
        claim(f"references/workflows/{filename}", workflow["_path"])
    for profile in content.profiles:
        claim(f"references/profiles/{profile.filename}", profile.path)
    for source in [*content.scripts, *content.assets]:
        claim(source.relative_to(content.skill.root).as_posix(), source)
    for role, source in content.icon_sources.items():
        claim(ICON_OUTPUTS[role], source)
    if diagnostics is None:
        collector.raise_if_errors()


def _check_entry_ordering(
    skill: Skill,
    entries: list[Entry],
    collector: Diagnostics,
) -> None:
    """Warn where the reference index order is the compiler's, not the author's.

    An omitted priority defaults to 100, which sinks the entry below every
    authored one, and equal priorities fall back to a kind-then-id sort. Both
    decide what the always-loaded index shows first, so neither should be silent.
    """
    declared = [entry for entry in entries if "priority" in entry.data]
    if entries and not declared:
        collector.warning(
            f"{skill.name}: no entry declares a priority; the reference index "
            "is ordered by kind then id",
            "entry.no-priorities",
            skill.root / "skill.yaml",
        )
    else:
        for entry in entries:
            if "priority" not in entry.data:
                collector.warning(
                    f"{entry.path}: priority is missing; the entry sorts last "
                    "at the default 100",
                    "entry.missing-priority",
                    entry.path,
                )
    grouped: dict[int, list[Entry]] = {}
    for entry in declared:
        grouped.setdefault(entry.priority, []).append(entry)
    for priority, shared in sorted(grouped.items()):
        if len(shared) < 2:
            continue
        order = ", ".join(entry.id for entry in shared)
        collector.warning(
            f"{skill.name}: entries share priority {priority} and are ordered "
            f"by kind then id: {order}",
            "entry.duplicate-priority",
            skill.root / "skill.yaml",
        )
    titled: dict[str, list[Entry]] = {}
    for entry in entries:
        titled.setdefault(entry.title, []).append(entry)
    for title, shared in titled.items():
        if len(shared) < 2:
            continue
        collector.warning(
            f"{skill.name}: entries share the title {title!r}, which the "
            f"reference index cannot tell apart: {', '.join(e.id for e in shared)}",
            "entry.duplicate-title",
            skill.root / "skill.yaml",
        )


def _check_workflow_reach(
    skill: Skill,
    workflows: list[dict],
    collector: Diagnostics,
) -> None:
    """Warn about a workflow that ships but no use chain from the primary reaches."""
    known = {str(workflow["id"]): workflow for workflow in workflows}
    if skill.primary_workflow not in known:
        return
    reached: set[str] = set()
    pending = [skill.primary_workflow]
    while pending:
        current = pending.pop()
        if current in reached or current not in known:
            continue
        reached.add(current)
        for step in known[current].get("steps", []):
            if isinstance(step, dict) and step.get("use"):
                pending.append(str(step["use"]))
    for workflow_id in sorted(set(known) - reached):
        collector.warning(
            f"{known[workflow_id]['_path']}: workflow {workflow_id} is never "
            f"reached from {skill.primary_workflow} but still ships",
            "workflow.unreachable",
            known[workflow_id]["_path"],
        )


def _content_config(skill: Skill, diagnostics: Diagnostics) -> dict:
    """The manifest's content section, reporting a shape the loader cannot use."""
    config = skill.manifest.get("content", {})
    if not isinstance(config, dict):
        diagnostics.error(
            f"{skill.name}: content must be a mapping",
            "content.invalid-type",
            skill.root / "skill.yaml",
        )
        config = {}
    unsupported = sorted(set(config) - ALLOWED_CONTENT_KEYS)
    if unsupported:
        diagnostics.warning(
            f"{skill.name}: unrecognized content fields ignored: "
            f"{', '.join(unsupported)}",
            "content.unknown-field",
            skill.root / "skill.yaml",
        )
    return config


def _load_entries(
    skill: Skill,
    config: dict,
    diagnostics: Diagnostics,
) -> list[Entry]:
    """Load every entry file, in the order the generated skill presents them."""
    entries: list[Entry] = []
    for path in _content_files(skill, config, "entries", diagnostics):
        diagnostics.add(yaml_scalar_warnings(path))
        entry = _load_entry(path, skill, diagnostics)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda entry: (entry.priority, entry.kind, entry.id))
    _check_entry_ordering(skill, entries, diagnostics)
    return entries


def _load_workflows(
    skill: Skill,
    config: dict,
    diagnostics: Diagnostics,
) -> list[dict]:
    """Load every workflow file, refusing a second one that claims a used id."""
    workflows: list[dict] = []
    workflow_paths: dict[str, Path] = {}
    for path in _content_files(skill, config, "workflows", diagnostics):
        diagnostics.add(yaml_scalar_warnings(path))
        data = _load_workflow(path, skill, diagnostics)
        if data is None:
            continue
        workflow_id = data["id"]
        previous = workflow_paths.get(workflow_id)
        if previous is not None:
            diagnostics.error(
                f"{path}: duplicate workflow id {workflow_id}: "
                f"{previous} and {path}",
                "workflow.duplicate-id",
                path,
            )
            continue
        workflow_paths[workflow_id] = path
        data["_skill"] = skill.name
        data["_path"] = path
        if workflow_id == skill.primary_workflow and "description" not in data:
            diagnostics.warning(
                f"{path}: the primary workflow has no description; the "
                "generated body opens without stating what the skill does",
                "workflow.missing-description",
                path,
            )
        workflows.append(data)
    _check_workflow_reach(skill, workflows, diagnostics)
    return workflows


def _load_profiles(
    skill: Skill,
    config: dict,
    diagnostics: Diagnostics,
) -> list[Profile]:
    """Load every profile source the content patterns select, ordered by name.

    Name order is the order a reader chooses a profile in, and it holds however
    the patterns were written, so the generated guidance does not depend on which
    pattern happened to match a file first.
    """
    profiles: list[Profile] = []
    for path in _content_files(skill, config, "profiles", diagnostics):
        diagnostics.add(yaml_scalar_warnings(path))
        try:
            profile = load_profile(path, skill.name, skill.root, diagnostics)
        except (OSError, UnicodeError) as exc:
            diagnostics.source_failure(exc, path, "source.unreadable")
            continue
        if profile is not None:
            profiles.append(profile)
    profiles.sort(key=lambda profile: profile.name)
    return profiles


def load_skill_profiles(skill: Skill) -> list[Profile]:
    """Every profile a skill defines, before any selection narrows them down."""
    diagnostics = Diagnostics()
    profiles = _load_profiles(skill, _content_config(skill, diagnostics), diagnostics)
    diagnostics.raise_if_errors()
    return profiles


def _load_icons(skill: Skill, diagnostics: Diagnostics) -> dict[str, Path]:
    """Resolve the interface icon sources, reporting any that cannot be used."""
    try:
        icon_sources = resolve_icon_sources(skill)
        validate_icon_sources(icon_sources)
    except IconError as exc:
        diagnostics.error(exc, exc.code, skill.root / "skill.yaml")
        return {}
    except (DegardisError, OSError, UnicodeError) as exc:
        diagnostics.error(exc, "icon.unreadable", skill.root / "skill.yaml")
        return {}
    return icon_sources


def load_content(
    skill: Skill,
    diagnostics: Diagnostics | None = None,
) -> SkillContent:
    """Resolve every source one skill declares, collecting what each reports.

    Sources load in the order below, which is the order their problems are
    reported in. Without a collector the caller wants a failure raised rather
    than a report, so everything gathered here is raised together at the end.
    """
    collector = diagnostics if diagnostics is not None else Diagnostics()
    collector.add(yaml_scalar_warnings(skill.root / "skill.yaml"))
    config = _content_config(skill, collector)

    entries = _load_entries(skill, config, collector)
    workflows = _load_workflows(skill, config, collector)
    profiles = _load_profiles(skill, config, collector)
    scripts = _content_files(skill, config, "scripts", collector)
    assets = _content_files(skill, config, "assets", collector)
    icon_sources = _load_icons(skill, collector)

    content = SkillContent(
        skill=skill,
        entries=entries,
        workflows=workflows,
        profiles=profiles,
        scripts=scripts,
        assets=assets,
        icon_sources=icon_sources,
    )
    _validate_output_paths(content, collector)
    if diagnostics is None:
        collector.raise_if_errors()
    return content


def select_profiles(
    contents: list[SkillContent], selectors: list[str] | None
) -> dict[str, set[str]]:
    """Which profiles each skill ships, from the selectors the caller gave.

    A profile is optional by definition, so a build that names none includes
    none. The manifest has no say in this: it declares which profiles exist, and
    the command that builds decides which of them this bundle carries.
    """
    selected: dict[str, set[str]] = {content.skill.name: set() for content in contents}
    available = {
        content.skill.name: {profile.name for profile in content.profiles}
        for content in contents
    }
    for selector in selectors or []:
        owner: str | None = None
        name = selector
        if ":" in selector:
            owner, name = selector.split(":", 1)
            if owner not in available:
                raise DegardisError(
                    f"Profile selector references unselected skill: {owner}"
                )
        owners = [owner] if owner else sorted(available)
        matches = 0
        for skill_name in owners:
            assert skill_name is not None
            if name == "all":
                selected[skill_name].update(available[skill_name])
                matches += len(available[skill_name])
            elif name in available[skill_name]:
                selected[skill_name].add(name)
                matches += 1
        if matches == 0 and name != "all":
            raise DegardisError(f"Profile selector matched no selected skill: {selector}")
    return selected


def collect_skills(
    skill_paths: list[Path], profiles: list[str] | None = None
) -> list[SkillBundle]:
    contents = [load_content(load_skill_path(path)) for path in skill_paths]
    selections = select_profiles(contents, profiles)
    bundles: list[SkillBundle] = []
    for content in contents:
        content.profiles = [
            profile
            for profile in content.profiles
            if profile.name in selections[content.skill.name]
        ]
        bundles.append(SkillBundle(primary=content.skill, contents=[content]))
    return bundles


def profile_matches(
    skill_paths: list[Path], selectors: list[str]
) -> dict[str, list[str]]:
    contents = [load_content(load_skill_path(path)) for path in skill_paths]
    available = {
        content.skill.name: {profile.name for profile in content.profiles}
        for content in contents
    }
    result: dict[str, list[str]] = {}
    for selector in selectors:
        owner: str | None = None
        profile_name = selector
        if ":" in selector:
            owner, profile_name = selector.split(":", 1)
        owners = [owner] if owner else sorted(available)
        result[selector] = [
            name
            for name in owners
            if name in available
            and (
                (profile_name == "all" and bool(available[name]))
                or profile_name in available[name]
            )
        ]
    return result


class SkillResolver:
    def __init__(self, sources: Path | list[Path]) -> None:
        values = [sources] if isinstance(sources, Path) else sources
        self.skill_paths = discover_skill_paths(values)

    def collect(
        self, profiles: list[str] | None = None
    ) -> list[SkillBundle]:
        return collect_skills(self.skill_paths, profiles)

    def profile_matches(self, selectors: list[str]) -> dict[str, list[str]]:
        return profile_matches(self.skill_paths, selectors)
