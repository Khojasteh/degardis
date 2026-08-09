from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from .icons import render_icon_assets
from .markdown import (
    entry_filename,
    entry_markdown,
    markdown_metrics,
    skill_markdown,
    skill_markdown_body,
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
from .package import (
    HOST_INVOCATION_PREFIXES,
    NAME_PLACEHOLDER,
    artifact_mode,
    openai_metadata,
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
DERIVED_MANIFEST_FIELDS = {"entry_kinds"}

# The required fields whose absence is its own check code, spelled out rather
# than composed, so every code a run can report is a literal in the source that
# `degardis explain` can be held to.
REQUIRED_MANIFEST_CODES = {
    "version": "manifest.missing-version",
    "description": "manifest.missing-description",
    "primary_workflow": "manifest.missing-primary_workflow",
}
REQUIRED_INTERFACE_CODES = {
    "display_name": "interface.missing-display_name",
    "short_description": "interface.missing-short_description",
    "default_prompt": "interface.missing-default_prompt",
}

# Sections of the agent report, in render order, naming what each reports. The
# four marked default answer "is it sound and what does it cost" without
# listing content the caller has not asked to act on.
AGENT_DIMENSIONS: dict[str, str] = {
    "skill": (
        "name, version, title, root, description length, primary workflow, "
        "and content counts"
    ),
    "identity": "the full description, license, and copyright",
    "budget": "generated SKILL.md size and the on-demand weight around it",
    "workflows": "each workflow, and the step that reaches it",
    "entries": "each entry's id, kind, priority, path, and size",
    "profiles": "each profile's name, selection, path, and size",
    "scripts": "selected script paths and sizes",
    "assets": "selected asset paths and sizes",
    "outputs": "every file a build would write, with size and mode",
    "diagnostics": "aggregated errors and warnings",
}
DEFAULT_AGENT_DIMENSIONS: tuple[str, ...] = (
    "skill",
    "budget",
    "workflows",
    "diagnostics",
)


def describe_agent_dimensions(names: tuple[str, ...] | None = None) -> str:
    """One aligned line per dimension, naming what it reports."""
    chosen = names if names is not None else tuple(AGENT_DIMENSIONS)
    width = max(len(name) for name in chosen)
    return "\n".join(f"  {name:<{width}} {AGENT_DIMENSIONS[name]}" for name in chosen)


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
    for field, code in REQUIRED_MANIFEST_CODES.items():
        _validate_non_empty_string(skill, manifest, field, code, diagnostics)
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
            "manifest.unsupported-format_version",
            path,
        )
    _validate_non_empty_string(
        skill, manifest, "title", "manifest.invalid-type", diagnostics, required=False
    )

    if "interface" not in manifest:
        for field, code in REQUIRED_INTERFACE_CODES.items():
            diagnostics.error(
                f"{skill.name}: interface.{field} is required",
                code,
                path,
            )
        return
    interface = manifest["interface"]
    if not isinstance(interface, dict):
        diagnostics.error(
            f"{skill.name}: interface must be a mapping", "manifest.invalid-type", path
        )
        return
    for field, code in REQUIRED_INTERFACE_CODES.items():
        if field not in interface:
            diagnostics.error(
                f"{skill.name}: interface.{field} is required",
                code,
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
    for field in sorted(DERIVED_MANIFEST_FIELDS & set(skill.manifest)):
        diagnostics.warning(
            f"{skill.name}: {field} is derived from the skill content; the "
            "manifest value is ignored and the field can be removed",
            "manifest.derived-field",
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
        "entry_kind_counts": {},
        "entries": [],
        "workflows": [],
        "profiles": [],
        "selected_profiles": [],
        "scripts": [],
        "assets": [],
        "counts": {
            "entries": 0,
            "workflows": 0,
            "profiles": 0,
            "scripts": 0,
            "assets": 0,
        },
        "skill_markdown": {
            "bytes": 0,
            "lines": 0,
            "body_bytes": 0,
            "body_lines": 0,
            "body_words": 0,
        },
        "skill_text": None,
        "reference_bytes": {"entries": 0, "workflows": 0, "profiles": 0},
        "outputs": [],
        "diagnostics": [],
        "errors": [],
        "warnings": [],
    }


def _workflow_reach(
    skill: Skill,
    content: SkillContent,
) -> dict[str, str]:
    """Map each workflow to the step that reaches it from the primary workflow.

    The reference index and the bundle both carry a supporting workflow whether
    or not a step invokes it, so an agent reviewing coverage needs the edge, not
    just the list.
    """
    known = {str(workflow["id"]): workflow for workflow in content.workflows}
    origin: dict[str, str] = {}
    if skill.primary_workflow in known:
        origin[skill.primary_workflow] = "primary"
    pending = [skill.primary_workflow]
    while pending:
        current = pending.pop(0)
        if current not in known:
            continue
        for index, step in enumerate(known[current].get("steps", []), start=1):
            if not isinstance(step, dict) or not step.get("use"):
                continue
            target = str(step["use"])
            if target in origin or target not in known:
                continue
            origin[target] = f"{current}.{index}"
            pending.append(target)
    return origin


def _bundle_outputs(
    skill: Skill,
    content: SkillContent,
    rendered: str,
) -> list[dict[str, Any]]:
    """List what a build would write, so nothing has to be built to see it."""
    outputs: list[dict[str, Any]] = []

    def add(relative: str, size: int) -> None:
        outputs.append(
            {"path": relative, "bytes": size, "mode": artifact_mode(relative)}
        )

    if rendered:
        add("SKILL.md", len(rendered.encode("utf-8")))
    for entry in content.entries:
        add(
            f"references/entries/{entry_filename(entry)}",
            len(entry_markdown(entry).encode("utf-8")),
        )
    for workflow in content.workflows:
        if workflow.get("id") == skill.primary_workflow:
            continue
        add(
            f"references/workflows/{workflow_filename(workflow, skill.name)}",
            len(workflow_markdown(workflow).encode("utf-8")),
        )
    for profile in content.profiles:
        add(
            f"references/profiles/{profile.filename}",
            len(profile.text.encode("utf-8")),
        )
    for source in [*content.scripts, *content.assets]:
        add(source.relative_to(skill.root).as_posix(), source.stat().st_size)
    for relative, data in render_icon_assets(content.icon_sources).items():
        add(relative, len(data))
    add(
        "agents/openai.yaml",
        len(
            openai_metadata(
                skill.interface,
                set(content.icon_sources),
                skill.name,
            ).encode("utf-8")
        ),
    )
    return sorted(outputs, key=lambda item: item["path"])


def _selected_profiles(
    skill: Skill,
    content: SkillContent,
    selectors: list[str] | None,
    diagnostics: Diagnostics,
) -> list[str]:
    """Resolve the same profile selection a build would make, or report why not."""
    if selectors is None:
        return []
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
        and NAME_PLACEHOLDER not in default_prompt
    ):
        # A source that spelled one host's invocation still names the skill, so
        # it builds; the warning says which host it silently committed to.
        hardcoded = next(
            (
                prefix
                for prefix in HOST_INVOCATION_PREFIXES
                if f"{prefix}{skill.name}" in default_prompt
            ),
            None,
        )
        if hardcoded:
            diagnostics.warning(
                f"{skill.name}: interface.default_prompt spells the invocation "
                f"{hardcoded}{skill.name} for one host; write "
                f"{NAME_PLACEHOLDER} and let each target render its own",
                "interface.default_prompt-literal-token",
                _manifest_path(skill),
            )
        else:
            diagnostics.error(
                f"{skill.name}: interface.default_prompt must mention "
                f"{NAME_PLACEHOLDER}",
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
        description = profile.description
        if description is not None and (
            not description.strip() or len(description) > 1024
        ):
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


def _measured_content(content: SkillContent, selected: list[str]) -> SkillContent:
    """The content a build would actually produce for this profile selection.

    Measuring the selection rather than every resolved profile keeps the reported
    numbers equal to a build's, rather than a variant nobody installs.
    """
    return SkillContent(
        skill=content.skill,
        entries=content.entries,
        workflows=content.workflows,
        profiles=[
            profile for profile in content.profiles if profile.name in selected
        ],
        scripts=content.scripts,
        assets=content.assets,
        icon_sources=content.icon_sources,
    )


def _file_inventory(skill: Skill, sources: list[Path]) -> list[dict[str, Any]]:
    """List copied sources by their path inside the skill, and their size."""
    return [
        {
            "path": item.relative_to(skill.root).as_posix(),
            "bytes": item.stat().st_size,
        }
        for item in sources
    ]


def _content_inventory(
    skill: Skill,
    content: SkillContent,
    selected: list[str],
) -> dict[str, Any]:
    """Inventory every resolved source, with the bytes each contributes."""
    counts: dict[str, int] = {}
    for entry in content.entries:
        counts[entry.kind] = counts.get(entry.kind, 0) + 1
    entries = [
        {
            "id": entry.id,
            "title": entry.title,
            "kind": entry.kind,
            "priority": entry.priority,
            "path": entry.path.relative_to(skill.root).as_posix(),
            "reference": f"references/entries/{entry_filename(entry)}",
            "bytes": len(entry_markdown(entry).encode("utf-8")),
        }
        for entry in content.entries
    ]
    reach = _workflow_reach(skill, content)
    workflows = [
        {
            "id": str(workflow["id"]),
            "title": str(workflow.get("title", workflow["id"])),
            "path": Path(workflow["_path"]).relative_to(skill.root).as_posix(),
            "steps": len(workflow.get("steps", [])),
            "reached_by": reach.get(str(workflow["id"]), ""),
            "bytes": len(workflow_markdown(workflow).encode("utf-8")),
        }
        for workflow in sorted(
            content.workflows,
            key=lambda item: (
                str(item["id"]) != skill.primary_workflow,
                str(item["id"]),
            ),
        )
    ]
    profiles = [
        {
            "name": profile.name,
            "label": profile.label,
            "path": profile.path.relative_to(skill.root).as_posix(),
            "selected": profile.name in selected,
            "bytes": len(profile.text.encode("utf-8")),
        }
        for profile in sorted(content.profiles, key=lambda item: item.name)
    ]
    return {
        "entry_kind_counts": dict(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "entries": entries,
        "workflows": workflows,
        "profiles": profiles,
        "scripts": _file_inventory(skill, content.scripts),
        "assets": _file_inventory(skill, content.assets),
        "reference_bytes": {
            "entries": sum(item["bytes"] for item in entries),
            "workflows": sum(
                item["bytes"]
                for item in workflows
                if item["reached_by"] != "primary"
            ),
            "profiles": sum(item["bytes"] for item in profiles if item["selected"]),
        },
        "counts": {
            "entries": len(content.entries),
            "workflows": len(content.workflows),
            "profiles": len(content.profiles),
            "scripts": len(content.scripts),
            "assets": len(content.assets),
        },
    }


def _inspect_skill(
    path: Path,
    profiles: list[str] | None = None,
    *,
    include_body: bool = False,
) -> dict[str, Any]:
    """Check one skill and inventory what a build would produce from it.

    Checking comes first and only reports; the inventory that follows measures
    the sources the checks accepted. A skill that cannot be loaded at all is
    reported without either.
    """
    source = path.resolve()
    result = _empty_result(source)
    diagnostics = Diagnostics()
    try:
        skill = load_skill_path(path)
    except (DegardisError, OSError, UnicodeError) as exc:
        diagnostics.source_failure(exc, source / "skill.yaml", "source.unreadable")
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

    measured = _measured_content(content, selected)
    rendered = ""
    if primary_workflow_found:
        rendered = _check_generated_references(skill, measured, diagnostics)
        if rendered:
            result["skill_markdown"] = markdown_metrics(rendered)
            if include_body:
                result["skill_text"] = skill_markdown_body(rendered)
    result["outputs"] = _bundle_outputs(skill, measured, rendered)
    result.update(_content_inventory(skill, content, selected))
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
    *,
    include_body: bool = False,
) -> list[dict[str, Any]]:
    return [
        _inspect_skill(path, profiles, include_body=include_body) for path in paths
    ]


def select_agent_dimensions(dimensions: list[str] | None) -> tuple[str, ...]:
    """Resolve the requested sections, keeping the rendering order fixed."""
    if not dimensions:
        return DEFAULT_AGENT_DIMENSIONS
    unknown = sorted(set(dimensions) - set(AGENT_DIMENSIONS))
    if unknown:
        raise DegardisError(
            f"Unknown dimensions: {', '.join(unknown)}; available:\n"
            f"{describe_agent_dimensions()}"
        )
    selected = set(dimensions) | {"skill"}
    return tuple(name for name in AGENT_DIMENSIONS if name in selected)


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
