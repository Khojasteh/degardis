from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .markdown import entry_filename, workflow_filename
from .icons import ICON_OUTPUTS, resolve_icon_sources, validate_icon_sources
from .model import (
    DegardisError,
    Entry,
    Skill,
    SkillBundle,
    SkillContent,
    ensure_within,
    load_yaml,
)
from .registry import discover_skill_paths, load_skill_path, load_skill_profiles


ALLOWED_CONTENT_KEYS = {"entries", "workflows", "scripts", "assets"}
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


def _glob(skill: Skill, patterns: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        pattern_path = skill.root / pattern
        ensure_within(
            pattern_path,
            skill.root,
            f"{skill.name}: content patterns",
        )
        for path in sorted(p for p in skill.root.glob(pattern) if p.is_file()):
            ensure_within(
                path,
                skill.root,
                f"{skill.name}: content files",
            )
            paths.append(path)
    return list(dict.fromkeys(paths))


def _content_patterns(
    skill: Skill,
    config: dict,
    key: str,
    default: list[str],
) -> list[str]:
    value = config.get(key, default)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise DegardisError(
            f"{skill.name}: content.{key} must be a list of non-empty strings"
        )
    return value


def _load_entry(path: Path, skill: Skill) -> Entry:
    data = load_yaml(path)
    unknown = sorted(set(data) - ALLOWED_ENTRY_FIELDS)
    if unknown:
        raise DegardisError(
            f"{path}: unsupported entry fields: {', '.join(unknown)}"
        )
    for key in ("id", "rule"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DegardisError(f"{path}: {key} must be a non-empty string")
    for key in ENTRY_TEXT_FIELDS - {"id", "rule"}:
        if key in data and not isinstance(data[key], str):
            raise DegardisError(f"{path}: {key} must be a string")
    kind = data.get("kind", "rule")
    if kind not in ALLOWED_ENTRY_KINDS:
        raise DegardisError(f"{path}: unsupported kind {kind}")
    priority = data.get("priority", 100)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise DegardisError(f"{path}: priority must be an integer")
    for key in ENTRY_LIST_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise DegardisError(f"{path}: {key} must be a list of strings")
    return Entry(path=path, data=data, skill=skill.name)


def _load_workflow(path: Path, skill: Skill) -> dict:
    data = load_yaml(path)
    unknown = sorted(set(data) - ALLOWED_WORKFLOW_FIELDS)
    if unknown:
        raise DegardisError(
            f"{path}: unsupported workflow fields: {', '.join(unknown)}"
        )
    workflow_id = data.get("id")
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise DegardisError(f"{path}: id must be a non-empty string")
    for key in ("title", "description"):
        if key in data and not isinstance(data[key], str):
            raise DegardisError(f"{path}: {key} must be a string")
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise DegardisError(f"{path}: steps must be a list")
    for index, step in enumerate(steps, start=1):
        label = f"{path}: step {index}"
        if isinstance(step, str):
            if not step.strip():
                raise DegardisError(f"{label} must be a non-empty string")
            continue
        if not isinstance(step, dict):
            raise DegardisError(f"{label} must be a string or mapping")
        unknown_step_fields = sorted(set(step) - ALLOWED_WORKFLOW_STEP_FIELDS)
        if unknown_step_fields:
            raise DegardisError(
                f"{label} has unsupported fields: "
                f"{', '.join(unknown_step_fields)}"
            )
        for key, value in step.items():
            if not isinstance(value, str) or not value.strip():
                raise DegardisError(f"{label} {key} must be a non-empty string")
        if "use" in step and ({"action", "instruction"} & set(step)):
            raise DegardisError(
                f"{label} use cannot be combined with action or instruction"
            )
        if not ({"use", "action", "id", "instruction"} & set(step)):
            raise DegardisError(
                f"{label} must define use, action, id, or instruction"
            )
    return data


def _validate_output_paths(content: SkillContent) -> None:
    claimed: dict[str, Path] = {}

    def claim(relative: str, source: Path) -> None:
        key = relative.casefold()
        previous = claimed.get(key)
        if previous is not None and previous != source:
            raise DegardisError(
                f"{content.skill.name}: output path collision at {relative}: "
                f"{previous} and {source}"
            )
        claimed[key] = source

    claim("SKILL.md", content.skill.root / "skill.yaml")
    claim("agents/openai.yaml", content.skill.root / "skill.yaml")
    for entry in content.entries:
        filename = entry_filename(entry)
        if filename == ".md":
            raise DegardisError(
                f"{entry.path}: entry id does not produce a valid filename"
            )
        claim(f"references/entries/{filename}", entry.path)
    for workflow in content.workflows:
        if workflow.get("id") == content.skill.primary_workflow:
            continue
        filename = workflow_filename(workflow, content.skill.name)
        if filename == ".md":
            raise DegardisError(
                f"{workflow.get('_path')}: workflow id does not produce "
                "a valid filename"
            )
        claim(f"references/workflows/{filename}", workflow["_path"])
    for profile in content.profiles:
        claim(f"references/profiles/{profile.filename}", profile.path)
    for source in [*content.scripts, *content.assets]:
        claim(source.relative_to(content.skill.root).as_posix(), source)
    for role, source in content.icon_sources.items():
        claim(ICON_OUTPUTS[role], source)


def load_content(skill: Skill) -> SkillContent:
    """Resolve every source one skill declares into the content a bundle ships."""
    content_config = skill.manifest.get("content", {})
    if not isinstance(content_config, dict):
        raise DegardisError(f"{skill.name}: content must be a mapping")
    unsupported = sorted(set(content_config) - ALLOWED_CONTENT_KEYS)
    if unsupported:
        raise DegardisError(
            f"{skill.name}: unsupported content fields: {', '.join(unsupported)}"
        )

    entries: list[Entry] = []
    for path in _glob(
        skill,
        _content_patterns(skill, content_config, "entries", ["entries/*.yaml"]),
    ):
        entries.append(_load_entry(path, skill))
    entries.sort(key=lambda entry: (entry.priority, entry.kind, entry.id))

    workflows: list[dict] = []
    workflow_paths: dict[str, Path] = {}
    for path in _glob(
        skill,
        _content_patterns(
            skill,
            content_config,
            "workflows",
            ["workflows/*.yaml"],
        ),
    ):
        data = _load_workflow(path, skill)
        workflow_id = data["id"]
        previous = workflow_paths.get(workflow_id)
        if previous is not None:
            raise DegardisError(
                f"{path}: duplicate workflow id {workflow_id}: "
                f"{previous} and {path}"
            )
        workflow_paths[workflow_id] = path
        data["_skill"] = skill.name
        data["_path"] = path
        workflows.append(data)

    scripts = _glob(
        skill,
        _content_patterns(skill, content_config, "scripts", ["scripts/**/*"]),
    )
    assets = _glob(
        skill,
        _content_patterns(skill, content_config, "assets", ["assets/**/*"]),
    )

    icon_sources = resolve_icon_sources(skill)
    validate_icon_sources(icon_sources)
    content = SkillContent(
        skill=skill,
        entries=entries,
        workflows=workflows,
        profiles=load_skill_profiles(skill),
        scripts=scripts,
        assets=assets,
        icon_sources=icon_sources,
    )
    _validate_output_paths(content)
    return content


def select_profiles(
    contents: list[SkillContent], selectors: list[str] | None
) -> dict[str, set[str]]:
    """Which profiles each skill ships, from the selectors the caller gave."""
    selected = {content.skill.name: set() for content in contents}
    available = {
        content.skill.name: {profile.name for profile in content.profiles}
        for content in contents
    }
    if selectors is None:
        for content in contents:
            config = content.skill.manifest.get("profiles", {})
            defaults = config.get("defaults", []) if isinstance(config, dict) else []
            unknown = set(map(str, defaults)) - available[content.skill.name]
            if unknown:
                raise DegardisError(
                    f"Unknown default profiles for {content.skill.name}: "
                    f"{', '.join(sorted(unknown))}"
                )
            selected[content.skill.name].update(map(str, defaults))
        return selected

    for selector in selectors:
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
