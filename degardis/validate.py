from __future__ import annotations

import re
from pathlib import Path

from .markdown import entry_filename, skill_markdown, workflow_filename
from .model import (
    SUPPORTED_FORMAT_VERSIONS,
    DegardisError,
    Skill,
    SkillBundle,
)
from .registry import discover_skill_paths, load_skill_path, load_skill_profiles
from .resolver import collect_skills
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
SKILL_MD_RECOMMENDED_LINES = 500


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
    data: dict,
    field: str,
    label: str,
    *,
    required: bool = True,
) -> list[str]:
    if field not in data:
        return [f"{label}: missing {field}"] if required else []
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        return [f"{label}: {field} must be a non-empty string"]
    return []


def _validate_manifest_types(skill: Skill) -> list[str]:
    manifest = skill.manifest
    errors: list[str] = []
    for field in ("version", "description", "primary_workflow"):
        errors.extend(_validate_non_empty_string(manifest, field, skill.name))
    format_version = manifest.get("format_version")
    if not isinstance(format_version, int) or isinstance(format_version, bool):
        errors.append(f"{skill.name}: format_version must be an integer")
    elif format_version not in SUPPORTED_FORMAT_VERSIONS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_FORMAT_VERSIONS))
        errors.append(
            f"{skill.name}: unsupported format_version {format_version}; "
            f"supported versions: {supported}"
        )
    errors.extend(
        _validate_non_empty_string(
            manifest,
            "title",
            skill.name,
            required=False,
        )
    )

    entry_kinds = manifest.get("entry_kinds")
    if entry_kinds is not None and (
        not isinstance(entry_kinds, list)
        or any(not isinstance(item, str) or not item.strip() for item in entry_kinds)
    ):
        errors.append(f"{skill.name}: entry_kinds must be a list of strings")

    profiles = manifest.get("profiles", {})
    if not isinstance(profiles, dict):
        errors.append(f"{skill.name}: profiles must be a mapping")
    else:
        defaults = profiles.get("defaults", [])
        if (
            not isinstance(defaults, list)
            or any(not isinstance(item, str) or not item.strip() for item in defaults)
        ):
            errors.append(
                f"{skill.name}: profiles.defaults must be a list of strings"
            )

    if "interface" not in manifest:
        for field in ("display_name", "short_description", "default_prompt"):
            errors.append(f"{skill.name}: interface.{field} is required")
        return errors
    interface = manifest["interface"]
    if not isinstance(interface, dict):
        errors.append(f"{skill.name}: interface must be a mapping")
        return errors
    for field in ("display_name", "short_description", "default_prompt"):
        if field not in interface:
            errors.append(f"{skill.name}: interface.{field} is required")
        elif (
            not isinstance(interface[field], str)
            or not interface[field].strip()
        ):
            errors.append(
                f"{skill.name}: interface.{field} must be a non-empty string"
            )
    if "brand_color" in interface:
        value = interface["brand_color"]
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"{skill.name}: interface.brand_color must be a non-empty string"
            )
    return errors


def bundle_warnings(bundle: SkillBundle) -> list[str]:
    rendered = skill_markdown(bundle, bundle.primary.name)
    line_count = len(rendered.splitlines())
    if line_count <= SKILL_MD_RECOMMENDED_LINES:
        return []
    return [
        f"{bundle.primary.name}: generated SKILL.md has {line_count} lines; "
        f"the recommended maximum is {SKILL_MD_RECOMMENDED_LINES}"
    ]


def validate_skill(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        skill = load_skill_path(path)
        errors.extend(_validate_name(skill.name, f"{skill.name} name"))
        manifest_errors = _validate_manifest_types(skill)
        errors.extend(manifest_errors)
        if manifest_errors:
            return errors
        if "dependencies" in skill.manifest:
            errors.append(f"{skill.name}: dependencies is not supported")
        description = skill.manifest.get("description")
        if isinstance(description, str) and len(description) > 1024:
            errors.append(
                f"{skill.name}: description must be 1-1024 characters"
            )
        skill.license
        skill.copyright
        interface = skill.interface
        short_description = interface.get("short_description")
        if (
            isinstance(short_description, str)
            and short_description
            and not 25 <= len(short_description) <= 64
        ):
            errors.append(
                f"{skill.name}: interface.short_description must be 25-64 characters"
            )
        default_prompt = interface.get("default_prompt")
        if (
            isinstance(default_prompt, str)
            and default_prompt
            and f"${skill.name}" not in default_prompt
        ):
            errors.append(
                f"{skill.name}: interface.default_prompt must mention ${skill.name}"
            )

        bundle = collect_skills([path])[0]
        content = bundle.content(skill.name)
        workflow_ids = {
            str(workflow.get("id", "")) for workflow in content.workflows
        }
        primary_workflow_found = skill.primary_workflow in workflow_ids
        if not primary_workflow_found:
            errors.append(
                f"{skill.name}: primary workflow not found: "
                f"{skill.primary_workflow}"
            )
        for workflow in content.workflows:
            if not workflow.get("id") or not isinstance(
                workflow.get("steps"), list
            ):
                errors.append(
                    f"{skill.name}: invalid workflow {workflow.get('id')}"
                )
                continue
            for step in workflow["steps"]:
                if isinstance(step, dict) and step.get("use"):
                    referenced = str(step["use"])
                    if referenced not in workflow_ids:
                        errors.append(
                            f"{workflow.get('_path')}: cross-skill or unknown "
                            f"workflow reference {referenced}"
                        )

        if primary_workflow_found:
            rendered = skill_markdown(bundle, skill.name)
            expected_references = {
                f"references/entries/{entry_filename(entry)}"
                for entry in content.entries
            }
            expected_references.update(
                f"references/workflows/{workflow_filename(workflow, skill.name)}"
                for workflow in content.workflows
                if workflow.get("id") != skill.primary_workflow
            )
            expected_references.update(
                f"references/profiles/{profile.filename}"
                for profile in content.profiles
            )
            expected_references.update(
                source.relative_to(skill.root).as_posix()
                for source in content.scripts
            )
            expected_references.update(
                source.relative_to(skill.root).as_posix()
                for source in content.assets
            )
            for link in MARKDOWN_LINK_PATTERN.findall(rendered):
                if link not in expected_references:
                    errors.append(f"{skill.name}: generated broken reference {link}")

        for profile in load_skill_profiles(skill):
            errors.extend(
                _validate_name(
                    profile.name, f"{skill.name} profile {profile.path.name}"
                )
            )
            if not profile.description or len(profile.description) > 1024:
                errors.append(
                    f"{profile.path}: description must be 1-1024 characters"
                )
    except (DegardisError, OSError, UnicodeError) as exc:
        errors.append(str(exc))
    return errors


def validate(sources: Path | list[Path]) -> list[str]:
    values = [sources] if isinstance(sources, Path) else sources
    try:
        skill_paths = discover_skill_paths(values)
    except (DegardisError, OSError, UnicodeError) as exc:
        return [str(exc)]
    errors: list[str] = []
    for path in skill_paths:
        errors.extend(validate_skill(path))
    return errors
