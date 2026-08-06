from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .markdown import entry_filename, workflow_filename
from .icons import ICON_OUTPUTS, resolve_icon_sources, validate_icon_sources
from .model import (
    DegardisError,
    Diagnostics,
    Entry,
    Profile,
    Skill,
    SkillBundle,
    SkillContent,
    ensure_within,
    load_yaml,
)
from .registry import (
    discover_skill_paths,
    load_profile,
    load_skill_path,
    profile_source_paths,
)


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


def _glob(
    skill: Skill,
    patterns: Iterable[str],
    diagnostics: Diagnostics,
) -> list[Path]:
    """The files a pattern list selects, reporting the ones that reach outside."""
    paths: list[Path] = []
    for pattern in patterns:
        try:
            ensure_within(
                skill.root / pattern,
                skill.root,
                f"{skill.name}: content patterns",
            )
        except DegardisError as exc:
            diagnostics.error(exc, "content.outside-skill")
            continue
        for path in sorted(p for p in skill.root.glob(pattern) if p.is_file()):
            try:
                ensure_within(
                    path,
                    skill.root,
                    f"{skill.name}: content files",
                )
            except DegardisError as exc:
                diagnostics.error(exc, "content.outside-skill", path)
                continue
            paths.append(path)
    return list(dict.fromkeys(paths))


def _content_patterns(
    skill: Skill,
    config: dict,
    key: str,
    default: list[str],
    diagnostics: Diagnostics,
) -> list[str] | None:
    """One content key's patterns, or None where the manifest gave none usable."""
    value = config.get(key, default)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        diagnostics.error(
            f"{skill.name}: content.{key} must be a list of non-empty strings",
            "content.invalid-type",
            skill.root / "skill.yaml",
        )
        return None
    return value


def _content_files(
    skill: Skill,
    config: dict,
    key: str,
    default: list[str],
    diagnostics: Diagnostics,
) -> list[Path]:
    """The files one content key selects."""
    patterns = _content_patterns(skill, config, key, default, diagnostics)
    if patterns is None:
        return []
    return _glob(skill, patterns, diagnostics)


def _load_entry(
    path: Path,
    skill: Skill,
    diagnostics: Diagnostics | None = None,
) -> Entry | None:
    collector = diagnostics if diagnostics is not None else Diagnostics()
    try:
        data = load_yaml(path)
    except DegardisError as exc:
        collector.error(exc, "source.invalid-yaml", path)
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
        collector.error(exc, "source.invalid-yaml", path)
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
    patterns = ["entries/*.yaml"]
    for path in _content_files(skill, config, "entries", patterns, diagnostics):
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
    patterns = ["workflows/*.yaml"]
    for path in _content_files(skill, config, "workflows", patterns, diagnostics):
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


def _load_profiles(skill: Skill, diagnostics: Diagnostics) -> list[Profile]:
    """Load every profile the skill defines, ordered by name.

    Name order is the order a reader chooses a profile in, so the generated
    guidance does not depend on the order the directory happened to list.
    """
    try:
        paths = profile_source_paths(skill)
    except DegardisError as exc:
        diagnostics.error(exc, "profile.invalid-directory", skill.root / "skill.yaml")
        return []
    profiles: list[Profile] = []
    for path in paths:
        try:
            profile = load_profile(path, skill.name, skill.root, diagnostics)
        except (OSError, UnicodeError) as exc:
            diagnostics.error(exc, "source.unreadable", path)
            continue
        if profile is not None:
            profiles.append(profile)
    profiles.sort(key=lambda profile: profile.name)
    return profiles


def _load_icons(skill: Skill, diagnostics: Diagnostics) -> dict[str, Path]:
    """Resolve the interface icon sources, reporting any that cannot be used."""
    try:
        icon_sources = resolve_icon_sources(skill)
        validate_icon_sources(icon_sources)
    except (DegardisError, OSError, UnicodeError) as exc:
        diagnostics.error(exc, "icon.invalid", skill.root / "skill.yaml")
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
    config = _content_config(skill, collector)

    entries = _load_entries(skill, config, collector)
    workflows = _load_workflows(skill, config, collector)
    profiles = _load_profiles(skill, collector)
    scripts = _content_files(skill, config, "scripts", ["scripts/**/*"], collector)
    assets = _content_files(skill, config, "assets", ["assets/**/*"], collector)
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
    """Which profiles each skill ships, from the selectors the caller gave."""
    selected: dict[str, set[str]] = {content.skill.name: set() for content in contents}
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
