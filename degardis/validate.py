"""Every check the compiler runs, over the one compilation each report reads.

Anything that checks a source belongs here rather than on one output path, so
`validate`, the `inspect` line report, and `build` cannot disagree about what a
source contains or about which findings it has. What those three read that
compilation as is `inspection.py`'s.

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

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import Plan, Quality, measure, plan_skill
from .bundlepaths import (
    FACET_INDEX,
    RESERVED_FACET_IDS,
    ROOT,
    copied_path,
)
from .content import (
    CONTENT_KEYS,
    COPIED_CONTENT_KEYS,
    COPIED_CONTENT_KINDS,
    PARSED_CONTENT_KEYS,
    content_files,
)
from .icons import IconError, render_icon_assets, resolve_icon_sources
from .markdown import (
    MARKDOWN_SUFFIXES,
    inline_reference_targets,
    link_targets,
    read_markdown,
)
from .model import DegardisError, Diagnostics, Skill
from .progress import Progress, Scope
from .registry import check_manifest, load_skill_path
from .render import (
    RenderedBundle,
    render_skill,
)
from .sources import (
    CONSTRUCT_LABELS,
    SourceSet,
    construct_key,
    read_construct,
)
from .yamlsource import yaml_scalar_warnings


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
    _check_facet_identity(content, diagnostics)
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


def _check_facet_identity(
    content: SkillContent, diagnostics: Diagnostics
) -> None:
    """Keep every facet distinguishable, in the index and in the bundle.

    Two checks, because they protect two different readers. A repeated title
    leaves the index with two rows a selecting agent cannot tell apart. A facet
    named for the index itself would be written over the index, so the reader
    that was meant to choose between facets would find one of them instead.
    """
    seen: dict[str, Path] = {}
    for facet in content.sources.facets.values():
        if facet.id in RESERVED_FACET_IDS:
            diagnostics.error(
                f"{facet.path}: a facet cannot be named {facet.id!r}; "
                f"{FACET_INDEX} is the generated index that lists the "
                "facets, and this file would be written over it",
                "facet.reserved-id",
                facet.path,
            )
            continue
        previous = seen.get(facet.title.casefold())
        if previous is not None:
            diagnostics.error(
                f"{facet.path}: facet title {facet.title!r} is already "
                f"used by {previous}, so the index would carry two rows a reader "
                "cannot tell apart",
                "facet.duplicate-title",
                facet.path,
            )
            continue
        seen[facet.title.casefold()] = facet.path


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


def _unknown_principle(name: str, known: Sequence[str]) -> str:
    """Say what a principle reference asked for, and what this skill states.

    Both levels that can name a principle report the same thing, so they say it
    in the same words; only the file the finding is reported against differs.
    """
    available = (
        f"This skill states: {', '.join(known)}."
        if known
        else "This skill states no principle."
    )
    return (
        f"principles names {name!r}, and this skill has no principles/{name}.md. "
        f"{available} A principle is authored in the skill that uses it, so "
        "nothing outside this source can supply one"
    )


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
    manifest = skill.root / "skill.yaml"
    used = set(skill.principles)
    for task in sources.tasks.values():
        used.update(task.principles)
    for name in skill.principles:
        if name not in sources.principles:
            diagnostics.error(
                f"{manifest}: {_unknown_principle(name, known)}",
                "manifest.unknown-principle",
                manifest,
            )
    for task in sources.tasks.values():
        for name in task.principles:
            if name not in sources.principles:
                diagnostics.error(
                    f"{task.path}: {_unknown_principle(name, known)}",
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
                    f"{manifest}: every task names the principle {name!r}; name "
                    "it at skill level instead, so it is read before task routing",
                    "principle.all-tasks",
                    manifest,
                )
            if task_paths and name in skill.principles:
                diagnostics.warning(
                    f"{manifest}: skill-level principles and "
                    f"{', '.join(str(path) for path in task_paths)} both name {name!r}; "
                    "remove the principle from either skill level or task level",
                    "principle.duplicate-placement",
                    manifest,
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
    """Every guide reference must resolve, and every guide must be reached.

    Both directions matter: neither a task nor a facet may route a reader to
    nothing, and a selected guide that nothing in the source reaches is weight no
    reader can use.

    The two owners report under their own codes because they are two repairs in
    two files: a task's routing is the work it was asked for, a facet's is the
    situation it recognized, and an author holding one is not looking at the
    other.
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
    for facet in plan.facets:
        for identifier in facet.guides:
            guide = guides.get(identifier)
            if guide is not None:
                consumed.add(guide.path.relative_to(content.skill.root).as_posix())
                continue
            diagnostics.error(
                f"{facet.path}: facet {facet.id} names the guide {identifier!r}, "
                "which the manifest selects no file for",
                "facet.unknown-guide",
                facet.path,
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
                f"{path}: content.{key} ships {relative}, and no task, facet, "
                "or authored link names it",
                "content.unconsumed",
                path,
            )


def _body_links(content: SkillContent) -> set[str]:
    """Every bundle path an authored body links to, wherever that body came from."""
    root = content.skill.root
    sources = content.sources
    copied_keys = {kind: key for key, kind in COPIED_CONTENT_KINDS.items()}
    found: set[str] = set()
    for body, path in _authored_bodies(sources):
        found.update(link_targets(body, path, root))
        for kind, target in inline_reference_targets(body):
            if kind in copied_keys:
                found.add(f"{copied_keys[kind]}/{target}")
            elif kind == "guide" and (guide := sources.guides.get(target)) is not None:
                found.add(guide.path.relative_to(root).as_posix())
    return found


def _authored_bodies(sources: SourceSet) -> Iterator[tuple[str, Path]]:
    """Every body an author wrote, with the file it was written in."""
    for store in (
        sources.tasks,
        sources.principles,
        sources.knowledge,
        sources.facets,
        sources.guides,
    ):
        for item in store.values():
            yield item.body, item.path


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
# Compiling every selected skill
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
