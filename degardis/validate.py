from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from .markdown import (
    entry_filename,
    entry_markdown,
    skill_markdown,
    workflow_filename,
    workflow_markdown,
)
from .model import (
    Diagnostics,
    SUPPORTED_FORMAT_VERSIONS,
    DegardisError,
    Skill,
    SkillBundle,
    SkillContent,
)
from .registry import discover_skill_paths, load_skill_path
from .resolver import load_content, select_profiles


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
MANIFEST_FIELDS = {
    "name",
    "title",
    "format_version",
    "version",
    "license",
    "copyright",
    "description",
    "primary_workflow",
    "entry_kinds",
    "profiles",
    "content",
    "interface",
}
INTERFACE_FIELDS = {
    "display_name",
    "short_description",
    "default_prompt",
    "brand_color",
    "icon",
    "icon_small",
    "icon_large",
}
PROFILES_FIELDS = {"directory", "defaults"}
REQUIRED_MANIFEST_FIELDS = ("version", "description", "primary_workflow")
REQUIRED_INTERFACE_FIELDS = ("display_name", "short_description", "default_prompt")


def _validate_name(value: str, label: str) -> list[str]:
    errors: list[str] = []
    if not NAME_PATTERN.fullmatch(value) or len(value) > 64:
        errors.append(
            f"{label}: must be 1-64 lowercase letters, digits, or single hyphens"
        )
    if value == "all":
        errors.append(f"{label}: all is reserved")
    return errors


def _validate_non_empty_string(
    skill: Skill,
    data: dict,
    field: str,
    code: str,
    diagnostics: Diagnostics,
    *,
    required: bool = True,
) -> None:
    path = _manifest_path(skill)
    if field not in data:
        if required:
            diagnostics.error(f"{skill.name}: missing {field}", code, path)
        return
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        diagnostics.error(
            f"{skill.name}: {field} must be a non-empty string",
            "manifest.invalid-type",
            path,
        )


def _validate_manifest_types(skill: Skill, diagnostics: Diagnostics) -> None:
    manifest = skill.manifest
    path = _manifest_path(skill)
    for field in REQUIRED_MANIFEST_FIELDS:
        _validate_non_empty_string(
            skill, manifest, field, f"manifest.missing-{field}", diagnostics
        )
    format_version = manifest.get("format_version")
    if not isinstance(format_version, int) or isinstance(format_version, bool):
        diagnostics.error(
            f"{skill.name}: format_version must be an integer",
            "manifest.invalid-type",
            path,
        )
    elif format_version not in SUPPORTED_FORMAT_VERSIONS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_FORMAT_VERSIONS))
        diagnostics.error(
            f"{skill.name}: unsupported format_version {format_version}; "
            f"supported versions: {supported}",
            "manifest.unsupported-format-version",
            path,
        )
    _validate_non_empty_string(
        skill, manifest, "title", "manifest.invalid-type", diagnostics, required=False
    )

    entry_kinds = manifest.get("entry_kinds")
    if entry_kinds is not None and (
        not isinstance(entry_kinds, list)
        or any(not isinstance(item, str) or not item.strip() for item in entry_kinds)
    ):
        diagnostics.error(
            f"{skill.name}: entry_kinds must be a list of strings",
            "manifest.invalid-type",
            path,
        )

    profiles = manifest.get("profiles", {})
    if not isinstance(profiles, dict):
        diagnostics.error(
            f"{skill.name}: profiles must be a mapping", "manifest.invalid-type", path
        )
    else:
        defaults = profiles.get("defaults", [])
        if not isinstance(defaults, list) or any(
            not isinstance(item, str) or not item.strip() for item in defaults
        ):
            diagnostics.error(
                f"{skill.name}: profiles.defaults must be a list of strings",
                "manifest.invalid-type",
                path,
            )

    if "interface" not in manifest:
        for field in REQUIRED_INTERFACE_FIELDS:
            diagnostics.error(
                f"{skill.name}: interface.{field} is required",
                f"interface.missing-{field}",
                path,
            )
        return
    interface = manifest["interface"]
    if not isinstance(interface, dict):
        diagnostics.error(
            f"{skill.name}: interface must be a mapping", "manifest.invalid-type", path
        )
        return
    for field in REQUIRED_INTERFACE_FIELDS:
        if field not in interface:
            diagnostics.error(
                f"{skill.name}: interface.{field} is required",
                f"interface.missing-{field}",
                path,
            )
        elif (
            not isinstance(interface[field], str)
            or not interface[field].strip()
        ):
            diagnostics.error(
                f"{skill.name}: interface.{field} must be a non-empty string",
                "interface.invalid-type",
                path,
            )
    if "brand_color" in interface:
        value = interface["brand_color"]
        if not isinstance(value, str) or not value.strip():
            diagnostics.error(
                f"{skill.name}: interface.brand_color must be a non-empty string",
                "interface.invalid-type",
                path,
            )


def _validate_manifest_warnings(skill: Skill, diagnostics: Diagnostics) -> None:
    path = _manifest_path(skill)
    unknown_manifest = sorted(set(skill.manifest) - MANIFEST_FIELDS)
    if unknown_manifest:
        diagnostics.warning(
            f"{skill.name}: unrecognized manifest fields ignored: "
            f"{', '.join(unknown_manifest)}",
            "manifest.unknown-field",
            path,
        )
    profiles = skill.manifest.get("profiles")
    if isinstance(profiles, dict):
        unknown_profiles = sorted(set(profiles) - PROFILES_FIELDS)
        if unknown_profiles:
            diagnostics.warning(
                f"{skill.name}: unrecognized profiles fields ignored: "
                f"{', '.join(unknown_profiles)}",
                "manifest.unknown-profiles-field",
                path,
            )
    interface = skill.manifest.get("interface")
    if isinstance(interface, dict):
        unknown_interface = sorted(set(interface) - INTERFACE_FIELDS)
        if unknown_interface:
            diagnostics.warning(
                f"{skill.name}: unrecognized interface fields ignored: "
                f"{', '.join(unknown_interface)}",
                "interface.unknown-field",
                path,
            )


def _manifest_path(skill: Skill) -> Path:
    return skill.root / "skill.yaml"


def _check_generated_references(
    skill: Skill,
    content: SkillContent,
    diagnostics: Diagnostics,
) -> str:
    bundle = SkillBundle(primary=skill, contents=[content])
    try:
        rendered = skill_markdown(bundle, skill.name)
    except (DegardisError, ValueError) as exc:
        diagnostics.error(exc, "output.render-failed", _manifest_path(skill))
        return ""
    expected_references = {
        f"references/entries/{entry_filename(entry)}" for entry in content.entries
    }
    expected_references.update(
        f"references/workflows/{workflow_filename(workflow, skill.name)}"
        for workflow in content.workflows
        if workflow.get("id") != skill.primary_workflow
    )
    expected_references.update(
        f"references/profiles/{profile.filename}" for profile in content.profiles
    )
    expected_references.update(
        source.relative_to(skill.root).as_posix() for source in content.scripts
    )
    expected_references.update(
        source.relative_to(skill.root).as_posix() for source in content.assets
    )
    for link in MARKDOWN_LINK_PATTERN.findall(rendered):
        if link not in expected_references:
            diagnostics.error(
                f"{skill.name}: generated broken reference {link}",
                "output.broken-reference",
                _manifest_path(skill),
            )
    return rendered


def _empty_result(source: Path) -> dict[str, Any]:
    return {
        "name": source.name,
        "title": source.name,
        "title_derived": False,
        "version": "",
        "source": source,
        "description": "",
        "license": None,
        "copyright": None,
        "primary_workflow": "",
        "profiles": [],
        "selected_profiles": [],
        "default_profiles": [],
        "diagnostics": [],
        "errors": [],
        "warnings": [],
    }


def _selected_profiles(
    skill: Skill,
    content: SkillContent,
    selectors: list[str] | None,
    diagnostics: Diagnostics,
) -> list[str]:
    """Resolve the same profile selection a build would make, or report why not."""
    try:
        selection = select_profiles([content], selectors)
    except DegardisError as exc:
        diagnostics.error(exc, "profile.unknown-selector", _manifest_path(skill))
        return []
    return sorted(selection.get(skill.name, set()))


def _identity(skill: Skill) -> dict[str, Any]:
    """The fields a report states about the skill itself, before any check runs."""
    return {
        "name": skill.name,
        "title": skill.title,
        "title_derived": "title" not in skill.manifest,
        "version": skill.version,
        "source": skill.root.resolve(),
        "description": skill.description,
        "primary_workflow": skill.primary_workflow,
    }


def _check_manifest_fields(skill: Skill, diagnostics: Diagnostics) -> None:
    """Check the manifest's own field names, types, and lengths."""
    _validate_manifest_warnings(skill, diagnostics)
    diagnostics.add_errors(
        _validate_name(skill.name, f"{skill.name} name"),
        "manifest.invalid-name",
        _manifest_path(skill),
    )
    _validate_manifest_types(skill, diagnostics)
    description = skill.manifest.get("description")
    if isinstance(description, str) and len(description) > 1024:
        diagnostics.error(
            f"{skill.name}: description must be 1-1024 characters",
            "manifest.description-length",
            _manifest_path(skill),
        )


def _legal_metadata(skill: Skill, diagnostics: Diagnostics) -> dict[str, Any]:
    """Read license and copyright, reporting either one that is not a string.

    A field that fails to read is left out, so the report keeps the absent value
    it started with rather than a partial one.
    """
    metadata: dict[str, Any] = {}
    for field in ("license", "copyright"):
        try:
            metadata[field] = getattr(skill, field)
        except DegardisError as exc:
            diagnostics.error(exc, "manifest.invalid-type", _manifest_path(skill))
    return metadata


def _check_interface(skill: Skill, diagnostics: Diagnostics) -> None:
    """Check the interface fields an agent surface displays."""
    interface = skill.interface
    short_description = interface.get("short_description")
    if (
        isinstance(short_description, str)
        and short_description
        and not 25 <= len(short_description) <= 64
    ):
        diagnostics.error(
            f"{skill.name}: interface.short_description must be 25-64 characters",
            "interface.short_description-length",
            _manifest_path(skill),
        )
    default_prompt = interface.get("default_prompt")
    if (
        isinstance(default_prompt, str)
        and default_prompt
        and f"${skill.name}" not in default_prompt
    ):
        diagnostics.error(
            f"{skill.name}: interface.default_prompt must mention ${skill.name}",
            "interface.default_prompt-token",
            _manifest_path(skill),
        )


def _check_profile_metadata(
    skill: Skill,
    content: SkillContent,
    diagnostics: Diagnostics,
) -> None:
    """Check the name and description of every profile the skill resolved."""
    for profile in content.profiles:
        diagnostics.add_errors(
            _validate_name(profile.name, f"{skill.name} profile {profile.path.name}"),
            "profile.invalid-name",
            profile.path,
        )
        if not profile.description or len(profile.description) > 1024:
            diagnostics.error(
                f"{profile.path}: description must be 1-1024 characters",
                "profile.description-length",
                profile.path,
            )


def _check_workflow_references(
    skill: Skill,
    content: SkillContent,
    diagnostics: Diagnostics,
) -> bool:
    """Check that the primary workflow exists and every step reaches a known one.

    Returns whether the primary workflow was found. Without it there is no body
    to generate, so the caller measures no markdown for the skill.
    """
    workflow_ids = {str(workflow.get("id", "")) for workflow in content.workflows}
    primary_workflow_found = skill.primary_workflow in workflow_ids
    if not primary_workflow_found:
        diagnostics.error(
            f"{skill.name}: primary workflow not found: {skill.primary_workflow}",
            "workflow.missing-primary",
            _manifest_path(skill),
        )
    for workflow in content.workflows:
        for step in workflow.get("steps", []):
            if isinstance(step, dict) and step.get("use"):
                referenced = str(step["use"])
                if referenced not in workflow_ids:
                    diagnostics.error(
                        f"{workflow.get('_path')}: cross-skill or unknown "
                        f"workflow reference {referenced}",
                        "workflow.unknown-reference",
                        workflow.get("_path"),
                    )
    return primary_workflow_found


def _inspect_skill(path: Path, profiles: list[str] | None = None) -> dict[str, Any]:
    """Check one skill, collecting everything wrong with it rather than the first.

    A skill that cannot be loaded at all is reported on its own, since no later
    check has a source to read.
    """
    source = path.resolve()
    result = _empty_result(source)
    diagnostics = Diagnostics()
    try:
        skill = load_skill_path(path)
    except (DegardisError, OSError, UnicodeError) as exc:
        diagnostics.error(exc, "source.unreadable", source / "skill.yaml")
        return _finish(result, diagnostics)

    result.update(_identity(skill))
    _check_manifest_fields(skill, diagnostics)
    result.update(_legal_metadata(skill, diagnostics))
    _check_interface(skill, diagnostics)

    content = load_content(skill, diagnostics)
    _check_profile_metadata(skill, content, diagnostics)
    selected = _selected_profiles(skill, content, profiles, diagnostics)
    result["selected_profiles"] = selected
    primary_workflow_found = _check_workflow_references(skill, content, diagnostics)
    result["profiles"] = sorted(profile.name for profile in content.profiles)

    if primary_workflow_found:
        _check_generated_references(skill, content, diagnostics)
    return _finish(result, diagnostics)


def _finish(result: dict[str, Any], diagnostics: Diagnostics) -> dict[str, Any]:
    result["diagnostics"] = list(diagnostics.records)
    result["errors"] = diagnostics.errors
    result["warnings"] = diagnostics.warnings
    return result


def validate_skill(path: Path) -> list[str]:
    return _inspect_skill(path)["errors"]


def inspect_skills(
    paths: list[Path],
    profiles: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [_inspect_skill(path, profiles) for path in paths]


def validate(sources: Path | list[Path]) -> list[str]:
    values = [sources] if isinstance(sources, Path) else sources
    try:
        skill_paths = discover_skill_paths(values)
    except (DegardisError, OSError, UnicodeError) as exc:
        return [str(exc)]
    errors: list[str] = []
    for path in skill_paths:
        errors.extend(_inspect_skill(path)["errors"])
    return errors
