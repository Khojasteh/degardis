"""Assemble the generated bundle: one root, one page per task, one facet index.

The shape the renderer produces is the architecture stated as files:

    SKILL.md -> tasks/<task>.md
    tasks/<task>.md -> tasks/<other>.md        (a declared hand-off)
    SKILL.md -> facets/index.md -> the facets that apply
    SKILL.md -> register.md                    (when principles or guides exist)

There is nothing between the root and a task. An index a run always passes
through answers no question the run had, and the compiler already knows which
knowledge belongs to which task, so it puts it there instead of leaving the agent
to find it. A hand-off is a task page linking another task page under a condition
its author declared: a route the author chose, not a hop the compiler added. The
facet index survives that rule because it is the opposite case: which facets
apply is decided by the situation, which only the running agent can see, so the
lookup is a real decision rather than an artifact of how the source was filed.
When principles or guides exist, the register is neither: it routes to
nothing, and it is written here because enumerating those separately loaded pages
is work the compiler has already done and the agent would otherwise repeat.

Authored text reaches a page through `markdown.py`'s transforms and through
nothing else, so this module never paraphrases, merges, summarizes, or drops any
of it. When a page comes out too large, the renderer says so and names what is
on it; it never decides which of the author's material the reader can do
without.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, wording
from .analysis import FacetPlan, GuidePlan, Plan, TaskPlan
from .bundlepaths import (
    Addresses,
    ROOT,
    copied_path,
    facet_path,
    guide_path,
    principle_path,
    resolve_addresses,
)
from .content import COPIED_CONTENT_KINDS, resolve_copied
from .markdown import (
    MAX_HEADING_LEVEL,
    code_span,
    heading_levels,
    relative_link,
    resolve_inline_references,
    shift_headings,
    unwrap_paragraphs,
)
from .model import Diagnostics, Skill
from .progress import Progress
from .sources import (
    Guide,
    Handoff,
    KNOWLEDGE_KINDS,
    Knowledge,
    Principle,
    SourceSet,
)
from .yamlsource import yaml_string


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

# Every kind an inline reference may name. The set is the format's, not this
# bundle's: a skill that ships no guide still knows what `[[guide:x]]` asks for,
# and the repair for it is the target rather than the kind. Tasks and facets are
# not in it, because each is reached by a route the source declares or the
# situation decides: a hand-off, the router, or the facet index.
INLINE_KINDS: tuple[str, ...] = (
    "principle",
    "guide",
    *COPIED_CONTENT_KINDS.values(),
)

# The kinds a body names as `kind:id` instead of linking, because the planner
# has made the page carrying that body an owner of every such target. A task's
# guides are owned by the task, a knowledge unit's by each task carrying it, a
# facet's by the facet, and a guide's by the guide. A principle's text may
# reference nothing, which the checks refuse, so its body names no kind.
_TASK_NAMED = frozenset({"guide"})
_KNOWLEDGE_NAMED = frozenset({"guide"})
_FACET_NAMED = frozenset({"guide"})
_GUIDE_NAMED = frozenset({"guide"})

# The kinds every body that may reference them names as `kind:id`, because the
# root already lists every target beside its conditions: only the skill owns a
# principle. No list on the
# carrying page accounts for the target, so the mention is still recorded as a
# reference the author's text makes.
_ROOT_NAMED = frozenset({"principle"})


@dataclass(frozen=True)
class LinkUse:
    """One outbound reference the renderer emitted, and the page it emitted it on.

    `authored` marks a reference that an inline reference in a construct's body
    produced, as a link, as a script's or asset's path, or as a principle's
    name, rather than a link the compiler wrote from a declaration. Only the
    first says where an author's own text reaches.
    """

    target: str
    page: str
    authored: bool = False


@dataclass(frozen=True)
class _Linked:
    """One row of a generated list of links: its text, its conditions, its page.

    The conditions are alternatives, in the order their author wrote them; an
    empty tuple is a link that always applies.
    """

    title: str
    conditions: tuple[str, ...]
    target: str


@dataclass(frozen=True)
class _LinkSection:
    """The wording one list of condition-carrying links is written with.

    A list of links is one kind of thing wherever it lands: principles on the
    root, guides on a task, facet, or guide page, and hand-offs on a task
    page. What applies always and what applies under stated conditions sit
    under one heading after one lead, because a link with conditions is not a
    second kind of guidance — it is the same guidance with the conditions on
    the row that carries it. Every such list writes its rows in one shape, so
    only the heading and the lead differ between them.
    """

    heading: str
    lead: str


_PRINCIPLE_SECTION = _LinkSection(
    heading=wording.PRINCIPLES_HEADING,
    lead=wording.PRINCIPLES_LEAD,
)
_GUIDE_SECTION = _LinkSection(
    heading=wording.GUIDES_HEADING,
    lead=wording.GUIDES_LEAD,
)
_HANDOFF_SECTION = _LinkSection(
    heading=wording.HANDOFFS_HEADING,
    lead=wording.HANDOFFS_LEAD,
)


@dataclass
class RenderedBundle:
    """Every generated file, and every link between them a check has to resolve.

    `inline_targets` holds the title and page a reference to a construct
    names, keyed by its kind and id. `copied_targets` holds each copied kind's
    bundle addresses, keyed by source-relative path, because a script or asset
    target names a trailing part of that path rather than an id and is resolved
    against all of them.
    """

    skill_text: str = ""
    pages: dict[str, str] = field(default_factory=dict)
    links: list[LinkUse] = field(default_factory=list)
    inline_targets: dict[tuple[str, str], tuple[str, str]] = field(
        default_factory=dict
    )
    copied_targets: dict[str, dict[str, str]] = field(default_factory=dict)
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
        # Split at line feeds alone: any other separator is a character the
        # author wrote, which `str.splitlines` would turn into a line break.
        self.lines.extend(text.strip("\n").split("\n"))
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
    addresses: Addresses | None = None,
) -> RenderedBundle:
    """Render the root, the register, every task page, and the facets."""
    addresses = addresses or resolve_addresses(frozenset())
    watcher = progress or Progress()
    watcher.phase(f"Rendering {skill.name}")
    bundle = RenderedBundle()
    bundle.diagnostics = diagnostics
    _set_reference_targets(skill, sources, plan, bundle, copied or {})
    bundle.skill_text = _render_root(skill, plan, sources, bundle, addresses)
    tracked = _needs_register(plan, sources)
    if tracked:
        bundle.pages[addresses.register] = _render_register(plan, sources)
    for item in plan.tasks:
        bundle.pages[item.page] = _render_task(item, plan, bundle, sources, tracked)
    for item in plan.principles:
        page = principle_path(item.id)
        bundle.pages[page] = _render_principle_page(item, bundle, page)
    if plan.facets:
        bundle.pages[addresses.facet_index] = _render_facet_index(
            plan, addresses.facet_index
        )
        for item in plan.facets:
            page = facet_path(item.id)
            bundle.pages[page] = _render_facet(item, bundle, page, sources)
    for item in plan.guides:
        page = guide_path(item.id)
        bundle.pages[page] = _render_guide(item, bundle, page, sources)
    _check_budgets(plan, bundle, skill, diagnostics, sources)
    return bundle


def _set_reference_targets(
    skill: Skill,
    sources: SourceSet,
    plan: Plan,
    bundle: RenderedBundle,
    copied: dict[str, list[Path]],
) -> None:
    """Name every file that an inline reference can name in this bundle."""
    for item in plan.principles:
        bundle.inline_targets[("principle", item.id)] = (
            item.title,
            principle_path(item.id),
        )
    for _, item in sorted(sources.guides.items()):
        bundle.inline_targets[("guide", item.id)] = (item.title, guide_path(item.id))
    for key, kind in COPIED_CONTENT_KINDS.items():
        files = bundle.copied_targets.setdefault(kind, {})
        for path in copied.get(key, []):
            source = path.relative_to(skill.root).as_posix()
            files[source] = copied_path(key, source)


# --------------------------------------------------------------------------
# The root
# --------------------------------------------------------------------------


def _needs_register(plan: Plan, sources: SourceSet) -> bool:
    """Whether the bundle has separately loaded principle or guide pages to track."""
    return bool(plan.principles or sources.guides)


def _render_root(
    skill: Skill,
    plan: Plan,
    sources: SourceSet,
    bundle: RenderedBundle,
    addresses: Addresses,
) -> str:
    """The orientation a host loads every time this skill is selected.

    It carries what a reader needs before knowing which task they are on, in the
    order they need it: the stance when the manifest states one, how to keep track of the reading
    the bundle asks for, the guidance that holds whatever the task, where the
    facets are, and last the routing that sends each outcome the request asks
    for to a task page. Routing comes last because everything above it holds for
    every task, and an agent that has chosen its route leaves the root. It
    carries nothing it can point at instead, and a section with nothing to carry
    contributes no heading at all.

    The frontmatter is a host contract rather than orientation for the agent.
    It must remain before the Markdown body, because hosts discover a skill from
    its name and description before they load the routing text below. Its
    fields are the ones the Agent Skills specification defines: `license` is one
    of them, so it sits at the top level, and what the specification does not
    define goes under `metadata`, the map it leaves for exactly that.
    """
    writer = _Writer()
    writer.line("---")
    writer.line(f"name: {yaml_string(skill.name)}")
    writer.line(f"description: {yaml_string(skill.description)}")
    license_value = skill.manifest.get("license")
    if isinstance(license_value, str) and license_value.strip():
        writer.line(f"license: {yaml_string(license_value)}")
    writer.line("metadata:")
    writer.line(f"  version: {yaml_string(skill.version)}")
    writer.line(f"  generated_by: degardis/{__version__}")
    copyright_value = skill.manifest.get("copyright")
    if isinstance(copyright_value, str) and copyright_value.strip():
        writer.line(f"  copyright: {yaml_string(copyright_value)}")
    writer.line("---")
    writer.line(f"# {_one_line(skill.title)}")
    writer.paragraph(skill.stance)
    writer.heading(2, wording.WORKING_STATE_HEADING)
    writer.paragraph(wording.WORKING_STATE_INSTRUCTIONS)
    if _needs_register(plan, sources):
        writer.heading(2, wording.REGISTER_HEADING)
        writer.paragraph(
            wording.REGISTER_INSTRUCTIONS.format(register=addresses.register)
        )
    _render_link_section(
        writer,
        _PRINCIPLE_SECTION,
        _principle_links(plan.principles),
        ROOT,
        bundle,
    )
    if plan.facets:
        writer.heading(2, wording.FACETS_HEADING)
        writer.paragraph(
            wording.FACETS_LEAD.format(index=addresses.facet_index)
        )
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

    Each target is linked once, with its conditions after it: one on the row
    itself, several as a list nested under the row, in authored order. The link
    comes first so a reader scanning the list finds what it opens before
    deciding whether it applies.
    """
    if not links:
        return
    writer.heading(2, section.heading)
    writer.paragraph(section.lead)
    unconditional = [link for link in links if not link.conditions]
    conditional = [link for link in links if link.conditions]
    for link in unconditional + conditional:
        fields = {
            "title": _one_line(link.title),
            "link": relative_link(link.target, page),
        }
        if not link.conditions:
            writer.line("- " + wording.LINK_ROW.format(**fields))
        elif len(link.conditions) == 1:
            writer.line(
                "- "
                + wording.LINK_ROW_CONDITIONAL.format(
                    **fields, condition=_one_line(link.conditions[0])
                )
            )
        else:
            writer.line("- " + wording.LINK_ROW_CONDITIONS.format(**fields))
            for condition in link.conditions:
                writer.line(f"  - {_one_line(condition)}")
        bundle.links.append(LinkUse(target=link.target, page=page))
    writer.blank()


def _one_line(text: str) -> str:
    """An authored value folded onto the one line it labels.

    A heading, a route, and a list row each end at their first newline, so a
    title or condition written across lines would leave the rest of itself as
    text that belongs to nothing. Only the whitespace moves, as when a paragraph
    is folded.
    """
    return " ".join(text.split())


def _principle_links(principles: Sequence[Principle]) -> list[_Linked]:
    return [
        _Linked(item.title, item.applicability, principle_path(item.id))
        for item in principles
    ]


def _render_router(writer: _Writer, plan: Plan, bundle: RenderedBundle) -> None:
    """Route each outcome the request asks for straight to the page that answers it.

    The cues are the task's own, because the author who defined the task is the
    one who knows what asking for it sounds like. Nothing is inferred from a
    task's title or its knowledge: a router built out of guesses sends a request
    to a page that does not serve it, and the agent has no way to tell. What a
    request asks for more than one of, and in what order, is the lead's to say
    rather than any cue's: a cue recognizes one task's outcome, and how outcomes
    combine is the same rule for every skill.
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
                title=_one_line(item.task.title), link=link
            )
        )
        bundle.links.append(LinkUse(target=item.page, page=ROOT))
        for cue in item.task.cues:
            writer.line(f"  - {_one_line(cue)}")
    if not single:
        writer.paragraph(wording.TASKS_UNMATCHED)


# --------------------------------------------------------------------------
# The progress register
# --------------------------------------------------------------------------


def _render_register(plan: Plan, sources: SourceSet) -> str:
    """The form the root asks the agent to keep, written out once.

    Page rows track every principle and guide the agent may be sent to, and the
    route table tracks the tasks it was routed to. The conformance ledger
    applies to every governing page, including the stance, current task, and
    applicable facets once the form exists. A skill with no principle or guide
    pages has nothing separately loaded to register, so no form is emitted at
    all.

    Which of them a run needs is the opposite case, and the columns are what
    keep the two apart. The compiler fills the two the source states, the id
    and the condition its author wrote, and leaves every cell the agent owns at
    one resting value. It does not pre-judge even a construct that states no
    condition: a verdict follows from encountering a link, and nothing has been
    encountered when this file is copied.

    The page carries only form fields, because it is a record rather than
    something to read. Static rows enumerate pages; the empty conformance table
    is where the running agent expands required pages into requirement-level
    state after reading them. What the fields mean is said once on the root, so
    the copied form cannot drift from a second copy of the protocol.

    A construct is named here by identity and never linked, for two reasons.
    This file is copied into a record the bundle cannot address, where a
    relative link resolves to nothing. And a link is how the bundle says one
    thing needs another: generated here, it would make every principle and
    guide look wanted by something, and the compiler could no longer tell an
    author that a file nothing names is a file nothing uses. Nothing this
    function writes is recorded as a reference.
    """
    writer = _Writer()
    writer.line(f"# {wording.REGISTER_HEADING}")
    _render_route_record(writer)
    _render_register_table(writer, wording.PRINCIPLES_HEADING, plan.principles)
    _render_register_table(
        writer,
        wording.GUIDES_HEADING,
        [sources.guides[identifier] for identifier in sorted(sources.guides)],
    )
    _render_conformance_table(writer)
    return writer.text()


def _render_route_record(writer: _Writer) -> None:
    """Write the route table, resting at one empty row until routing fills it.

    It is a table rather than one row because a request may ask for more than
    one task, and the tasks still to do are register facts: kept anywhere else
    they are the memory the root forbids. A row's code comes from the task page
    the same way a principle's or guide's comes from theirs, so a task governs
    only once its page has been read, and a hand-off adds a row rather than
    rewriting the one it interrupts.

    Why a row is on the route is a register fact for the same reason. A task
    joins it for a requested outcome or through a hand-off, one task may occur
    in more than one row, and each occurrence does only its own outcome, so a
    row that did not say which one it serves would leave that to memory too.
    """
    writer.heading(2, wording.ROUTE_HEADING)
    columns = list(wording.ROUTE_COLUMNS)
    writer.line(_table_line(columns))
    writer.line(_table_line(["---"] * len(columns)))
    writer.line(_table_line([wording.REGISTER_EMPTY] * len(columns)))
    writer.blank()


def _render_conformance_table(writer: _Writer) -> None:
    """Write the empty requirement-level ledger the running agent populates."""
    writer.heading(2, wording.CONFORMANCE_HEADING)
    rows = [list(wording.CONFORMANCE_COLUMNS)]
    writer.line(_table_line(rows[0]))
    writer.line(_table_line(["---"] * len(rows[0])))
    writer.blank()


def _render_register_table(
    writer: _Writer,
    heading: str,
    items: Sequence[Principle | Guide],
) -> None:
    """One namespace's rows, or no heading where that namespace ships nothing.

    Unconditional rows come first, as they do in every list of these constructs
    the bundle writes: an agent holding this table beside the page it came from
    is matching one against the other, and two orderings for one set is a second
    thing to reconcile before either can be used.

    A construct with several conditions takes one row per condition, adjacent
    and in authored order, its id repeated on each. The conditions are
    alternatives, so each is judged on its own: one row per condition is what
    lets a single one hold while the others do not, without the agent writing a
    compound verdict into one cell.

    The table is compact because its reader is an agent; padding cells for
    visual alignment would add bytes without changing the record.
    """
    if not items:
        return
    writer.heading(2, heading)
    ordered = [item for item in items if not item.applicability]
    ordered += [item for item in items if item.applicability]
    rows = [list(wording.REGISTER_COLUMNS)]
    for item in ordered:
        for condition in (
            [_cell(each) for each in item.applicability]
            or [wording.REGISTER_UNCONDITIONAL]
        ):
            rows.append(
                [
                    item.id,
                    condition,
                    wording.REGISTER_EMPTY,
                    wording.REGISTER_EMPTY,
                    wording.REGISTER_EMPTY,
                ]
            )
    writer.line(_table_line(rows[0]))
    writer.line(_table_line(["---"] * len(rows[0])))
    for row in rows[1:]:
        writer.line(_table_line(row))
    writer.blank()


def _table_line(cells: Sequence[str]) -> str:
    return "|" + "|".join(cells) + "|"


def _cell(text: str) -> str:
    """One authored string as a table cell, still saying what it said.

    A title or a condition is prose an author wrote for a sentence, so it may
    hold a line break or a pipe that would end the cell early and shift every
    column after it. Nothing is reworded: the text is folded onto one line and
    the pipe is escaped so it renders as the character the author typed.
    """
    return " ".join(text.split()).replace("|", r"\|")


# --------------------------------------------------------------------------
# A task page
# --------------------------------------------------------------------------


def _render_task(
    item: TaskPlan,
    plan: Plan,
    bundle: RenderedBundle,
    sources: SourceSet,
    tracked: bool,
) -> str:
    """One task page, with its complete knowledge closure in one load.

    The order is what an agent reads in: what counts as done, the hand-offs
    that bound the work, the author's own method, knowledge grouped by its
    declared kind, and last the separately loaded guide files. Principles are
    the root's: they hold across every task, so no task page lists them.
    Within each knowledge kind the task author's order is preserved. Nothing
    here is a pointer to knowledge the compiler could have placed instead.

    Hand-offs come before the approach because they bound the task: a reader
    learns which situations send the work to another task before reading how
    to do it here, and the situations are the author's, declared rather than
    written into the method.

    The recognition cues are not repeated here. They are the router's question,
    and the root has already answered it: an agent reading this page has chosen
    the task, so restating the cues asks it to decide again on a page that
    offers no alternative, and charges every run for the second copy.

    When the bundle ships a register, the page closes with the code its task
    row takes, so the row names a task only after its page has been read.
    """
    task = item.task
    writer = _Writer()
    writer.line(f"# {_one_line(task.title)}")
    writer.heading(2, wording.GOAL_HEADING)
    writer.line(task.goal)
    _render_link_section(
        writer,
        _HANDOFF_SECTION,
        _handoff_links(task.handoffs, plan),
        item.page,
        bundle,
    )
    if task.body.strip():
        writer.heading(2, wording.APPROACH_HEADING)
        writer.paragraph(
            _moved(task.body, task.path, item.page, bundle, named=_TASK_NAMED)
        )
    if item.closure:
        writer.heading(2, wording.KNOWLEDGE_HEADING)
        for kind in KNOWLEDGE_KINDS:
            units = item.of_kind(kind)
            if not units:
                continue
            writer.heading(3, wording.KNOWLEDGE_KIND_HEADINGS[kind])
            for unit in units:
                _render_unit(writer, unit, item.page, bundle)
    _render_link_section(
        writer,
        _GUIDE_SECTION,
        _guide_links(item.guides, sources),
        item.page,
        bundle,
    )
    return _with_read_code(writer, item.page) if tracked else writer.text()


def _guide_links(
    references: Sequence[str], sources: SourceSet
) -> list[_Linked]:
    """Resolve one owner's guide references, in the order it named them.

    A guide the manifest does not select is skipped rather than linked; the
    reference is reported as unresolved by the checks, which is where an owner
    naming a guide that is not there belongs.
    """
    return [
        _Linked(guide.title, guide.applicability, guide_path(guide.id))
        for identifier in references
        if (guide := sources.guides.get(identifier)) is not None
    ]


def _handoff_links(references: Sequence[Handoff], plan: Plan) -> list[_Linked]:
    """Resolve one task's hand-offs, in the order it declared them.

    A target the manifest selects no task for is skipped rather than linked;
    the reference is reported as unresolved by the checks, which is where a
    task naming a page that is not there belongs.
    """
    return [
        _Linked(target.task.title, item.applicability, target.page)
        for item in references
        if (target := plan.task(item.task)) is not None
    ]


def _render_unit(
    writer: _Writer,
    unit: Knowledge,
    page: str,
    bundle: RenderedBundle,
) -> None:
    """One knowledge unit as a section of the page it was compiled into."""
    writer.heading(4, _one_line(unit.title))
    writer.paragraph(
        _moved(unit.body, unit.path, page, bundle, base=5, named=_KNOWLEDGE_NAMED)
    )


def _render_principle_page(item: Principle, bundle: RenderedBundle, page: str) -> str:
    """Render one principle behind whichever link requires it."""
    writer = _Writer()
    writer.line(f"# {_one_line(item.title)}")
    writer.paragraph(_moved(item.body, item.path, page, bundle, base=2))
    return _with_read_code(writer, page)


def _render_guide(
    item: GuidePlan, bundle: RenderedBundle, page: str, sources: SourceSet
) -> str:
    """One conditional knowledge page, closing with the guides it owns.

    Its guides come last, as they do on a task or facet page. A guide this one
    requires or references is listed here rather than on the pages that lead
    here, so its reader judges its conditions once this guide applies; the
    body names a guide it references rather than linking it.
    """
    guide = item.guide
    writer = _Writer()
    writer.line(f"# {_one_line(guide.title)}")
    writer.paragraph(
        _moved(guide.body, guide.path, page, bundle, base=2, named=_GUIDE_NAMED)
    )
    _render_link_section(
        writer,
        _GUIDE_SECTION,
        _guide_links(item.guides, sources),
        page,
        bundle,
    )
    return _with_read_code(writer, page)


def _with_read_code(writer: _Writer, page: str) -> str:
    """Close a register-tracked page with the code its register row takes.

    A row's `Read code` can then be filled only by opening this page: the code
    is printed here and nowhere else in the bundle, so neither the root, the
    register, nor another page can supply it, and it comes last so a read that
    reaches it has passed everything above it. A thematic break sets it apart,
    so the compiler's line is not taken for the author's closing sentence; the
    writer's paragraph spacing keeps a blank line above the break, without which
    Markdown would read it as underlining the text before it into a heading.

    The code is derived from the page's own address and text, so a rebuild of
    unchanged source prints the same code and an edit to the page prints a new
    one, which leaves a register filled before the edit visibly stale on
    exactly the rows the edit touched.
    """
    text = writer.text()
    code = hashlib.sha256(f"{page}\n{text}".encode()).hexdigest()[:8]
    writer.paragraph("---")
    writer.paragraph(wording.READ_CODE_LINE.format(code=code))
    return writer.text()


def _moved(
    body: str,
    source: Path,
    page: str,
    bundle: RenderedBundle,
    *,
    base: int = 3,
    named: frozenset[str] = frozenset(),
) -> str:
    """Take one authored body to its destination page, its references resolved.

    Paragraphs are folded first, so a reference the author's wrap split across
    two lines is one reference by the time it is resolved. Authored Markdown
    links are left as written: an external one needs nothing, and one written
    by path is refused by the checks rather than repaired here. `named` holds
    the kinds whose references the carrying page links in its own lists, so
    the body names them instead.

    A body whose headings span more levels than fit below `base` is reported:
    Markdown stops at level six, so its deepest headings would merge there.
    """
    levels = heading_levels(body)
    if levels and bundle.diagnostics is not None:
        depth = max(levels) - min(levels) + 1
        if base + depth - 1 > MAX_HEADING_LEVEL:
            bundle.diagnostics.warning(
                f"{source}: its headings span {depth} levels, which from level "
                f"{base} would reach level {base + depth - 1}; Markdown stops at "
                f"level {MAX_HEADING_LEVEL}, so the deepest are written as one",
                "render.heading-depth",
                source,
            )
    text = resolve_inline_references(
        unwrap_paragraphs(body),
        lambda kind, target: _inline_reference(
            kind,
            target,
            source,
            page,
            bundle,
            diagnostics=bundle.diagnostics,
            named=named,
        ),
    )
    return shift_headings(text, base)


def _inline_reference(
    kind: str,
    target: str,
    source: Path,
    page: str,
    bundle: RenderedBundle,
    diagnostics: Diagnostics | None,
    named: frozenset[str] = frozenset(),
) -> str | None:
    """Render one resolved token, leaving a bad token visible for its repair.

    A script or asset is something the reader runs or uses rather than a page
    it reads, so it renders as its bundle path. A principle or guide is named
    as `kind:id` rather than opening a second route to its page from the middle
    of the text, wherever another list already links it under the heading its
    register row is kept by: a principle always, from the root, and a guide
    where its kind is `named`, because the planner has made the page carrying
    the body an owner. A guide anywhere else renders as a link to its page;
    only a principle's text, which the checks refuse, reaches that case.
    """
    if kind not in INLINE_KINDS:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline reference kind {kind!r} is not "
                f"{', '.join(INLINE_KINDS[:-1])}, or {INLINE_KINDS[-1]}",
                "inline.unknown-kind",
                source,
            )
        return None
    title = ""
    if kind in bundle.copied_targets:
        files = bundle.copied_targets[kind]
        matches = resolve_copied(target, files)
        if len(matches) > 1:
            if diagnostics is not None:
                diagnostics.error(
                    f"{source}: inline {kind} reference {target!r} matches "
                    f"{', '.join(matches)}; write more of the path so it names "
                    "one of them",
                    "inline.ambiguous-target",
                    source,
                )
            return None
        destination = files[matches[0]] if matches else None
    else:
        entry = bundle.inline_targets.get((kind, target))
        title, destination = entry if entry is not None else ("", None)
    if destination is None:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline {kind} reference {target!r} is not selected "
                "into this bundle",
                "inline.unknown-target",
                source,
            )
        return None
    if kind in bundle.copied_targets:
        bundle.links.append(LinkUse(target=destination, page=page, authored=True))
        return code_span(destination)
    if kind in named:
        return code_span(f"{kind}:{target}")
    bundle.links.append(LinkUse(target=destination, page=page, authored=True))
    if kind in _ROOT_NAMED:
        return code_span(f"{kind}:{target}")
    return f"[{_one_line(title)}]({relative_link(destination, page)})"


# --------------------------------------------------------------------------
# Facets
# --------------------------------------------------------------------------


def _render_facet_index(plan: Plan, page: str) -> str:
    """The one page a reader consults to decide which facets apply.

    It exists to support a choice, so it carries what a choice needs and nothing
    else: each facet's title, its description where its author wrote one, and
    a link. It never repeats a facet's contents, because a reader who can
    decide from the index has no reason to open the page and a reader who cannot
    has just paid for the page twice.

    Rows group by category only when there are two or more categories to tell
    apart. One category over everything is a heading that separates nothing.
    Facets stating no category are the residue of that grouping, so their group
    comes after every named one.
    """
    writer = _Writer()
    writer.line(f"# {wording.FACET_INDEX_HEADING}")
    writer.paragraph(wording.FACET_INDEX_LEAD)
    grouped = plan.categorized
    ordered = sorted(
        (item.facet for item in plan.facets),
        key=lambda item: (
            (not item.category, item.category) if grouped else (False, ""),
            item.title.casefold(),
        ),
    )
    category: str | None = None
    writer.blank()
    for item in ordered:
        if grouped and item.category != category:
            category = item.category
            writer.heading(
                2, _one_line(category) or wording.FACET_INDEX_UNCATEGORIZED
            )
        link = relative_link(facet_path(item.id), page)
        title = _one_line(item.title)
        row = (
            wording.FACET_ROW_DESCRIBED.format(
                title=title, link=link, description=_one_line(item.description)
            )
            if item.description
            else wording.FACET_ROW.format(title=title, link=link)
        )
        writer.line(f"- {row}")
    return writer.text()


def _render_facet(
    item: FacetPlan,
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
    reading what this page already gave them. A guide the body references is
    among them, so the body names it rather than linking it.
    """
    facet = item.facet
    writer = _Writer()
    writer.line(f"# {_one_line(facet.title)}")
    writer.blank()
    if facet.description:
        writer.line(facet.description)
        writer.blank()
    writer.paragraph(
        _moved(facet.body, facet.path, page, bundle, base=2, named=_FACET_NAMED)
    )
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
    index and the progress register are the exceptions: each is as long as the
    number of constructs the author wrote rather than anything one file says,
    so a warning on either would name no file its author could act on.
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
            f"receive it truncated. {_contributors(item)} Reduce the generated "
            "load without dropping material the task requires.",
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
            "Its only authored contributor is the principle itself; reduce the "
            "load without changing the guidance or reach the principle must provide.",
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
            f"Largest contributor: {guide.path.name} {size}B. Reduce the load "
            "without dropping guidance needed on the paths that open it.",
            "render.guide-budget",
            guide.path,
        )
    for item in plan.facets:
        page = facet_path(item.id)
        size = bundle.page_bytes(page)
        if size <= FACET_BUDGET_BYTES:
            continue
        diagnostics.warning(
            f"{item.facet.path}: {page} is {size} bytes, above the "
            f"{FACET_BUDGET_BYTES}-byte budget for one facet load. "
            "Its only authored contributor is the facet itself; reduce the load "
            "without dropping the situation-specific decisions the facet owns.",
            "render.facet-budget",
            item.facet.path,
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
