"""Every check the compiler runs, and the one inspection result each report reads.

`inspect_skills` compiles each selected skill once and returns one dictionary per
skill. `validate`, the `inspect` line report, and `build` all read that same
dictionary, so the three cannot disagree about what a source contains or about
which findings it has. Anything that checks a source belongs in `compile_skill`
rather than on one output path.

The checks fall into three groups. Reading and schema checks are delegated to the
modules that own them — the loader, the manifest reader, and the construct
readers. Relation checks live here: whether every principle the skill selects
exists, whether every knowledge reference resolves, whether a requirement chain
closes, and whether every file a generated page links to is a file the bundle
ships. Placement is delegated to the planner and page size to the renderer, each
of which is the only part that knows what it decided.

What none of them check is whether the skill is any good. A pass means the source
compiles to a complete, self-consistent bundle whose links resolve. Whether the
knowledge on a task page is the knowledge that task needs is a judgement about
expertise, and it is established by using the skill, not by compiling it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis import Plan, Quality, measure, plan_skill
from .bundlepaths import (
    OPENAI_METADATA,
    PROFILE_INDEX,
    RESERVED_PROFILE_IDS,
    ROOT,
    copied_path,
    guide_path,
    principle_path,
    profile_path,
)
from .content import (
    CONTENT_KEYS,
    COPIED_CONTENT_KEYS,
    PARSED_CONTENT_KEYS,
    content_files,
)
from .fingerprint import source_fingerprint
from .icons import IconError, render_icon_assets, resolve_icon_sources
from .markdown import MARKDOWN_SUFFIXES, read_markdown
from .model import DegardisError, Diagnostic, Diagnostics, Skill
from .package import artifact_mode, openai_metadata
from .progress import Progress, Scope
from .registry import check_manifest, discover_skill_paths, load_skill_path
from .render import (
    PRINCIPLE_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
    RenderedBundle,
    render_skill,
)
from .sources import (
    CONSTRUCT_LABELS,
    KNOWLEDGE_KINDS,
    SourceSet,
    construct_key,
    read_construct,
)
from .yamlsource import yaml_scalar_warnings


INSPECT_DIMENSIONS: dict[str, str] = {
    "skill": (
        "name, version, title, root, description length, generated page sizes, "
        "and one count per selected content key"
    ),
    "identity": (
        "the full description and purpose, license, copyright, and source digest"
    ),
    "sources": "every selected source file, its construct kind, id, and size",
    "tasks": (
        "each task, its recognition cues, its goal, and the page it compiles to"
    ),
    "knowledge": (
        "each knowledge unit, what it requires, and which task pages carry it"
    ),
    "principles": (
        "each principle this skill names, its source, owners, and activation conditions"
    ),
    "profiles": "each profile, its category, and its description",
    "guides": "each guide, its activation, and the tasks that name it",
    "composition": (
        "why each task page carries what it carries: direct knowledge, required "
        "knowledge and the page written"
    ),
    "quality": (
        "orphan and near-duplicate knowledge, constraint ratio, "
        "closure duplication, startup bytes, page-budget headroom, and one-load "
        "bytes by task"
    ),
    "outputs": "every file a build would write, with size and mode",
    "diagnostics": "aggregated errors and warnings",
}
DEFAULT_INSPECT_DIMENSIONS: tuple[str, ...] = (
    "skill",
    "tasks",
    "principles",
    "diagnostics",
)


def describe_inspect_dimensions() -> str:
    width = max(len(name) for name in INSPECT_DIMENSIONS)
    return "".join(
        f"  {name:<{width}}  {text}\n" for name, text in INSPECT_DIMENSIONS.items()
    )


def select_inspect_dimensions(dimensions: list[str] | None) -> tuple[str, ...]:
    if not dimensions:
        return DEFAULT_INSPECT_DIMENSIONS
    requested = [*dimensions, "skill"]
    unknown = sorted({name for name in requested if name not in INSPECT_DIMENSIONS})
    if unknown:
        raise DegardisError(
            f"unknown dimensions: {', '.join(unknown)}; the dimensions are "
            f"{', '.join(INSPECT_DIMENSIONS)}"
        )
    return tuple(name for name in INSPECT_DIMENSIONS if name in set(requested))


# --------------------------------------------------------------------------
# Loading one skill's selected source
# --------------------------------------------------------------------------


@dataclass
class SkillContent:
    """One skill's manifest and every source file it selects."""

    skill: Skill
    sources: SourceSet = field(default_factory=SourceSet)
    selected: dict[str, list[Path]] = field(default_factory=dict)
    icon_sources: dict[str, Path] = field(default_factory=dict)
    icon_assets: dict[str, bytes] = field(default_factory=dict)

    def files(self, key: str) -> list[Path]:
        return self.selected.get(key, [])


def load_content(skill: Skill, diagnostics: Diagnostics) -> SkillContent:
    """Select, read, and schema-check every source the manifest names."""
    content = SkillContent(skill=skill)
    diagnostics.add(yaml_scalar_warnings(skill.root / "skill.yaml"))
    config = check_manifest(skill, diagnostics)
    for key in CONTENT_KEYS:
        content.selected[key] = content_files(skill, config, key, diagnostics)
    for key in PARSED_CONTENT_KEYS:
        _read_constructs(content, key, diagnostics)
    _check_profile_identity(content, diagnostics)
    content.icon_sources, content.icon_assets = _load_icons(skill, diagnostics)
    return content


def _read_constructs(
    content: SkillContent, key: str, diagnostics: Diagnostics
) -> None:
    """Read every file one content key selects, under that key's own schema.

    The key decides the construct schema. Knowledge is the one parsed namespace
    whose files declare a finer-grained `kind` themselves; that kind controls
    rendering, not identity or file lookup. A tree laid out differently still
    compiles because the manifest, not the directory name, selects the files.
    """
    label = CONSTRUCT_LABELS[key]
    store = content.sources.kind(key)
    origins: dict[str, Path] = {}
    for path in content.files(key):
        if path.suffix.casefold() not in MARKDOWN_SUFFIXES:
            diagnostics.error(
                f"{path}: a {label} source is a Markdown file, whose frontmatter "
                "states its fields and whose body is its content",
                "source.unsupported",
                path,
            )
            continue
        try:
            source = read_markdown(path)
        except DegardisError as exc:
            diagnostics.source_failure(exc, path, "source.invalid-yaml")
            continue
        diagnostics.add(yaml_scalar_warnings(path, source.frontmatter, 1))
        construct = read_construct(source, key, diagnostics)
        if construct is None:
            continue
        identifier = construct_key(construct, key)
        previous = origins.get(identifier)
        if previous is not None:
            diagnostics.error(
                f"{path}: {label} id {construct.id} is already taken by "
                f"{previous}; a file stem is a construct's identity, so two "
                "files cannot share one",
                "source.duplicate-id",
                path,
            )
            continue
        origins[identifier] = path
        store[identifier] = construct


def _check_profile_identity(
    content: SkillContent, diagnostics: Diagnostics
) -> None:
    """Keep every profile distinguishable, in the index and in the bundle.

    Two checks, because they protect two different readers. A repeated title
    leaves the index with two rows a selecting agent cannot tell apart. A profile
    named for the index itself would be written over the index, so the reader
    that was meant to choose between profiles would find one of them instead.
    """
    seen: dict[str, Path] = {}
    for profile in content.sources.profiles.values():
        if profile.id in RESERVED_PROFILE_IDS:
            diagnostics.error(
                f"{profile.path}: a profile cannot be named {profile.id!r}; "
                f"{PROFILE_INDEX} is the generated index that lists the "
                "profiles, and this file would be written over it",
                "profile.reserved-id",
                profile.path,
            )
            continue
        previous = seen.get(profile.title.casefold())
        if previous is not None:
            diagnostics.error(
                f"{profile.path}: profile title {profile.title!r} is already "
                f"used by {previous}, so the index would carry two rows a reader "
                "cannot tell apart",
                "profile.duplicate-title",
                profile.path,
            )
            continue
        seen[profile.title.casefold()] = profile.path


def _load_icons(
    skill: Skill, diagnostics: Diagnostics
) -> tuple[dict[str, Path], dict[str, bytes]]:
    """Resolve the declared icon and rasterize it, keeping what it rendered.

    Rendering is how an icon source is checked at all — an unusable image is
    found by converting it — so these bytes exist here whether or not anything
    asks for them. Keeping them is what lets the outputs report state the size
    a build will write, for a file that is not yet on disk anywhere.
    """
    try:
        sources = resolve_icon_sources(skill)
        assets = render_icon_assets(sources)
    except IconError as exc:
        diagnostics.error(exc, exc.code, skill.root / "skill.yaml")
        return {}, {}
    return sources, assets


# --------------------------------------------------------------------------
# Relation checks
# --------------------------------------------------------------------------


def _check_principles(skill: Skill, content: SkillContent, diagnostics: Diagnostics) -> None:
    """Resolve every level's principle references against this skill alone.

    `principles/<id>.md` in this source is the only place a reference resolves.
    There is no fallback — not to the compiler, not to another installed skill,
    not to a cache or the network — because a skill whose guidance came from
    somewhere else is a skill whose text its author never saw and cannot change.

    A misspelled name is otherwise silent: the placement would simply not find
    it, the guidance would not appear, and nothing on the generated page would
    say that anything was asked for. So the message names the file that would
    have answered, and lists what this skill does state.
    """
    sources = content.sources
    known = sorted(sources.principles)
    available = (
        f"This skill states: {', '.join(known)}."
        if known
        else "This skill states no principle."
    )
    used = set(skill.principles)
    for task in sources.tasks.values():
        used.update(task.principles)
    for name in skill.principles:
        if name in sources.principles:
            continue
        diagnostics.error(
            f"{skill.root / 'skill.yaml'}: principles names {name!r}, and this "
            f"skill has no principles/{name}.md. {available} A principle is "
            "authored in the skill that uses it, so nothing outside this source "
            "can supply one",
            "manifest.unknown-principle",
            skill.root / "skill.yaml",
        )
    for task in sources.tasks.values():
        for name in task.principles:
            if name in sources.principles:
                continue
            diagnostics.error(
                f"{task.path}: principles names {name!r}, and this skill has no "
                f"principles/{name}.md. {available} A principle is "
                "authored in the skill that uses it, so nothing outside this source "
                "can supply one",
                "task.unknown-principle",
                task.path,
            )
    for name in known:
        if name in used:
            task_paths = [
                task.path for task in sources.tasks.values() if name in task.principles
            ]
            if (
                task_paths
                and name not in skill.principles
                and len(task_paths) == len(sources.tasks)
            ):
                diagnostics.warning(
                    f"{skill.root / 'skill.yaml'}: every task names the principle "
                    f"{name!r}; name it at skill level instead, so it is read before "
                    "task routing",
                    "principle.all-tasks",
                    skill.root / "skill.yaml",
                )
            if task_paths and name in skill.principles:
                diagnostics.warning(
                    f"{skill.root / 'skill.yaml'}: skill-level principles and "
                    f"{', '.join(str(path) for path in task_paths)} both name {name!r}; "
                    "remove the principle from either skill level or task level",
                    "principle.duplicate-placement",
                    skill.root / "skill.yaml",
                )
            continue
        item = sources.principles[name]
        diagnostics.warning(
            f"{item.path}: no skill or task principles field names {name}, so the "
            "bundle carries none of it; name it from a level that needs it, or "
            "delete the file",
            "principle.unused",
            item.path,
        )


def _check_routed_tasks(
    skill: Skill, content: SkillContent, diagnostics: Diagnostics
) -> None:
    """Hold the manifest's routing order to the tasks the source actually has.

    The order is the one thing about routing no task file can state, so the
    manifest states it. That makes the list a second register of names beside
    the directory, and a register that can disagree in silence is worse than no
    register: a name with no file would route the agent to a page that is not
    there, and a file with no name would ship a task nothing can reach. Both
    directions are therefore errors, and between them the manifest and the
    directory are the same set or the build stops.
    """
    known = sorted(content.sources.tasks)
    available = (
        f"This skill states: {', '.join(known)}."
        if known
        else "This skill states no task."
    )
    declared = dict.fromkeys(skill.tasks)
    for name in declared:
        if name in content.sources.tasks:
            continue
        diagnostics.error(
            f"{skill.root / 'skill.yaml'}: tasks names {name!r}, and this skill "
            f"has no tasks/{name}.md. {available} A task is the page its route "
            "opens, so a name with no file routes the agent nowhere",
            "manifest.unknown-task",
            skill.root / "skill.yaml",
        )
    for name in known:
        if name in declared:
            continue
        item = content.sources.tasks[name]
        diagnostics.error(
            f"{item.path}: the manifest's tasks field does not name {name}, so "
            "nothing routes to it; add it where it belongs in the routing order, "
            "or delete the file",
            "manifest.unrouted-task",
            item.path,
        )


def _check_plan(
    content: SkillContent, plan: Plan, diagnostics: Diagnostics
) -> None:
    """Report what the closure could not resolve, against whoever wrote it."""
    sources = content.sources
    for origin, missing in plan.unresolved:
        kind, _, identifier = origin.partition(":")
        if kind == "task":
            task = sources.tasks[identifier]
            diagnostics.error(
                f"{task.path}: task {task.id} names the knowledge {missing}, "
                "which the manifest selects no file for",
                "task.unknown-knowledge",
                task.path,
            )
            continue
        unit = sources.knowledge[origin]
        diagnostics.error(
            f"{unit.path}: {unit.kind} {unit.id} requires {missing}, which the "
            "manifest selects no file for",
            "knowledge.unknown-requires",
            unit.path,
        )
    for cycle in plan.cycles:
        unit = sources.knowledge[cycle[0]]
        diagnostics.error(
            f"{unit.path}: these units require each other in a cycle: "
            f"{' -> '.join(cycle)}. A dependency closure cannot resolve a "
            "cycle; break it",
            "knowledge.requirement-cycle",
            unit.path,
        )
    reached = {unit.key for item in plan.tasks for unit in item.closure}
    for key, unit in sorted(sources.knowledge.items()):
        if key in reached:
            continue
        diagnostics.warning(
            f"{unit.path}: no task reaches {key}, so the bundle carries none of "
            "it; name it from a task, or from something a task reaches",
            "knowledge.orphan",
            unit.path,
        )
    for item in plan.tasks:
        if item.carries_material:
            continue
        diagnostics.warning(
            f"{item.task.path}: task {item.id} compiles to a page carrying "
            "only its goal; give it knowledge, a body, or a guide",
            "task.empty",
            item.task.path,
        )


def _check_guides(
    content: SkillContent, plan: Plan, diagnostics: Diagnostics
) -> None:
    """Every task guide reference must resolve, and every guide must be reached.

    Both directions matter: a task must not route a reader to nothing, and a
    selected guide that no task or authored page reaches is weight no reader can
    use.
    """
    guides = content.sources.guides
    consumed: set[str] = set()
    for item in plan.tasks:
        for identifier in item.task.guides:
            guide = guides.get(identifier)
            if guide is not None:
                consumed.add(guide.path.relative_to(content.skill.root).as_posix())
                continue
            diagnostics.error(
                f"{item.task.path}: task {item.id} names the guide {identifier!r}, "
                "which the manifest selects no file for",
                "task.unknown-guide",
                item.task.path,
            )
    linked = consumed | _body_links(content)
    for key in ("guides", *COPIED_CONTENT_KEYS):
        selected_for_key = {
            path.relative_to(content.skill.root).as_posix()
            for path in content.files(key)
        }
        for relative in sorted(selected_for_key - linked):
            path = content.skill.root / relative
            diagnostics.warning(
                f"{path}: content.{key} ships {relative}, and no task guide "
                "or authored link names it",
                "content.unconsumed",
                path,
            )


def _body_links(content: SkillContent) -> set[str]:
    """Every bundle path an authored body links to, wherever that body came from."""
    from .markdown import inline_reference_targets, link_targets

    root = content.skill.root
    found: set[str] = set()
    sources = content.sources
    bodies = [
        *((task.body, task.path) for task in sources.tasks.values()),
        *((item.body, item.path) for item in sources.principles.values()),
        *((unit.body, unit.path) for unit in sources.knowledge.values()),
        *((item.body, item.path) for item in sources.profiles.values()),
        *((item.body, item.path) for item in sources.guides.values()),
    ]
    for body, path in bodies:
        found.update(link_targets(body, path, root))
        copied_kinds = {
            "asset": "assets",
            "script": "scripts",
        }
        found.update(
            f"{copied_kinds[kind]}/{target}"
            for kind, target in inline_reference_targets(body)
            if kind in copied_kinds
        )
        found.update(
            guide.path.relative_to(root).as_posix()
            for kind, target in inline_reference_targets(body)
            if kind == "guide" and (guide := sources.guides.get(target)) is not None
        )
    return found


# --------------------------------------------------------------------------
# Compiling one skill
# --------------------------------------------------------------------------


@dataclass
class Compiled:
    content: SkillContent
    plan: Plan = field(default_factory=Plan)
    quality: Quality = field(default_factory=Quality)
    rendered: RenderedBundle | None = None


def compile_skill(
    skill: Skill, diagnostics: Diagnostics, progress: Progress | None = None
) -> Compiled:
    """Read, check, place, and render one skill, collecting every problem found."""
    watcher = progress or Progress()
    watcher.phase(f"Reading {skill.name}")
    content = load_content(skill, diagnostics)
    result = Compiled(content=content)
    watcher.phase(f"Checking {skill.name}")
    _check_principles(skill, content, diagnostics)
    _check_routed_tasks(skill, content, diagnostics)
    result.plan = plan_skill(content.sources, skill.principles, skill.tasks)
    _check_plan(content, result.plan, diagnostics)
    _check_guides(content, result.plan, diagnostics)
    result.quality = measure(result.plan, content.sources)
    result.rendered = render_skill(
        skill,
        content.sources,
        result.plan,
        diagnostics,
        progress=watcher,
        copied=content.selected,
    )
    _check_outputs(result, diagnostics)
    return result


def _check_outputs(result: Compiled, diagnostics: Diagnostics) -> None:
    """Check what a build would write: collisions, and every link it emitted."""
    if result.rendered is None:
        return
    content = result.content
    root = content.skill.root
    written: dict[str, Path] = {}
    for key in COPIED_CONTENT_KEYS:
        for path in content.files(key):
            relative = copied_path(key, path.relative_to(root).as_posix())
            previous = written.get(relative)
            if previous is not None:
                diagnostics.error(
                    f"{path}: two selected files would be written to {relative}",
                    "output.path-collision",
                    path,
                )
            written[relative] = path
    generated = result.rendered.pages
    for relative in generated:
        if relative not in written:
            continue
        diagnostics.error(
            f"{written[relative]}: a generated page is written to {relative}, "
            "and a selected file already occupies it; rename one of them",
            "output.path-collision",
            written[relative],
        )
    shipped = set(written) | set(generated) | {ROOT}
    manifest = root / "skill.yaml"
    for link in result.rendered.links:
        if link.target in shipped:
            continue
        diagnostics.error(
            f"{manifest}: {link.page} links {link.target}, which is not a file "
            "this bundle ships",
            "output.broken-reference",
            manifest,
        )


# --------------------------------------------------------------------------
# The inspection result
# --------------------------------------------------------------------------


@dataclass
class Inspection:
    """One skill as this run read it: its identity, its compilation, its findings."""

    root: Path
    diagnostics: Diagnostics
    skill: Skill | None = None
    compiled: Compiled | None = None


def compile_all(
    skill_paths: Iterable[Path], progress: Progress | None = None
) -> list[Inspection]:
    """Compile every selected skill once, so no caller compiles one twice.

    `validate`, the `inspect` report, and `build` all need the same compilation.
    Reading it once is not only cheaper: it is what makes the three agree, since
    a second pass could observe a source edited between them.

    `progress` only names the phase now running. It cannot reach a diagnostic,
    a result, or an exit status, so a run that displays one and a run that
    displays nothing compile the same sources to the same bundle.
    """
    inspections: list[Inspection] = []
    roots = list(skill_paths)
    watcher = progress or Progress()
    for position, root in enumerate(roots, start=1):
        scope = Scope(watcher, f" ({position}/{len(roots)})" if len(roots) > 1 else "")
        # Named for the directory, because the manifest that carries the skill's
        # own name is what the next line is about to read. Every phase below
        # names the skill itself.
        scope.phase(f"Reading {root.name}")
        diagnostics = Diagnostics()
        try:
            skill = load_skill_path(root)
        except DegardisError as exc:
            diagnostics.source_failure(exc, root / "skill.yaml", "manifest.unreadable")
            inspections.append(Inspection(root=root, diagnostics=diagnostics))
            continue
        compiled = compile_skill(skill, diagnostics, scope)
        inspections.append(
            Inspection(
                root=root, diagnostics=diagnostics, skill=skill, compiled=compiled
            )
        )
    return inspections


def inspect_skills(
    skill_paths: Iterable[Path],
    *,
    body_pages: Sequence[str] = (),
    progress: Progress | None = None,
) -> list[dict[str, Any]]:
    return [
        result_dict(inspection, body_pages=body_pages)
        for inspection in compile_all(skill_paths, progress)
    ]


def result_dict(
    inspection: Inspection, *, body_pages: Sequence[str] = ()
) -> dict[str, Any]:
    if inspection.skill is None or inspection.compiled is None:
        return _unreadable_result(inspection.root, inspection.diagnostics)
    return _result_dict(
        inspection.skill,
        inspection.compiled,
        inspection.diagnostics,
        body_pages=body_pages,
    )


def _empty_attention() -> dict[str, Any]:
    return {
        "root_bytes": 0,
        "root_lines": 0,
        "task_pages": 0,
        "task_bytes": 0,
        "largest_task_bytes": 0,
        "average_task_bytes": 0,
        "principle_bytes": 0,
        "largest_principle_bytes": 0,
        "profile_bytes": 0,
        "guide_bytes": 0,
        "largest_guide_bytes": 0,
        "root_budget": ROOT_BUDGET_BYTES,
        "task_budget": TASK_BUDGET_BYTES,
        "principle_budget": PRINCIPLE_BUDGET_BYTES,
        "guide_budget": GUIDE_BUDGET_BYTES,
    }


def _unreadable_result(root: Path, diagnostics: Diagnostics) -> dict[str, Any]:
    return {
        "name": root.name,
        "title": root.name,
        "version": "",
        "description": "",
        "purpose": "",
        "license": None,
        "copyright": None,
        "source": root,
        "format_version": None,
        "source_fingerprint": source_fingerprint(root, {}),
        "counts": dict.fromkeys(CONTENT_KEYS, 0),
        "sources": [],
        "tasks": [],
        "knowledge": [],
        "principles": {
            "selected": [],
            "states": [],
        },
        "profiles": [],
        "composition": [],
        "quality": _quality_rows(Quality(), _empty_attention(), []),
        "attention": _empty_attention(),
        "outputs": [],
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "pages": [],
        "page_text": {},
    }


def _result_dict(
    skill: Skill,
    compiled: Compiled,
    diagnostics: Diagnostics,
    *,
    body_pages: Sequence[str],
) -> dict[str, Any]:
    content = compiled.content
    rendered = compiled.rendered
    generated = rendered.page_texts() if rendered is not None else {}
    text = rendered.skill_text if rendered is not None else ""
    tasks = _task_rows(compiled)
    attention = _attention(compiled, text)
    return {
        "name": skill.name,
        "title": skill.title,
        "version": skill.version,
        "description": skill.description,
        "purpose": skill.purpose,
        "license": skill.manifest.get("license"),
        "copyright": skill.manifest.get("copyright"),
        "source": skill.root,
        "format_version": skill.manifest.get("format_version"),
        "source_fingerprint": source_fingerprint(skill.root, content.selected),
        "counts": {key: len(content.files(key)) for key in CONTENT_KEYS},
        "sources": _source_rows(content),
        "tasks": tasks,
        "knowledge": _knowledge_rows(compiled),
        "principles": _principle_rows(compiled),
        "profiles": _profile_rows(content),
        "guides": _guide_rows(compiled),
        "composition": _composition_rows(compiled),
        "quality": _quality_rows(compiled.quality, attention, tasks),
        "attention": attention,
        "outputs": _output_rows(compiled),
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "pages": list(generated),
        "page_text": {
            page: generated[page] for page in body_pages if page in generated
        },
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _source_rows(content: SkillContent) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = content.skill.root
    for key in CONTENT_KEYS:
        store = content.sources.kind(key) if key in PARSED_CONTENT_KEYS else {}
        by_path = {construct.path: construct for construct in store.values()}
        for path in content.files(key):
            construct = by_path.get(path)
            rows.append(
                {
                    "kind": (
                        construct.kind
                        if key == "knowledge" and construct is not None
                        else key
                    ),
                    "id": construct.id if construct is not None else "",
                    "path": path.relative_to(root).as_posix(),
                    "bytes": _size(path),
                }
            )
    return rows


def _task_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    return [
        {
            "id": item.id,
            "title": item.task.title,
            "goal": item.task.goal,
            "recognize": list(item.task.recognize),
            "page": item.page,
            "bytes": rendered.page_bytes(item.page) if rendered else 0,
            "knowledge": len(item.closure),
            "guides": list(item.task.guides),
            "principles": [
                {"id": principle.id, "activation": principle.activation}
                for principle in item.principles
            ],
        }
        for item in compiled.plan.tasks
    ]


def _knowledge_rows(compiled: Compiled) -> list[dict[str, Any]]:
    carriers: dict[str, list[str]] = {}
    for item in compiled.plan.tasks:
        for unit in item.closure:
            carriers.setdefault(unit.key, []).append(item.id)
    return [
        {
            "key": key,
            "kind": unit.kind,
            "id": unit.id,
            "title": unit.title,
            "requires": list(unit.requires),
            "tasks": carriers.get(key, []),
            "bytes": len(unit.body.encode("utf-8")),
        }
        for key, unit in sorted(compiled.content.sources.knowledge.items())
    ]


def _principle_rows(compiled: Compiled) -> dict[str, Any]:
    """Every principle this skill states, with its provenance and its placement.

    The source path is part of the row because a principle is now authored here
    rather than supplied, so the first question about one is which file in this
    skill says it.
    """
    sources = compiled.content.sources
    root = compiled.content.skill.root
    selected = {item.id for item in compiled.plan.principles}
    placements: dict[str, list[dict[str, str]]] = {}
    for reference in compiled.plan.root_principles:
        placements.setdefault(reference.id, []).append(
            {"owner": ROOT, "activation": reference.activation}
        )
    for task in compiled.plan.tasks:
        for reference in task.principles:
            placements.setdefault(reference.id, []).append(
                {"owner": f"task:{task.id}", "activation": reference.activation}
            )
    return {
        "selected": [item.id for item in compiled.plan.principles],
        "states": [
            {
                "id": name,
                "title": item.title,
                "path": item.path.relative_to(root).as_posix(),
                "selected": name in selected,
                "activation": item.activation,
                "placements": placements.get(name, []),
                "page": principle_path(name) if name in selected else "-",
                "bytes": len(item.body.encode("utf-8")),
            }
            for name, item in sorted(sources.principles.items())
        ],
    }


def _profile_rows(content: SkillContent) -> list[dict[str, Any]]:
    return [
        {
            "id": identifier,
            "title": profile.title,
            "category": profile.category,
            "description": profile.description,
            "bytes": len(profile.body.encode("utf-8")),
        }
        for identifier, profile in sorted(content.sources.profiles.items())
    ]


def _guide_rows(compiled: Compiled) -> list[dict[str, Any]]:
    """Describe every guide, its activation, and the tasks that name it."""
    root = compiled.content.skill.root
    owners: dict[str, list[dict[str, str]]] = {
        identifier: [] for identifier in compiled.content.sources.guides
    }
    for item in compiled.plan.tasks:
        for identifier in item.task.guides:
            if identifier in owners:
                owners[identifier].append({"task": item.id})
    return [
        {
            "id": identifier,
            "title": guide.title,
            "activation": guide.activation,
            "path": guide.path.relative_to(root).as_posix(),
            "tasks": owners[identifier],
            "bytes": len(guide.body.encode("utf-8")),
        }
        for identifier, guide in sorted(compiled.content.sources.guides.items())
    ]


def _composition_rows(compiled: Compiled) -> list[dict[str, Any]]:
    """Why each page carries what it carries, for the author asking exactly that."""
    return [
        {
            "id": item.id,
            "direct": list(item.direct),
            "required": list(item.required),
            "groups": [
                {"kind": kind, "knowledge": [unit.id for unit in item.of_kind(kind)]}
                for kind in KNOWLEDGE_KINDS
                if item.of_kind(kind)
            ],
            "page": item.page,
        }
        for item in compiled.plan.tasks
    ]


def _quality_rows(
    quality: Quality, attention: dict[str, Any], tasks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Add per-load costs to quality without treating the root as optional.

    A run always loads SKILL.md, then it deliberately opens exactly one task
    page. Startup bytes and each task's minimum read therefore come from the
    rendered files rather than source-file sizes. Headroom is the tightest
    remaining margin among those two independently enforced page budgets.
    """
    startup_bytes = attention["root_bytes"]
    headroom = min(
        [
            attention["root_budget"] - startup_bytes,
            *(attention["task_budget"] - task["bytes"] for task in tasks),
        ]
    )
    return {
        "tasks": quality.tasks,
        "knowledge_units": quality.knowledge_units,
        "orphan_knowledge": list(quality.orphan_knowledge),
        "near_duplicates": [
            {"left": left, "right": right, "similarity": similarity}
            for left, right, similarity in quality.near_duplicates
        ],
        "constraint_ratio": quality.constraint_ratio,
        "principles": quality.principles,
        "duplicated_bytes": quality.duplicated_bytes,
        "unique_bytes": quality.unique_bytes,
        "headroom": headroom,
        "startup_bytes": startup_bytes,
        "minimum_read_bytes_by_task": {
            task["id"]: startup_bytes + task["bytes"] for task in tasks
        },
    }


def _attention(compiled: Compiled, text: str) -> dict[str, Any]:
    rendered = compiled.rendered
    pages = rendered.pages if rendered is not None else {}
    task_pages = [item.page for item in compiled.plan.tasks]
    task_sizes = [len(pages.get(page, "").encode("utf-8")) for page in task_pages]
    principle_pages = [principle_path(item.id) for item in compiled.plan.principles]
    profile_pages = [
        PROFILE_INDEX,
        *(profile_path(item.id) for item in compiled.plan.profiles),
    ]
    principle_sizes = [
        len(pages.get(page, "").encode("utf-8")) for page in principle_pages
    ]
    guide_sizes = []
    for guide in compiled.content.sources.guides.values():
        page = guide_path(guide.id)
        guide_sizes.append(len(pages.get(page, "").encode("utf-8")))
    profile_bytes = sum(
        len(pages.get(page, "").encode("utf-8")) for page in profile_pages
    )
    return {
        "root_bytes": len(text.encode("utf-8")),
        "root_lines": len(text.splitlines()),
        "task_pages": len(task_sizes),
        "task_bytes": sum(task_sizes),
        "largest_task_bytes": max(task_sizes, default=0),
        "average_task_bytes": (
            round(sum(task_sizes) / len(task_sizes)) if task_sizes else 0
        ),
        "principle_bytes": sum(principle_sizes),
        "largest_principle_bytes": max(principle_sizes, default=0),
        "profile_bytes": profile_bytes,
        "guide_bytes": sum(guide_sizes),
        "largest_guide_bytes": max(guide_sizes, default=0),
        "root_budget": ROOT_BUDGET_BYTES,
        "task_budget": TASK_BUDGET_BYTES,
        "principle_budget": PRINCIPLE_BUDGET_BYTES,
        "guide_budget": GUIDE_BUDGET_BYTES,
    }


def _output_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    if rendered is None:
        return []
    content = compiled.content
    root = content.skill.root
    rows: list[dict[str, Any]] = [
        {
            "path": ROOT,
            "bytes": len(rendered.skill_text.encode("utf-8")),
            "mode": artifact_mode(ROOT),
        }
    ]
    for relative, page in sorted(rendered.pages.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(page.encode("utf-8")),
                "mode": artifact_mode(relative),
            }
        )
    for key in COPIED_CONTENT_KEYS:
        for path in content.files(key):
            relative = copied_path(key, path.relative_to(root).as_posix())
            rows.append(
                {
                    "path": relative,
                    "bytes": _size(path),
                    "mode": artifact_mode(relative),
                }
            )
    for relative, data in sorted(content.icon_assets.items()):
        rows.append(
            {"path": relative, "bytes": len(data), "mode": artifact_mode(relative)}
        )
    metadata = openai_metadata(
        content.skill.interface, set(content.icon_sources), content.skill.name
    )
    rows.append(
        {
            "path": OPENAI_METADATA,
            "bytes": len(metadata.encode("utf-8")),
            "mode": artifact_mode(OPENAI_METADATA),
        }
    )
    return sorted(rows, key=lambda row: row["path"])


def promote_warnings(results: list[dict[str, Any]]) -> None:
    """Report every warning as an error, without changing which checks ran."""
    for result in results:
        records: list[Diagnostic] = []
        for record in result["diagnostics"]:
            records.append(
                Diagnostic(
                    severity="error",
                    message=record.message,
                    code=record.code,
                    path=record.path,
                    line=record.line,
                )
                if record.severity == "warning"
                else record
            )
        result["diagnostics"] = records
        result["errors"] = [
            record.message for record in records if record.severity == "error"
        ]
        result["warnings"] = []


def validate(paths: Path | list[Path]) -> list[str]:
    """Every error one or more skills report, for an embedded caller."""
    sources = [paths] if isinstance(paths, Path) else list(paths)
    results = inspect_skills(discover_skill_paths(sources))
    return [message for result in results for message in result["errors"]]
