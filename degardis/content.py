"""What a manifest selects from the source tree, and what it may never select.

A Format 2 manifest never defaults a content key to a directory: a key it leaves
out says the skill ships none of that content. So this module answers one
question — which files does this pattern list name? — and reports a pattern that
names nothing, because a misspelled path, a wrongly cased one, or a `!` that now
removes nothing are invisible in the bundle that results.

Directory names in the recommended tree are conventional. The manifest key that
selected a file decides which schema the file must satisfy, so nothing here
infers a construct kind from where a file happens to sit.
"""

from __future__ import annotations

import fnmatch
import stat
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath

from .model import DegardisError, Diagnostics, Skill, ensure_within


# The content keys a manifest may set, in the order a report lists them. The
# first nine select source the compiler parses; the last three select files a
# build copies unchanged.
PARSED_CONTENT_KEYS: tuple[str, ...] = (
    "policies",
    "rules",
    "patterns",
    "heuristics",
    "guidance",
    "protocols",
    "records",
    "workflows",
    "profiles",
)
COPIED_CONTENT_KEYS: tuple[str, ...] = ("references", "scripts", "assets")
CONTENT_KEYS: tuple[str, ...] = (*PARSED_CONTENT_KEYS, *COPIED_CONTENT_KEYS)
ALLOWED_CONTENT_KEYS = frozenset(CONTENT_KEYS)

# The one content key a manifest must set. A skill with no workflow has no
# execution to render, so there would be nothing for `SKILL.md` to contain.
REQUIRED_CONTENT_KEYS: tuple[tuple[str, str], ...] = (
    ("workflows", "content.missing-workflows"),
)

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


def _is_bytecode(relative: Path) -> bool:
    """Whether a path is Python bytecode rather than authored content.

    Python writes bytecode beside the scripts a skill ships, so a pattern such
    as `scripts/**/*` matches it once those scripts have run. It is generated
    output of the author's own source and must never reach a bundle, where it
    would be stale on the first edit and wrong on another Python.
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


def matching_paths(root: Path, pattern: str) -> list[Path]:
    """Every path under root one pattern names, matched the same way anywhere.

    Path.glob defers each comparison to the host filesystem, which matches names
    without regard to case on Windows and macOS and with regard to it elsewhere.
    That makes which files a skill ships a property of the machine building it:
    `!RULES/one.yaml` drops `rules/one.yaml` on one host and nothing on the
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
        matches = matching_paths(skill.root, body)
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
                ensure_within(path, skill.root, f"{skill.name}: content files")
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


def content_config(skill: Skill, diagnostics: Diagnostics) -> dict:
    """The manifest's content mapping, reporting what it cannot be read as."""
    config = skill.manifest.get("content")
    if config is None:
        # `manifest.missing-content` already named this, from the manifest's own
        # required-field check. Reporting it again here would give one mistake
        # two codes and send the author looking for a second repair.
        return {}
    if not isinstance(config, dict):
        diagnostics.error(
            f"{skill.name}: content must be a mapping of content keys to glob "
            "patterns",
            "content.invalid-type",
            skill.root / "skill.yaml",
        )
        return {}
    unknown = sorted(set(config) - ALLOWED_CONTENT_KEYS)
    if unknown:
        diagnostics.error(
            f"{skill.name}: unrecognized content keys: {', '.join(unknown)}; "
            f"content selects {', '.join(CONTENT_KEYS)}",
            "content.unknown-field",
            skill.root / "skill.yaml",
        )
    for key, code in REQUIRED_CONTENT_KEYS:
        if key not in config:
            diagnostics.error(
                f"{skill.name}: content.{key} is required, because a skill with "
                f"no {key} has no execution to render",
                code,
                skill.root / "skill.yaml",
            )
    return config


def content_files(
    skill: Skill,
    config: dict,
    key: str,
    diagnostics: Diagnostics,
) -> list[Path]:
    """The files one content key selects, reporting a key that ships nothing.

    A key the manifest leaves out asks for no content of that kind, so nothing is
    resolved for it and nothing is reported. A key the manifest does declare is a
    statement that the skill ships those files, and the bundle is the one place
    that statement coming out empty never shows.
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
