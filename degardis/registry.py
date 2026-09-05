"""Find the skills a command was pointed at, and read each manifest.

Discovery runs before any check, so it reports only what would otherwise make a
command act on the wrong tree: a path that is not a skill, an archive or a built
bundle handed over in place of source, and two skills claiming one name. Every
other manifest problem is a finding a report carries, because a manifest that
names a missing workflow is still a manifest whose identity a report can name.
"""

from __future__ import annotations

import re
from pathlib import Path

from .content import content_config
from .model import (
    CURRENT_FORMAT_VERSION,
    DegardisError,
    Diagnostics,
    Skill,
    SourceError,
)
from .yamlsource import load_yaml


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# What a manifest may declare. `content` selects source; the four construct keys
# beside it bind constructs for the complete run. A manifest declares no
# run-level pattern or heuristic: a pattern is selected at a workflow step and a
# heuristic at a decision or gate, because neither is binding by being available.
MANIFEST_FIELDS = frozenset(
    {
        "name",
        "format_version",
        "version",
        "license",
        "copyright",
        "description",
        "primary_workflow",
        "policies",
        "rules",
        "protocols",
        "guidance",
        "content",
        "interface",
    }
)
# Each required manifest field with the literal code its absence reports, in
# the same shape as REQUIRED_INTERFACE_FIELDS below: one code per key, so an
# author who knows the key can build the code, and a coverage check can find
# every code this module reports by reading the source. `name` is read before
# any other check, because discovery needs it to identify the skill at all.
REQUIRED_MANIFEST_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "manifest.missing-name"),
    ("format_version", "manifest.missing-format_version"),
    ("version", "manifest.missing-version"),
    ("description", "manifest.missing-description"),
    ("primary_workflow", "manifest.missing-primary_workflow"),
    ("content", "manifest.missing-content"),
    ("interface", "manifest.missing-interface"),
)

# The constructs a manifest may bind for the complete run, and the content key
# each is selected from.
MANIFEST_BINDING_KEYS: tuple[str, ...] = ("policies", "rules", "protocols", "guidance")

INTERFACE_FIELDS = frozenset(
    {
        "display_name",
        "short_description",
        "icon",
        "brand_color",
        "default_prompt",
    }
)
# Each required interface field with the literal code its absence reports.
# Written out rather than assembled, so a coverage check can find every code
# this module can report by reading the source.
REQUIRED_INTERFACE_FIELDS: tuple[tuple[str, str], ...] = (
    ("display_name", "interface.missing-display_name"),
    ("short_description", "interface.missing-short_description"),
    ("default_prompt", "interface.missing-default_prompt"),
)

# A host lists many skills at once, so a short description that runs past this
# is a description the reader never finishes.
SHORT_DESCRIPTION_LIMIT = 60
DESCRIPTION_LIMIT = 1024

NAME_PLACEHOLDER = "{name}"
HOST_INVOCATION_PREFIXES = ("$", "/", "@", "#")
BRAND_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_skill_path(root: Path) -> Skill:
    path = root / "skill.yaml"
    if not path.is_file():
        raise DegardisError(f"Missing skill manifest: {path}", "manifest.missing")
    manifest = load_yaml(path)
    name = str(manifest.get("name", ""))
    if not name:
        raise SourceError(f"{path}: name is required", "manifest.missing-name", path)
    if root.name != name:
        raise SourceError(
            f"{path}: skill directory {root.name} does not match manifest name "
            f"{name}",
            "manifest.name-mismatch",
            path,
        )
    _require_current_format(root, manifest)
    return Skill(name=name, root=root, manifest=manifest)


def _require_current_format(root: Path, manifest: dict) -> None:
    """Accept only this compiler's current format.

    format_version numbering starts at 1, so zero or below was never valid at
    any point. A version below the current one was written for an earlier
    compiler; a version above it was written for a later compiler this one does
    not know how to read. Neither is convertible here: Format 2 is the first
    released source format, and its constructs — typed workflow inputs, declared
    outcomes, gates, and graph edges — are not derivable from a source that
    never carried them.
    """
    path = root / "skill.yaml"
    if "format_version" not in manifest:
        raise SourceError(
            f"{path}: format_version is required, and is the integer "
            f"{CURRENT_FORMAT_VERSION}",
            "manifest.missing-format_version",
            path,
        )
    version = manifest.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise SourceError(
            f"{path}: format_version must be the integer {CURRENT_FORMAT_VERSION}",
            "manifest.invalid-format_version",
            path,
        )
    if version == CURRENT_FORMAT_VERSION:
        return
    if version <= 0:
        raise SourceError(
            f"{path}: format_version {version} is not a valid format version",
            "manifest.invalid-format_version",
            path,
        )
    if version < CURRENT_FORMAT_VERSION:
        raise SourceError(
            f"{path}: format_version {version} is an earlier source format, and "
            f"no command converts one; rewrite the source as format "
            f"{CURRENT_FORMAT_VERSION}",
            "manifest.obsolete-format_version",
            path,
        )
    raise SourceError(
        f"{path}: format_version {version} is newer than this compiler supports "
        f"({CURRENT_FORMAT_VERSION}); install a newer degardis release to read it",
        "manifest.unsupported-format_version",
        path,
    )


def _reject_generated_bundle(path: Path) -> None:
    """Stop a source command from reading what a build produced.

    A bundle carries no skill.yaml, so discovery would descend past it and pick
    up any template a skill ships as an asset, reporting a pass for a skill the
    caller never named.
    """
    if (path / "skill.yaml").is_file() or not (path / "SKILL.md").is_file():
        return
    raise DegardisError(
        f"{path} is a generated skill bundle, not Degardis source. Point this "
        "command at the authored source directory containing skill.yaml.",
        "source.generated-bundle",
    )


def discover_skill_paths(sources: list[Path] | tuple[Path, ...]) -> list[Path]:
    discovered: list[Path] = []
    for source in sources:
        path = source.resolve()
        if path.is_file() and path.suffix.casefold() == ".zip":
            raise DegardisError(
                f"{path} is a skill archive, not Degardis source. Point this "
                "command at the authored source directory containing skill.yaml.",
                "source.archive-input",
            )
        if not path.is_dir():
            raise DegardisError(f"Skill path is not a directory: {path}")
        _reject_generated_bundle(path)
        if (path / "skill.yaml").is_file():
            candidates = [path]
        else:
            candidates = _discover_skill_directories(path)
            if not candidates:
                raise DegardisError(f"No skills found inside: {path}")
        for candidate in candidates:
            if candidate not in discovered:
                discovered.append(candidate)

    names: dict[str, Path] = {}
    for path in discovered:
        try:
            skill = load_skill_path(path)
        except (DegardisError, OSError, UnicodeError):
            # A manifest that cannot be read has no name to collide with, and
            # discovery is not the place its failure belongs: a command that
            # reports on skills has to reach this one to report it, inside its
            # own report and against the check that found it. Commands that only
            # build raise the same failure when they go on to load the skill.
            continue
        previous = names.get(skill.name)
        if previous and previous != path:
            raise DegardisError(
                f"Duplicate skill name {skill.name}: {previous}, {path}"
            )
        names[skill.name] = path
    return discovered


def _discover_skill_directories(root: Path) -> list[Path]:
    """Find descendant skills without treating their contents as collections."""
    discovered: list[Path] = []
    pending = [root]
    visited: set[Path] = set()
    while pending:
        directory = pending.pop()
        resolved = directory.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        children = sorted(
            (child.resolve() for child in directory.iterdir() if child.is_dir()),
            reverse=True,
        )
        for child in children:
            if (child / "skill.yaml").is_file():
                discovered.append(child)
            else:
                _reject_generated_bundle(child)
                pending.append(child)
    return sorted(discovered)


def check_manifest(skill: Skill, diagnostics: Diagnostics) -> dict:
    """Check every manifest field, and return the content configuration it names.

    The format version, the name, and the directory match are already settled by
    the load that produced this Skill, since a command cannot report on a source
    it could not identify. Everything else is a finding.
    """
    path = skill.root / "skill.yaml"
    manifest = skill.manifest

    def error(message: str, code: str) -> None:
        diagnostics.error(f"{path}: {message}", code, path)

    unknown = sorted(set(manifest) - MANIFEST_FIELDS)
    if unknown:
        error(
            f"unrecognized manifest fields: {', '.join(unknown)}; a manifest "
            f"declares {', '.join(sorted(MANIFEST_FIELDS))}",
            "manifest.unknown-field",
        )
    for field, code in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            error(f"{field} is required", code)

    if not NAME_PATTERN.fullmatch(skill.name):
        error(
            "name must be lowercase letters, digits, and single hyphens",
            "manifest.invalid-name",
        )
    for field in ("version", "description", "primary_workflow"):
        value = manifest.get(field)
        if field in manifest and (not isinstance(value, str) or not value.strip()):
            error(f"{field} must be a non-empty string", "manifest.invalid-type")
    for field in ("license", "copyright"):
        value = manifest.get(field)
        if field in manifest and (not isinstance(value, str) or not value.strip()):
            error(f"{field} must be a non-empty string", "manifest.invalid-type")
    description = manifest.get("description")
    if isinstance(description, str) and len(description) > DESCRIPTION_LIMIT:
        diagnostics.warning(
            f"{path}: description is {len(description)} characters; a host "
            f"selecting a skill reads at most about {DESCRIPTION_LIMIT}",
            "manifest.description-length",
            path,
        )
    primary = manifest.get("primary_workflow")
    if isinstance(primary, str) and primary and not NAME_PATTERN.fullmatch(primary):
        error(
            "primary_workflow must name a workflow file stem, in lowercase "
            "letters, digits, and single hyphens",
            "manifest.invalid-name",
        )

    for key in MANIFEST_BINDING_KEYS:
        if key not in manifest:
            continue
        value = manifest[key]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) for item in value)
            or any(not NAME_PATTERN.fullmatch(item) for item in value)
        ):
            error(
                f"{key} must be a non-empty list of file stems, in lowercase "
                "letters, digits, and single hyphens",
                "manifest.invalid-type",
            )
            continue
        repeated = sorted({item for item in value if value.count(item) > 1})
        if repeated:
            error(
                f"{key} names {', '.join(repeated)} more than once",
                "manifest.duplicate-binding",
            )

    _check_interface(skill, diagnostics)
    return content_config(skill, diagnostics)


def _check_interface(skill: Skill, diagnostics: Diagnostics) -> None:
    path = skill.root / "skill.yaml"
    interface = skill.manifest.get("interface")

    def error(message: str, code: str) -> None:
        diagnostics.error(f"{path}: {message}", code, path)

    if "interface" not in skill.manifest:
        return
    if not isinstance(interface, dict):
        error("interface must be a mapping of display fields", "interface.invalid-type")
        return
    unknown = sorted(set(interface) - INTERFACE_FIELDS)
    if unknown:
        error(
            f"unrecognized interface fields: {', '.join(unknown)}; interface "
            f"declares {', '.join(sorted(INTERFACE_FIELDS))}",
            "interface.unknown-field",
        )
    for field, code in REQUIRED_INTERFACE_FIELDS:
        value = interface.get(field)
        if field not in interface:
            error(f"interface.{field} is required", code)
        elif not isinstance(value, str) or not value.strip():
            error(
                f"interface.{field} must be a non-empty string",
                "interface.invalid-type",
            )
    short = interface.get("short_description")
    if isinstance(short, str) and len(short) > SHORT_DESCRIPTION_LIMIT:
        diagnostics.warning(
            f"{path}: interface.short_description is {len(short)} characters; a "
            f"host listing skills shows about {SHORT_DESCRIPTION_LIMIT}",
            "interface.short_description-length",
            path,
        )
    color = interface.get("brand_color")
    if "brand_color" in interface and (
        not isinstance(color, str) or not BRAND_COLOR_PATTERN.fullmatch(color)
    ):
        error(
            "interface.brand_color must be a six-digit hex colour such as "
            "'#5B4B8A'",
            "interface.invalid-type",
        )
    prompt = interface.get("default_prompt")
    if isinstance(prompt, str) and prompt.strip():
        _check_default_prompt(prompt, path, diagnostics)


def _check_default_prompt(prompt: str, path: Path, diagnostics: Diagnostics) -> None:
    """Hold the invocation prompt to a placeholder no host's syntax replaces.

    Every target renders the prompt in its own invocation syntax, so a source
    that spells one host's prefix literally reaches every other host wrong. The
    placeholder is the only portable way to name the invoked skill.
    """
    for prefix in HOST_INVOCATION_PREFIXES:
        if re.search(rf"(?<!\w)\{prefix}[a-z0-9][a-z0-9-]*", prompt):
            diagnostics.error(
                f"{path}: interface.default_prompt spells a host invocation "
                f"syntax ({prefix}) literally, which reaches every other host "
                f"verbatim; write {NAME_PLACEHOLDER} where the skill is named",
                "interface.default_prompt-literal-token",
                path,
            )
            return
    if NAME_PLACEHOLDER not in prompt:
        diagnostics.warning(
            f"{path}: interface.default_prompt names no skill; write "
            f"{NAME_PLACEHOLDER} where the invoked skill belongs",
            "interface.default_prompt-token",
            path,
        )
