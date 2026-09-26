"""Assemble the generated bundle: one root, one page per task, one facet index.

The shape the renderer produces is the architecture stated as files:

    SKILL.md -> tasks/<task>.md
    SKILL.md -> facets/index.md -> the facets that apply
    SKILL.md -> register.md                    (when principles or guides exist)

There is nothing between the root and a task. An index a run always passes
through answers no question the run had, and the compiler already knows which
knowledge belongs to which task, so it puts it there instead of leaving the agent
to find it. The facet index survives that rule because it is the opposite case:
which facets apply is decided by the situation, which only the running agent can
see, so the lookup is a real decision rather than an artifact of how the source
was filed. When principles or guides exist, the register is neither: it routes to
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
from .analysis import Plan, TaskPlan
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
    relative_link,
    resolve_inline_references,
    shift_headings,
    unwrap_paragraphs,
)
from .model import Diagnostics, Skill
from .progress import Progress
from .sources import Facet, Guide, KNOWLEDGE_KINDS, Knowledge, Principle, SourceSet
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
# and the repair for it is the target rather than the kind.
INLINE_KINDS: tuple[str, ...] = (
    "task",
    "principle",
    "facet",
    "guide",
    *COPIED_CONTENT_KINDS.values(),
)


@dataclass(frozen=True)
class LinkUse:
    """One outbound reference the renderer emitted, and the page it emitted it on.

    `authored` marks a link an inline reference in a construct's body produced,
    rather than one the compiler wrote from a declaration. Only the first says
    where an author's own text reaches.
    """

    target: str
    page: str
    authored: bool = False


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
    """Every generated file, and every link between them a check has to resolve.

    `inline_targets` holds what a reference to a construct can open, keyed by
    its kind and id. `copied_targets` holds each copied kind's files, keyed by
    source-relative path, because a script or asset target names a trailing
    part of that path rather than an id and is resolved against all of them.
    """

    skill_text: str = ""
    pages: dict[str, str] = field(default_factory=dict)
    links: list[LinkUse] = field(default_factory=list)
    inline_targets: dict[tuple[str, str], tuple[str, str, str]] = field(
        default_factory=dict
    )
    copied_targets: dict[str, dict[str, tuple[str, str]]] = field(
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
        bundle.pages[item.page] = _render_task(item, bundle, sources, tracked)
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
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.pages[page] = _render_guide(item, bundle, page)
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
        bundle.inline_targets[("task", item.id)] = (
            item.task.title,
            item.page,
            item.task.goal,
        )
    for item in plan.principles:
        page = principle_path(item.id)
        bundle.inline_targets[("principle", item.id)] = (item.title, page, "")
    for item in plan.facets:
        page = facet_path(item.id)
        bundle.inline_targets[("facet", item.id)] = (item.title, page, item.description)
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.inline_targets[("guide", item.id)] = (item.title, page, "")
    for key, kind in COPIED_CONTENT_KINDS.items():
        files = bundle.copied_targets.setdefault(kind, {})
        for path in copied.get(key, []):
            source = path.relative_to(skill.root).as_posix()
            files[source] = (path.name, copied_path(key, source))


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
    writer.line(f"description: {yaml_string(skill.description)}")
    license_value = skill.manifest.get("license")
    writer.line("metadata:")
    writer.line(f"  version: {yaml_string(skill.version)}")
    writer.line(f"  generated_by: degardis/{__version__}")
    copyright_value = skill.manifest.get("copyright")
    if isinstance(copyright_value, str) and copyright_value.strip():
        writer.line(f"  copyright: {yaml_string(copyright_value)}")
    if isinstance(license_value, str) and license_value.strip():
        writer.line(f"  license: {yaml_string(license_value)}")
    writer.line("---")
    writer.line(f"# {_one_line(skill.title)}")
    writer.paragraph(skill.purpose)
    if _needs_register(plan, sources):
        writer.heading(2, wording.REGISTER_HEADING)
        writer.paragraph(
            wording.REGISTER_INSTRUCTIONS.format(register=addresses.register)
        )
        writer.heading(3, wording.REGISTER_GATE_HEADING)
        writer.paragraph(wording.REGISTER_GATE_INSTRUCTIONS)
    _render_link_section(
        writer,
        _PRINCIPLE_SECTION,
        _principle_links(plan.root_principles),
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
                title=_one_line(link.title),
                link=relative_link(link.target, page),
                activation=_one_line(link.activation),
            )
        )
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
                title=_one_line(item.task.title), link=link
            )
        )
        bundle.links.append(LinkUse(target=item.page, page=ROOT))
        for cue in item.task.recognize:
            writer.line(f"  - {_one_line(cue)}")
    if not single:
        writer.paragraph(wording.TASKS_UNMATCHED)


# --------------------------------------------------------------------------
# The instruction register
# --------------------------------------------------------------------------


def _render_register(plan: Plan, sources: SourceSet) -> str:
    """The form the root asks the agent to keep, written out once.

    Page rows track every principle and guide the agent may be sent to, and one
    row tracks the task it was routed to. The conformance ledger applies to
    every governing page, including the purpose, current task, and applicable
    facets once the form exists. A skill with no principle or guide pages has
    nothing separately loaded to register, so no form is emitted at all.

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
    _render_task_record(writer)
    _render_register_table(writer, wording.PRINCIPLES_HEADING, plan.principles)
    _render_register_table(
        writer,
        wording.GUIDES_HEADING,
        [sources.guides[identifier] for identifier in sorted(sources.guides)],
    )
    _render_conformance_table(writer)
    return writer.text()


def _render_task_record(writer: _Writer) -> None:
    """Write the one row naming the task the run is on, empty until routing fills it.

    It is one row rather than a history. Only the current task's page governs,
    so an earlier task kept beside it would be a second task to reconcile, and a
    row per requester message would ask the agent to re-decide routing that the
    message did not change. Its code comes from the task page the same way a
    principle's or guide's comes from theirs, so a switch of task is not recorded
    until the new page has been read.
    """
    writer.heading(2, wording.TASK_RECORD_HEADING)
    columns = list(wording.TASK_RECORD_COLUMNS)
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

    The table is compact because its reader is an agent; padding cells for
    visual alignment would add bytes without changing the record.
    """
    if not items:
        return
    writer.heading(2, heading)
    ordered = [item for item in items if not item.activation]
    ordered += [item for item in items if item.activation]
    rows = [list(wording.REGISTER_COLUMNS)]
    for item in ordered:
        rows.append(
            [
                item.id,
                _cell(item.activation) if item.activation else wording.REGISTER_UNCONDITIONAL,
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

    A title or an activation is prose an author wrote for a sentence, so it may
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
    bundle: RenderedBundle,
    sources: SourceSet,
    tracked: bool,
) -> str:
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
        _PRINCIPLE_SECTION,
        _principle_links(item.principles),
        item.page,
        bundle,
    )
    if task.body.strip():
        writer.heading(2, wording.APPROACH_HEADING)
        writer.paragraph(_moved(task.body, task.path, item.page, bundle))
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
        _guide_links(item.task.guides, sources),
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
        _Linked(guide.title, guide.activation, guide_path(guide.id))
        for identifier in references
        if (guide := sources.guides.get(identifier)) is not None
    ]


def _render_unit(
    writer: _Writer,
    unit: Knowledge,
    page: str,
    bundle: RenderedBundle,
) -> None:
    """One knowledge unit as a section of the page it was compiled into."""
    writer.heading(4, _one_line(unit.title))
    writer.paragraph(_moved(unit.body, unit.path, page, bundle, base=5))


def _render_principle_page(item: Principle, bundle: RenderedBundle, page: str) -> str:
    """Render one principle behind whichever activation link requires it."""
    writer = _Writer()
    writer.line(f"# {_one_line(item.title)}")
    writer.paragraph(_moved(item.body, item.path, page, bundle, base=2))
    return _with_read_code(writer, page)


def _render_guide(item: Guide, bundle: RenderedBundle, page: str) -> str:
    """Render one conditional knowledge page behind the task that names it."""
    writer = _Writer()
    writer.line(f"# {_one_line(item.title)}")
    writer.paragraph(_moved(item.body, item.path, page, bundle, base=2))
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
) -> str:
    """Take one authored body to its destination page, its references resolved.

    Paragraphs are folded first, so a reference the author's wrap split across
    two lines is one reference by the time it is resolved. Authored Markdown
    links are left as written: an external one needs nothing, and one written
    by path is refused by the checks rather than repaired here.
    """
    text = resolve_inline_references(
        unwrap_paragraphs(body),
        lambda kind, target: _inline_reference(
            kind, target, source, page, bundle, diagnostics=bundle.diagnostics
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
) -> str | None:
    """Render one resolved token, leaving a bad token visible for its repair."""
    if kind not in INLINE_KINDS:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline reference kind {kind!r} is not "
                f"{', '.join(INLINE_KINDS[:-1])}, or {INLINE_KINDS[-1]}",
                "inline.unknown-kind",
                source,
            )
        return None
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
        found = files[matches[0]] if matches else None
    else:
        entry = bundle.inline_targets.get((kind, target))
        found = entry[:2] if entry is not None else None
    if found is None:
        if diagnostics is not None:
            diagnostics.error(
                f"{source}: inline {kind} reference {target!r} is not selected "
                "into this bundle",
                "inline.unknown-target",
                source,
            )
        return None
    title, destination = found
    bundle.links.append(LinkUse(target=destination, page=page, authored=True))
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
            writer.heading(2, _one_line(category) or "Other")
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
    writer.line(f"# {_one_line(item.title)}")
    writer.blank()
    if item.description:
        writer.line(item.description)
        writer.blank()
    writer.paragraph(_moved(item.body, item.path, page, bundle, base=2))
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
    index and the instruction register are the exceptions: each is as long as the
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
            f"{item.path}: {page} is {size} bytes, above the "
            f"{FACET_BUDGET_BYTES}-byte budget for one facet load. "
            "Its only authored contributor is the facet itself; reduce the load "
            "without dropping the situation-specific decisions the facet owns.",
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
