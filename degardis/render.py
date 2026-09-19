"""Assemble the generated bundle: one root, one page per task, one facet index.

The shape the renderer produces is the architecture stated as files:

    SKILL.md -> tasks/<task>.md
    SKILL.md -> facets/index.md -> the facets that apply

There is nothing between the root and a task. An index a run always passes
through answers no question the run had, and the compiler already knows which
knowledge belongs to which task, so it puts it there instead of leaving the agent
to find it. The facet index survives that rule because it is the opposite case:
which facets apply is decided by the situation, which only the running agent can
see, so the lookup is a real decision rather than an artefact of how the source
was filed.

Authored text reaches a page through `markdown.py`'s transforms and through
nothing else, so this module never paraphrases, merges, summarizes, or drops any
of it. When a page comes out too large, the renderer says so and names what is
on it; it never decides which of the author's material the reader can do
without.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, wording
from .analysis import Plan, TaskPlan
from .bundlepaths import FACET_INDEX, ROOT, copied_path, facet_path, guide_path, principle_path
from .content import COPIED_CONTENT_KINDS
from .markdown import (
    link_targets,
    relative_link,
    resolve_inline_references,
    rewrite_links,
    shift_headings,
    unwrap_paragraphs,
)
from .model import Diagnostics, Skill
from .progress import Progress
from .sources import Facet, Guide, KNOWLEDGE_KINDS, Knowledge, Principle, SourceSet


# What one load costs its reader.
#
# The root is read every time this skill is selected, including by a run that
# turns out not to need it, so it is held to less than a page an agent opens
# deliberately. It is not held to nothing: it carries a compact index of the
# skill-level principles, which a reader can open when the named guidance matters.
ROOT_BUDGET_BYTES = 12 * 1024

# A task page is opened once, after the agent knows what it is doing, and carries
# that task's complete knowledge closure. It is the one place in the bundle where
# paying for a large read is the point.
TASK_BUDGET_BYTES = 24 * 1024

# Principle, guide, and facet pages are each individually loaded when the reader
# decides they apply, so all three use the same small allowance as the root. A
# task is the deliberately complete knowledge page for one class of work, and is
# the one larger load.
PRINCIPLE_BUDGET_BYTES = 8 * 1024
GUIDE_BUDGET_BYTES = 8 * 1024
FACET_BUDGET_BYTES = 8 * 1024

# How many contributors an oversize report names. Enough to show where the weight
# is, few enough that the finding stays one finding.
OVERSIZE_CONTRIBUTORS = 5

@dataclass(frozen=True)
class LinkUse:
    """One outbound reference the renderer emitted, and the page it emitted it on."""

    target: str
    page: str


@dataclass(frozen=True)
class _Linked:
    """One row of a generated list of links: its text, its condition, its page."""

    title: str
    activation: str
    target: str


@dataclass(frozen=True)
class _LinkSection:
    """The wording one list of activation-carrying links is written with.

    A list of links is one kind of thing wherever it lands: principles on the
    root and on a task page, guides on a task page and on a facet page. What
    applies always and what applies under a stated condition sit under one
    heading after one lead, because a link with an activation is not a second
    kind of guidance — it is the same guidance with the condition on the row
    that carries it. Holding the heading and the three templates together is
    what lets one renderer write every such list without deciding any of its
    words.
    """

    heading: str
    lead: str
    row: str
    conditional_row: str


_PRINCIPLE_SECTION = _LinkSection(
    heading=wording.PRINCIPLES_HEADING,
    lead=wording.PRINCIPLES_LEAD,
    row=wording.PRINCIPLE_ROW,
    conditional_row=wording.PRINCIPLE_ROW_CONDITIONAL,
)
_GUIDE_SECTION = _LinkSection(
    heading=wording.GUIDES_HEADING,
    lead=wording.GUIDES_LEAD,
    row=wording.GUIDE_ROW,
    conditional_row=wording.GUIDE_ROW_CONDITIONAL,
)


@dataclass
class RenderedBundle:
    """Every generated file, and every link between them a check has to resolve."""

    skill_text: str = ""
    pages: dict[str, str] = field(default_factory=dict)
    links: list[LinkUse] = field(default_factory=list)
    source_paths: dict[str, str] = field(default_factory=dict)
    inline_targets: dict[tuple[str, str], tuple[str, str, str]] = field(
        default_factory=dict
    )
    diagnostics: Diagnostics | None = None

    def page_bytes(self, relative: str) -> int:
        return len(self.pages.get(relative, "").encode("utf-8"))

    def page_texts(self) -> dict[str, str]:
        """Every generated page keyed by its bundle path, the root included.

        The root is a field of its own because the build writes it from there,
        so a caller asking for the generated surface as a whole would otherwise
        have to remember to put it back beside the pages. The order is the
        bundle's own: the root first, then each page by path.
        """
        return {ROOT: self.skill_text, **dict(sorted(self.pages.items()))}


class _Writer:
    """Accumulates Markdown lines, so section spacing is decided in one place."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, text: str = "") -> None:
        self.lines.append(text)

    def blank(self) -> None:
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def heading(self, level: int, text: str) -> None:
        self.blank()
        self.lines.append(f"{'#' * level} {text}")
        self.blank()

    def paragraph(self, text: str) -> None:
        if not text.strip():
            return
        self.blank()
        self.lines.extend(text.strip("\n").splitlines())
        self.blank()

    def text(self) -> str:
        body = "\n".join(self.lines).strip("\n")
        return body + "\n" if body else ""


def render_skill(
    skill: Skill,
    sources: SourceSet,
    plan: Plan,
    diagnostics: Diagnostics,
    progress: Progress | None = None,
    copied: dict[str, list[Path]] | None = None,
) -> RenderedBundle:
    """Render the root, every task page, and the facet index and its pages."""
    watcher = progress or Progress()
    watcher.phase(f"Rendering {skill.name}")
    bundle = RenderedBundle()
    bundle.diagnostics = diagnostics
    _set_reference_targets(skill, sources, plan, bundle, copied or {})
    bundle.skill_text = _render_root(skill, plan, bundle)
    for item in plan.tasks:
        bundle.pages[item.page] = _render_task(skill, item, bundle, sources)
    for item in plan.principles:
        page = principle_path(item.id)
        bundle.pages[page] = _render_principle_page(skill, item, bundle, page)
    if plan.facets:
        bundle.pages[FACET_INDEX] = _render_facet_index(plan)
        for item in plan.facets:
            page = facet_path(item.id)
            bundle.pages[page] = _render_facet(skill, item, bundle, page, sources)
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.pages[page] = _render_guide(skill, item, bundle, page)
    _check_budgets(plan, bundle, skill, diagnostics, sources)
    return bundle


def _set_reference_targets(
    skill: Skill,
    sources: SourceSet,
    plan: Plan,
    bundle: RenderedBundle,
    copied: dict[str, list[Path]],
) -> None:
    """Name every file that an inline reference can open in this bundle."""
    for item in plan.tasks:
        bundle.source_paths[item.task.path.relative_to(skill.root).as_posix()] = item.page
        bundle.inline_targets[("task", item.id)] = (
            item.task.title,
            item.page,
            item.task.goal,
        )
    for item in plan.principles:
        page = principle_path(item.id)
        bundle.source_paths[item.path.relative_to(skill.root).as_posix()] = page
        bundle.inline_targets[("principle", item.id)] = (item.title, page, "")
    for item in plan.facets:
        page = facet_path(item.id)
        bundle.source_paths[item.path.relative_to(skill.root).as_posix()] = page
        bundle.inline_targets[("facet", item.id)] = (item.title, page, item.description)
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.source_paths[item.path.relative_to(skill.root).as_posix()] = page
        bundle.inline_targets[("guide", item.id)] = (item.title, page, "")
    for key, kind in COPIED_CONTENT_KINDS.items():
        for path in copied.get(key, []):
            source = path.relative_to(skill.root).as_posix()
            page = copied_path(key, source)
            bundle.source_paths[source] = page
            title = path.name
            target = source.removeprefix(f"{key}/")
            bundle.inline_targets[(kind, target)] = (title, page, "")


# --------------------------------------------------------------------------
# The root
# --------------------------------------------------------------------------


def _render_root(skill: Skill, plan: Plan, bundle: RenderedBundle) -> str:
    """The orientation a host loads every time this skill is selected.

    It carries what a reader needs before knowing which task they are on, in the
    order they need it: what the skill is for, how to keep track of the reading
    the bundle asks for, the guidance that holds whatever the task, where the
    facets are, and last the routing that sends the request to one task page.
    Routing comes last because everything above it holds for every task, and an
    agent that has chosen its task leaves the root. It carries nothing it can
    point at instead, and a section with nothing to carry contributes no heading
    at all.

    The frontmatter is a host contract rather than orientation for the agent.
    It must remain before the Markdown body, because hosts discover a skill from
    its name and description before they load the routing text below.
    """
    writer = _Writer()
    writer.line("---")
    writer.line(f"name: {skill.name}")
    writer.line(f"description: {skill.description}")
    license_value = skill.manifest.get("license")
    writer.line("metadata:")
    writer.line(f"  version: {skill.version}")
    writer.line(f"  generated_by: degardis/{__version__}")
    copyright_value = skill.manifest.get("copyright")
    if isinstance(copyright_value, str) and copyright_value.strip():
        writer.line(f"  copyright: {copyright_value}")
    if isinstance(license_value, str) and license_value.strip():
        writer.line(f"  license: {license_value}")
    writer.line("---")
    writer.line(f"# {skill.title}")
    writer.paragraph(skill.purpose)
    if (
        plan.root_principles
        or plan.facets
        or any(item.principles or item.task.guides for item in plan.tasks)
    ):
        writer.heading(2, wording.READING_HEADING)
        writer.paragraph(wording.READING_PARAGRAPHS)
    _render_link_section(
        writer,
        _PRINCIPLE_SECTION,
        _principle_links(plan.root_principles),
        ROOT,
        bundle,
    )
    if plan.facets:
        writer.heading(2, wording.FACETS_HEADING)
        writer.paragraph(wording.FACETS_LEAD.format(index=FACET_INDEX))
    _render_router(writer, plan, bundle)
    return writer.text()


def _render_link_section(
    writer: _Writer,
    section: _LinkSection,
    links: Sequence[_Linked],
    page: str,
    bundle: RenderedBundle,
) -> None:
    """Write one list of links under one heading, unconditional rows first.

    One heading holds both readings. Splitting the conditional ones off would
    ask a reader who has landed here to notice two sections where the page has
    one set of guidance, and the unconditional rows come first because they are
    the ones every reader of this page needs. A page that opens nothing
    contributes no heading at all. Every row is recorded as an outbound link, so
    a page the build does not ship is reported rather than shipped broken.
    """
    if not links:
        return
    writer.heading(2, section.heading)
    writer.paragraph(section.lead)
    unconditional = [link for link in links if not link.activation]
    conditional = [link for link in links if link.activation]
    for link in unconditional + conditional:
        row = section.conditional_row if link.activation else section.row
        writer.line(
            "- "
            + row.format(
                title=link.title,
                link=relative_link(link.target, page),
                activation=link.activation,
            )
        )
        bundle.links.append(LinkUse(target=link.target, page=page))
    writer.blank()


def _principle_links(principles: Sequence[Principle]) -> list[_Linked]:
    return [
        _Linked(item.title, item.activation, principle_path(item.id))
        for item in principles
    ]


def _render_router(writer: _Writer, plan: Plan, bundle: RenderedBundle) -> None:
    """Route the request straight to the page that answers it.

    The cues are the task's own, because the author who defined the task is the
    one who knows what asking for it sounds like. Nothing is inferred from a
    task's title or its knowledge: a router built out of guesses sends a request
    to a page that does not serve it, and the agent has no way to tell.
    """
    if not plan.tasks:
        return
    writer.heading(2, wording.TASKS_HEADING)
    single = len(plan.tasks) == 1
    writer.paragraph(wording.TASKS_SINGLE_LEAD if single else wording.TASKS_LEAD)
    for item in plan.tasks:
        link = relative_link(item.page, ROOT)
        writer.line(
            "- "
            + wording.TASK_ROUTE.format(
                title=item.task.title, link=link
            )
        )
        bundle.links.append(LinkUse(target=item.page, page=ROOT))
        for cue in item.task.recognize:
            writer.line(f"  - {cue}")
    if not single:
        writer.paragraph(wording.TASKS_UNMATCHED)


# --------------------------------------------------------------------------
# A task page
# --------------------------------------------------------------------------


def _render_task(skill: Skill, item: TaskPlan, bundle: RenderedBundle, sources: SourceSet) -> str:
    """One task page, with its complete knowledge closure in one load.

    The order is what an agent reads in: what counts as done, the author's own
    method, knowledge grouped by its declared kind, and last the separately
    loaded guide files. Within each knowledge kind the task author's order is
    preserved. Nothing here is a pointer to knowledge the compiler could have
    placed instead.

    The recognition cues are not repeated here. They are the router's question,
    and the root has already answered it: an agent reading this page has chosen
    the task, so restating the cues asks it to decide again on a page that
    offers no alternative, and charges every run for the second copy.
    """
    task = item.task
    writer = _Writer()
    writer.line(f"# {task.title}")
    writer.heading(2, wording.GOAL_HEADING)
    writer.line(task.goal)
    _render_link_section(
        writer,
        _PRINCIPLE_SECTION,
        _principle_links(item.principles),
        item.page,
        bundle,
    )
    if task.body.strip():
        writer.heading(2, wording.APPROACH_HEADING)
        writer.paragraph(_moved(task.body, task.path, skill, item.page, bundle))
    if item.closure:
        writer.heading(2, wording.KNOWLEDGE_HEADING)
        for kind in KNOWLEDGE_KINDS:
            units = item.of_kind(kind)
            if not units:
                continue
            writer.heading(3, wording.KNOWLEDGE_KIND_HEADINGS[kind])
            for unit in units:
                _render_unit(writer, skill, unit, item.page, bundle)
    _render_link_section(
        writer,
        _GUIDE_SECTION,
        _guide_links(item.task.guides, sources),
        item.page,
        bundle,
    )
    return writer.text()


def _guide_links(
    references: Sequence[str], sources: SourceSet
) -> list[_Linked]:
    """Resolve one owner's guide references, in the order it named them.

    A guide the manifest does not select is skipped rather than linked; the
    reference is reported as unresolved by the checks, which is where an owner
    naming a guide that is not there belongs.
    """
    return [
        _Linked(guide.title, guide.activation, guide_path(guide.id))
        for identifier in references
        if (guide := sources.guides.get(identifier)) is not None
    ]


def _render_unit(
    writer: _Writer,
    skill: Skill,
    unit: Knowledge,
    page: str,
    bundle: RenderedBundle,
) -> None:
    """One knowledge unit as a section of the page it was compiled into."""
    writer.heading(4, unit.title)
    writer.paragraph(_moved(unit.body, unit.path, skill, page, bundle, base=5))


def _render_principle_page(
    skill: Skill, item: Principle, bundle: RenderedBundle, page: str
) -> str:
    """Render one principle behind whichever activation link requires it."""
    writer = _Writer()
    writer.line(f"# {item.title}")
    writer.paragraph(_moved(item.body, item.path, skill, page, bundle, base=2))
    return writer.text()


def _render_guide(skill: Skill, item: Guide, bundle: RenderedBundle, page: str) -> str:
    """Render one conditional knowledge page behind the task that names it."""
    writer = _Writer()
    writer.line(f"# {item.title}")
    writer.paragraph(_moved(item.body, item.path, skill, page, bundle, base=2))
    return writer.text()


def _moved(
    body: str,
    source: Path,
    skill: Skill,
    page: str,
    bundle: RenderedBundle,
    *,
    base: int = 3,
) -> str:
    """Take one authored body to its destination page, unchanged but re-addressed.

    Paragraphs are folded first, so a link the author's wrap split across two
    lines is one link by the time it is re-addressed and one link by the time the
    checks collect what this page points at.
    """
    body = unwrap_paragraphs(body)
    authored_body = body
    text = rewrite_links(body, source, skill.root, page, bundle.source_paths)
    text = resolve_inline_references(
        text,
        lambda kind, target: _inline_reference(
            kind, target, source, page, bundle, diagnostics=bundle.diagnostics
        ),
    )
    for target in link_targets(
        authored_body, source, skill.root, bundle.source_paths
    ):
        bundle.links.append(LinkUse(target=target, page=page))
    return shift_headings(text, base)


def _inline_reference(
    kind: str,
    target: str,
    source: Path,
    page: str,
    bundle: RenderedBundle,
    diagnostics: Diagnostics | None,
) -> str | None:
    """Render one resolved token, leaving a bad token visible for its repair."""
    available_kinds = {item[0] for item in bundle.inline_targets}
    if kind not in available_kinds:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline reference kind {kind!r} is not task, principle, "
                "facet, guide, asset, or script",
                "inline.unknown-kind",
                source,
            )
        return None
    item = bundle.inline_targets.get((kind, target))
    if item is None:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline {kind} reference {target!r} is not selected "
                "into this bundle",
                "inline.unknown-target",
                source,
            )
        return None
    title, destination, _ = item
    bundle.links.append(LinkUse(target=destination, page=page))
    return f"[{title}]({relative_link(destination, page)})"


# --------------------------------------------------------------------------
# Facets
# --------------------------------------------------------------------------


def _render_facet_index(plan: Plan) -> str:
    """The one page a reader consults to decide which facets apply.

    It exists to support a choice, so it carries what a choice needs and nothing
    else: each facet's title, its description where its author wrote one, and
    a link. It never repeats a facet's contents, because a reader who can
    decide from the index has no reason to open the page and a reader who cannot
    has just paid for the page twice.

    Rows group by category only when there are two or more categories to tell
    apart. One category over everything is a heading that separates nothing.
    """
    writer = _Writer()
    writer.line(f"# {wording.FACET_INDEX_HEADING}")
    writer.paragraph(wording.FACET_INDEX_LEAD)
    grouped = plan.categorized
    ordered = sorted(
        plan.facets,
        key=lambda item: ((item.category if grouped else ""), item.title.casefold()),
    )
    category: str | None = None
    writer.blank()
    for item in ordered:
        if grouped and item.category != category:
            category = item.category
            writer.heading(2, category or "Other")
        link = relative_link(facet_path(item.id), FACET_INDEX)
        row = (
            wording.FACET_ROW_DESCRIBED.format(
                title=item.title, link=link, description=item.description
            )
            if item.description
            else wording.FACET_ROW.format(title=item.title, link=link)
        )
        writer.line(f"- {row}")
    return writer.text()


def _render_facet(
    skill: Skill,
    item: Facet,
    bundle: RenderedBundle,
    page: str,
    sources: SourceSet,
) -> str:
    """One facet page: the author's guidance, under the title they gave it.

    The page says nothing of its own about what a facet is or how it ranks
    against a task's constraints. A reader arrives here from the index having
    just been told the first, and the task page states the second where the
    reader is actually holding the constraints.

    Guides come last, for the same reason they do on a task page: a reader who
    has to decide whether a separate load is worth opening decides it after
    reading what this page already gave them.
    """
    writer = _Writer()
    writer.line(f"# {item.title}")
    writer.blank()
    if item.description:
        writer.line(item.description)
        writer.blank()
    writer.paragraph(_moved(item.body, item.path, skill, page, bundle, base=2))
    _render_link_section(
        writer,
        _GUIDE_SECTION,
        _guide_links(item.guides, sources),
        page,
        bundle,
    )
    return writer.text()


# --------------------------------------------------------------------------
# Page size
# --------------------------------------------------------------------------


def _check_budgets(
    plan: Plan,
    bundle: RenderedBundle,
    skill: Skill,
    diagnostics: Diagnostics,
    sources: SourceSet,
) -> None:
    """Report a file that costs more than one load, and say what is on it.

    Nothing is dropped to make a page fit. The compiler cannot tell which of an
    author's material a reader could do without, and a bundle that silently
    discards an illustration or a rationale to meet a number is a bundle whose
    contents nobody reviewed. So the finding names the largest contributors,
    which is what turns "this is too big" into a decision its author can make.

    Every generated page an agent opens on its own is checked here. The facet
    index is the exception: its size is the number of facets the author wrote
    rather than anything one file says, so a warning on it would name no file
    its author could act on.
    """
    manifest = skill.root / "skill.yaml"
    root_bytes = len(bundle.skill_text.encode("utf-8"))
    if root_bytes > ROOT_BUDGET_BYTES:
        diagnostics.warning(
            f"{manifest}: generated {ROOT} is {root_bytes} bytes, above the "
            f"{ROOT_BUDGET_BYTES}-byte budget for a file loaded every time this "
            "skill is selected",
            "render.root-budget",
            manifest,
        )
    for item in plan.tasks:
        size = bundle.page_bytes(item.page)
        if size <= TASK_BUDGET_BYTES:
            continue
        diagnostics.warning(
            f"{item.task.path}: {item.page} is {size} bytes, above the "
            f"{TASK_BUDGET_BYTES}-byte budget for one load, so an agent may "
            f"receive it truncated. {_contributors(item)}",
            "render.task-budget",
            item.task.path,
        )
    for item in plan.principles:
        page = principle_path(item.id)
        size = bundle.page_bytes(page)
        if size <= PRINCIPLE_BUDGET_BYTES:
            continue
        diagnostics.warning(
            f"{item.path}: {page} is {size} bytes, above the "
            f"{PRINCIPLE_BUDGET_BYTES}-byte budget for one principle load. "
            "Its only authored contributor is the principle itself; "
            "shorten it or divide genuinely distinct guidance into principles.",
            "render.principle-budget",
            item.path,
        )
    for guide in sources.guides.values():
        page = guide_path(guide.id)
        size = bundle.page_bytes(page)
        if size <= GUIDE_BUDGET_BYTES:
            continue
        diagnostics.warning(
            f"{guide.path}: {page} is {size} bytes, above the "
            f"{GUIDE_BUDGET_BYTES}-byte budget for one guide load. "
            f"Largest contributor: {guide.path.name} {size}B. Shorten it or divide "
            "it into separately usable guides with appropriately scoped activations.",
            "render.guide-budget",
            guide.path,
        )
    for item in plan.facets:
        page = facet_path(item.id)
        size = bundle.page_bytes(page)
        if size <= FACET_BUDGET_BYTES:
            continue
        diagnostics.warning(
            f"{item.path}: {page} is {size} bytes, above the "
            f"{FACET_BUDGET_BYTES}-byte budget for one facet load. "
            "Its only authored contributor is the facet itself; shorten it, or "
            "divide it into facets the index can tell apart.",
            "render.facet-budget",
            item.path,
        )


def _contributors(item: TaskPlan) -> str:
    """Name what weighs most on one page, so its author can decide what to do."""
    weighed = sorted(
        ((len(unit.body.encode("utf-8")), unit.key) for unit in item.closure),
        reverse=True,
    )[:OVERSIZE_CONTRIBUTORS]
    if not weighed:
        return (
            "Nothing on this page comes from knowledge, so the weight is the "
            "task's own body."
        )
    listed = ", ".join(f"{key} {size}B" for size, key in weighed)
    return (
        f"Largest contributors: {listed}. Remove knowledge this task does not "
        "need, shorten what it does, split the task if it is really two, or move "
        "material to a separate guide load."
    )
