"""Every check the compiler runs, over the one compilation each report reads.

Anything that checks a source belongs here rather than on one output path, so
`validate`, the `inspect` line report, and `build` cannot disagree about what a
source contains or about which findings it has. What those three read that
compilation as is `inspection.py`'s.

The checks fall into three groups. Reading and schema checks are delegated to the
modules that own them — the loader, the manifest reader, and the construct
readers. Relation checks live here: whether every principle the skill selects
exists, whether every knowledge and guide reference resolves, whether a
requirement chain closes, whether every hand-off names a task, and whether every
file a generated page links to is a file the bundle ships. Placement is
delegated to the planner and page size to the renderer, each of which is the
only part that knows what it decided.

What none of them check is whether the skill is any good. A pass means the source
compiles to a complete, self-consistent bundle whose links resolve. Whether the
knowledge on a task page is the knowledge that task needs is a judgment about
expertise, and it is established by using the skill, not by compiling it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import Plan, Quality, measure, orphans, plan_skill
from .bundlepaths import (
    Addresses,
    OPENAI_METADATA,
    ROOT,
    copied_path,
    facet_path,
    guide_path,
    principle_path,
    resolve_addresses,
    task_path,
)
from .content import (
    CONTENT_KEYS,
    COPIED_CONTENT_KEYS,
    COPIED_CONTENT_KINDS,
    PARSED_CONTENT_KEYS,
    content_files,
    resolve_copied,
)
from .icons import ICON_ROLES, IconError, read_icon, resolve_icon_source
from .markdown import (
    MARKDOWN_SUFFIXES,
    inline_reference_targets,
    internal_links,
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
    icon_source: Path | None = None
    icon_address: str | None = None
    icon_assets: dict[str, bytes] = field(default_factory=dict)
    addresses: Addresses = field(
        default_factory=lambda: resolve_addresses(frozenset())
    )

    def files(self, key: str) -> list[Path]:
        return self.selected.get(key, [])

    @property
    def icon_addresses(self) -> dict[str, str]:
        """Where the icon lands, under each role the host metadata names.

        One file serves both roles, so both name the same address, and neither
        is named where the icon was refused and nothing will ship.
        """
        if self.icon_address is None:
            return {}
        return dict.fromkeys(ICON_ROLES, self.icon_address)


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
    _load_icon(content, diagnostics)
    content.addresses = resolve_addresses(_claimed_addresses(content))
    return content


def _copied_addresses(content: SkillContent) -> set[str]:
    """The bundle address of every selected script and asset."""
    root = content.skill.root
    return {
        copied_path(key, path.relative_to(root).as_posix())
        for key in COPIED_CONTENT_KEYS
        for path in content.files(key)
    }


def _claimed_addresses(content: SkillContent) -> set[str]:
    """Every bundle address the source itself claims.

    What the author wrote decides these: a file they ship keeps the address
    it is copied to, and a construct's page keeps the address its filename
    gives it, because a file stem is that construct's identity. Everything
    the compiler names is placed around them.
    """
    claimed = {ROOT, OPENAI_METADATA, *_copied_addresses(content)}
    if content.icon_address is not None:
        claimed.add(content.icon_address)
    sources = content.sources
    claimed |= {task_path(name) for name in sources.tasks}
    claimed |= {principle_path(name) for name in sources.principles}
    claimed |= {guide_path(name) for name in sources.guides}
    claimed |= {facet_path(name) for name in sources.facets}
    return claimed


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
        identifier = construct.id
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
    """Keep every facet tellable from every other, in the index that lists them.

    A repeated title leaves the index with two rows a selecting agent cannot
    tell apart, and the index exists to support exactly that choice. A facet
    named `index` is not a failure at all: `index` is this compiler's name for
    the index, not a name the author may not use, so the facet keeps the
    address its filename gives it and the index is written beside it.
    """
    seen: dict[str, Path] = {}
    for facet in content.sources.facets.values():
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


def _load_icon(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Read and check the declared icon, keeping what a build must still write.

    The icon keeps its source path, like any copied file. Reading it is how it
    is checked at all, so its bytes are read whether or not anything asks for
    them. They are kept only where no selected file already ships that path:
    that is what lets the outputs report state the size of a file not yet on
    disk anywhere, without listing one file twice where the author selected
    the icon as an asset as well.
    """
    skill = content.skill
    try:
        source = resolve_icon_source(skill)
        if source is None:
            return
        data = read_icon(source)
    except IconError as exc:
        diagnostics.error(exc, exc.code, skill.root / "skill.yaml")
        return
    address = copied_path(
        "icon", source.relative_to(skill.root.resolve()).as_posix()
    )
    content.icon_source = source
    content.icon_address = address
    if address not in _copied_addresses(content):
        content.icon_assets = {address: data}


# --------------------------------------------------------------------------
# Relation checks
# --------------------------------------------------------------------------


def _unknown_principle(name: str, known: Sequence[str]) -> str:
    """Say what a principle reference asked for, and what this skill states."""
    available = (
        f"This skill states: {', '.join(known)}."
        if known
        else "This skill states no principle."
    )
    return (
        f"principles names {name!r}, but no selected principle has that id. "
        f"{available} A principle is authored in the skill that uses it, so "
        "nothing outside this source can supply one"
    )


def _check_principles(
    skill: Skill, content: SkillContent, diagnostics: Diagnostics
) -> None:
    """Resolve the skill's principle references against this skill alone.

    A principle holds across every task, so the skill is its one owner, and
    `skill.yaml` is the one place that names it. A selected principle with that
    id in this source is the only place a reference resolves. There is no
    fallback — not to the compiler, not to another installed skill, not to a
    cache or the network — because a skill whose guidance came from somewhere
    else is a skill whose text its author never saw and cannot change.

    A misspelled name is otherwise silent: the placement would simply not find
    it, the guidance would not appear, and nothing on the generated page would
    say that anything was asked for. So the message names the file that would
    have answered, and lists what this skill does state.

    A list the manifest check refused names nothing here, so which principles
    it meant is unknown. The unused warning then stays quiet rather than
    calling a principle unused on the evidence of a list that may well name it.
    """
    sources = content.sources
    known = sorted(sources.principles)
    manifest = skill.root / "skill.yaml"
    ownership_known = "principles" not in skill.manifest or bool(skill.principles)
    for name in skill.principles:
        if name not in sources.principles:
            diagnostics.error(
                f"{manifest}: {_unknown_principle(name, known)}",
                "manifest.unknown-principle",
                manifest,
            )
    for name in known if ownership_known else ():
        if name in skill.principles:
            continue
        item = sources.principles[name]
        diagnostics.warning(
            f"{item.path}: skill.yaml principles does not name {name}, so the "
            "bundle carries none of it; a principle holds across every task, and "
            "the skill is its one owner",
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

    A usable list is never empty, so an empty one is a field the manifest's own
    check already refused as missing or invalid. Comparing against it would
    report every task as unrouted by a list that does name them, giving one
    mistake a finding per task file.
    """
    if not skill.tasks:
        return
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
            f"{skill.root / 'skill.yaml'}: tasks names {name!r}, but no selected "
            f"task has that id. {available} A task is the page its route opens, "
            "so a name with no selected source routes the agent nowhere",
            "manifest.unknown-task",
            skill.root / "skill.yaml",
        )
    for name in known:
        if name in declared:
            continue
        item = content.sources.tasks[name]
        diagnostics.error(
            f"{item.path}: the manifest's tasks field does not name {name}, so "
            "nothing routes to it; reconcile selection with routing",
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
    for key in orphans(plan, sources):
        unit = sources.knowledge[key]
        diagnostics.warning(
            f"{unit.path}: no task reaches {key}, so the bundle carries none of "
            "it; selected knowledge must belong to a task closure",
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


def _check_guide_requirements(
    content: SkillContent, plan: Plan, diagnostics: Diagnostics
) -> None:
    """Report every guide requirement no selected guide answers, and every cycle.

    Both are read from every selected guide, reached or not, because a
    requirement is a fact about the guide that declares it. Each finding is
    reported against the guide whose `requires` the author has to edit.
    """
    guides = content.sources.guides
    for origin, missing in plan.guide_unresolved:
        guide = guides[origin]
        diagnostics.error(
            f"{guide.path}: guide {guide.id} requires {missing}, which the "
            "manifest selects no file for",
            "guide.unknown-requires",
            guide.path,
        )
    for cycle in plan.guide_cycles:
        guide = guides[cycle[0]]
        diagnostics.error(
            f"{guide.path}: these guides require each other in a cycle: "
            f"{' -> '.join(cycle)}. A requirement names a guide to read first, "
            "and a cycle has no first; break it",
            "guide.requirement-cycle",
            guide.path,
        )


def _check_guides(
    content: SkillContent, plan: Plan, diagnostics: Diagnostics
) -> None:
    """Every guide reference must resolve, and every guide must be reached.

    Both directions matter: neither a task nor a facet may route a reader to
    nothing, and a selected guide that nothing in the source reaches is weight no
    reader can use. A guide reaches a reader from a list some page links: a
    task's or a facet's, or the list on a guide page one of those leads to,
    which carries what that guide requires. Reaching it through those lists is
    what counts.

    The two owners report under their own codes because they are two repairs in
    two files: a task's routing is the work it was asked for, a facet's is the
    situation it recognized, and an author holding one is not looking at the
    other.
    """
    guides = content.sources.guides
    consumed = {
        guides[identifier].path.relative_to(content.skill.root).as_posix()
        for identifier in plan.reached_guides
    }
    for item in plan.tasks:
        for identifier in item.task.guides:
            if identifier in guides:
                continue
            diagnostics.error(
                f"{item.task.path}: task {item.id} names the guide {identifier!r}, "
                "which the manifest selects no file for",
                "task.unknown-guide",
                item.task.path,
            )
    for facet in (item.facet for item in plan.facets):
        for identifier in facet.guides:
            if identifier in guides:
                continue
            diagnostics.error(
                f"{facet.path}: facet {facet.id} names the guide {identifier!r}, "
                "which the manifest selects no file for",
                "facet.unknown-guide",
                facet.path,
            )
    linked = consumed | _body_links(content)
    # The host metadata names the icon, so a host reaches it with no reference.
    icon = {content.icon_address} if content.icon_address is not None else set()
    for key in ("guides", *COPIED_CONTENT_KEYS):
        selected_for_key = {
            path.relative_to(content.skill.root).as_posix()
            for path in content.files(key)
        }
        exempt = icon if key == "assets" else set()
        for relative in sorted(selected_for_key - linked - exempt):
            path = content.skill.root / relative
            diagnostics.warning(
                f"{path}: content.{key} ships {relative}, and no task, facet, "
                "or inline reference names it",
                "content.unconsumed",
                path,
            )


def _check_reference_sources(
    content: SkillContent, diagnostics: Diagnostics
) -> None:
    """Report every inline reference the body holding it may not make.

    A principle is a standard that stands on its own, so its text references
    nothing, of any kind, and a reference there is an error whether or not
    its target resolves. Every other body may reference any kind: a principle
    reference names a principle the root already lists, and a guide reference
    makes the page carrying it an owner. Every principle file is checked,
    whether or not the skill names it, because its text is a fact about the
    file. A guide referencing itself names the page it is on, which still
    renders, so it is a warning.

    Each finding is reported once per body, however often its text repeats it.
    """
    sources = content.sources
    for principle in sources.principles.values():
        for kind, target in dict.fromkeys(inline_reference_targets(principle.body)):
            diagnostics.error(
                f"{principle.path}: principle {principle.id} references "
                f"[[{kind}:{target}]]; a principle stands on its own and may "
                "reference nothing; remove the reference",
                "principle.inline-reference",
                principle.path,
            )
    for guide in sources.guides.values():
        if guide.id in _referenced(guide.body, "guide"):
            diagnostics.warning(
                f"{guide.path}: guide {guide.id} references itself, which names "
                "the page its reader already has open; remove the reference",
                "guide.self-reference",
                guide.path,
            )


def _referenced(body: str, kind: str) -> tuple[str, ...]:
    """Every target of one kind a body references inline, once, in reading order."""
    return tuple(
        dict.fromkeys(
            target
            for found, target in inline_reference_targets(body)
            if found == kind
        )
    )


def _check_handoffs(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Every hand-off must name a task the bundle writes a page for.

    A hand-off is the one link a task page writes to another task page, and it
    is written from a declaration rather than from prose, so a target with no
    file would be a route to nothing that no reader notices until the work
    reaches it. The finding is reported against the task that declared it,
    which is the file whose hand-off names the missing page.
    """
    tasks = content.sources.tasks
    for task in tasks.values():
        for item in task.handoffs:
            if item.task in tasks:
                continue
            diagnostics.error(
                f"{task.path}: task {task.id} hands off to {item.task!r}, which "
                "the manifest selects no file for",
                "task.unknown-handoff",
                task.path,
            )


def _body_links(content: SkillContent) -> set[str]:
    """Every selected file an authored inline reference names, by source path.

    A script or asset target is resolved exactly as the renderer resolves it,
    so a reference that names a file on a page counts as using that file here.
    An ambiguous target names nothing, and its own finding says so.
    """
    root = content.skill.root
    sources = content.sources
    copied = {
        kind: [path.relative_to(root).as_posix() for path in content.files(key)]
        for key, kind in COPIED_CONTENT_KINDS.items()
    }
    found: set[str] = set()
    for body, _ in _authored_bodies(sources):
        for kind, target in inline_reference_targets(body):
            if kind in copied:
                matches = resolve_copied(target, copied[kind])
                if len(matches) == 1:
                    found.add(matches[0])
            elif kind == "guide" and (guide := sources.guides.get(target)) is not None:
                found.add(guide.path.relative_to(root).as_posix())
    return found


def _check_links(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Refuse every authored link that names bundle content by path.

    A path is written from the author's file and read from the page the text
    lands on, which is a different directory, so it would open the wrong file
    or none. An inline reference names the content instead, and the compiler
    renders it from the page itself. Each finding is reported against the
    file that holds the link, which is the file the author has to edit.
    """
    for body, path in _authored_bodies(content.sources):
        for target in dict.fromkeys(internal_links(body)):
            diagnostics.error(
                f"{path}: links {target!r} by path; name a principle, guide, "
                "script, or asset with an inline reference such as "
                "[[guide:id]] or [[asset:path]] instead",
                "link.internal-path",
                path,
            )


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
    result.plan = plan_skill(content.sources, skill.principles, skill.tasks)
    _check_principles(skill, content, diagnostics)
    _check_routed_tasks(skill, content, diagnostics)
    _check_plan(content, result.plan, diagnostics)
    _check_guide_requirements(content, result.plan, diagnostics)
    _check_guides(content, result.plan, diagnostics)
    _check_reference_sources(content, diagnostics)
    _check_handoffs(content, diagnostics)
    _check_links(content, diagnostics)
    result.quality = measure(result.plan, content.sources)
    result.rendered = render_skill(
        skill,
        content.sources,
        result.plan,
        diagnostics,
        progress=watcher,
        copied=content.selected,
        addresses=content.addresses,
    )
    _check_outputs(result, diagnostics)
    return result


def _generated_addresses(result: Compiled) -> set[str]:
    """Every bundle path a build writes that no selected file supplied.

    Most of these cannot collide with a selected file, because the compiler
    placed them around what the source claims. Two can: `SKILL.md` and the
    interface metadata are named by the host rather than by this compiler, so
    there is nowhere else to put them, and a source file copied onto one is
    reported. So is a construct's page, whose address comes from a filename the
    author chose and is theirs to change.
    """
    pages = result.rendered.pages if result.rendered is not None else {}
    return {ROOT, OPENAI_METADATA, *pages}


def _check_outputs(result: Compiled, diagnostics: Diagnostics) -> None:
    """Check what a build would write: collisions, and every link it emitted.

    Two paths collide when they differ only in letter case, because a Windows
    or macOS file system writes both to one file and keeps whichever came last.
    """
    if result.rendered is None:
        return
    content = result.content
    root = content.skill.root
    copied = [
        (copied_path(key, path.relative_to(root).as_posix()), path)
        for key in COPIED_CONTENT_KEYS
        for path in content.files(key)
    ]
    # The icon keeps its source path like a selected file, so it is checked as
    # one wherever a build writes it. Where a selected file already ships that
    # path the two are one file, nothing is written for the icon, and there is
    # nothing to collide.
    if content.icon_source is not None:
        copied += [(relative, content.icon_source) for relative in content.icon_assets]
    written: dict[str, Path] = {}
    folded: dict[str, str] = {}
    for relative, path in copied:
        previous = folded.get(relative.casefold())
        if previous == relative:
            diagnostics.error(
                f"{path}: two selected files would be written to {relative}",
                "output.path-collision",
                path,
            )
        elif previous is not None:
            diagnostics.error(
                f"{path}: {relative} and {previous} differ only in letter case, "
                "so a case-insensitive file system writes both to one file",
                "output.path-collision",
                path,
            )
        written[relative] = path
        folded.setdefault(relative.casefold(), relative)
    generated = _generated_addresses(result)
    claimed = {address.casefold(): address for address in generated}
    for relative in sorted(written):
        address = claimed.get(relative.casefold())
        if address is None:
            continue
        diagnostics.error(
            f"{written[relative]}: a generated file is written to {address}, "
            f"and the selected {relative} already occupies it; rename one of them",
            "output.path-collision",
            written[relative],
        )
    _check_directories(generated, written, diagnostics)
    shipped = set(written) | generated
    manifest = root / "skill.yaml"
    for link in result.rendered.links:
        if link.target in shipped:
            continue
        diagnostics.error(
            f"{manifest}: {link.page} references {link.target}, which is not a "
            "file this bundle ships",
            "output.broken-reference",
            manifest,
        )


def _check_directories(
    generated: set[str], written: dict[str, Path], diagnostics: Diagnostics
) -> None:
    """Check the directories a build writes, which no path names on its own.

    Two spellings of one directory that differ only in letter case are one
    directory on a Windows or macOS file system and two elsewhere, so the
    bundle, archive entries included, would depend on the host that built it.
    A file at a path some other file needs as a directory cannot be written at
    all. Generated paths are placed first, so a finding names the selected file
    that brings the conflict, and each conflicting spelling is reported once.
    """
    paths: list[tuple[str, Path | None]] = [
        *((relative, None) for relative in sorted(generated)),
        *((relative, written[relative]) for relative in sorted(written)),
    ]
    directories: dict[str, str] = {}
    introduced: dict[str, Path | None] = {}
    reported: set[str] = set()
    for relative, source in paths:
        parts = relative.split("/")
        for depth in range(1, len(parts)):
            directory = "/".join(parts[:depth])
            folded = directory.casefold()
            previous = directories.setdefault(folded, directory)
            introduced.setdefault(folded, source)
            if previous == directory or source is None or directory in reported:
                continue
            reported.add(directory)
            diagnostics.error(
                f"{source}: directory {directory} and {previous} differ only in "
                "letter case, so a case-insensitive file system writes both into "
                "one directory",
                "output.path-collision",
                source,
            )
    for relative, source in paths:
        folded = relative.casefold()
        if folded not in directories:
            continue
        culprit = source if source is not None else introduced[folded]
        if culprit is None:
            continue
        diagnostics.error(
            f"{culprit}: {relative} would be written as a file and as the "
            f"directory {directories[folded]}, which no file system can hold at "
            "one path",
            "output.path-collision",
            culprit,
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
