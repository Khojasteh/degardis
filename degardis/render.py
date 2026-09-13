"""Assemble the generated bundle: one root, one page per task, one profile index.

The shape the renderer produces is the architecture stated as files:

    SKILL.md -> tasks/<task>.md
    SKILL.md -> profiles/index.md -> the profiles that apply

There is nothing between the root and a task. An index a run always passes
through answers no question the run had, and the compiler already knows which
knowledge belongs to which task, so it puts it there instead of leaving the agent
to find it. The profile index survives that rule because it is the opposite case:
which profiles apply is decided by the situation, which only the running agent can
see, so the lookup is a real decision rather than an artefact of how the source
was filed.

Everything this module does to authored text is mechanical: it shifts heading
levels so a document becomes a section, it re-addresses relative links so they
still resolve from where the text landed, and it folds a hard-wrapped paragraph
back into one line so the author's editor width stops travelling with the text.
It does not paraphrase, merge, summarize, or drop any of it. When a page comes out too large, the renderer says
so and names what is on it; it never decides which of the author's material the
reader can do without.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, wording
from .analysis import Plan, TaskPlan
from .bundlepaths import PROFILE_INDEX, ROOT, copied_path, guide_path, principle_path, profile_path
from .markdown import (
    relative_link,
    resolve_inline_references,
    rewrite_links,
    shift_headings,
    unwrap_paragraphs,
)
from .model import Diagnostics, Skill
from .progress import Progress
from .sources import Guide, KNOWLEDGE_KINDS, Knowledge, Principle, SourceSet


# What one load costs its reader.
#
# The root is read every time this skill is selected, including by a run that
# turns out not to need it, so it is held to less than a page an agent opens
# deliberately. It is not held to nothing: it carries a compact index of the
# skill-level principles, which a reader can open when the named guidance matters.
ROOT_BUDGET_BYTES = 8 * 1024

# A task page is opened once, after the agent knows what it is doing, and carries
# that task's complete knowledge closure. It is the one place in the bundle where
# paying for a large read is the point.
TASK_BUDGET_BYTES = 24 * 1024

# Principle and guide pages are individually loaded when their activation applies,
# so both use the same small allowance as the root. A task is the deliberately
# complete knowledge page for one class of work, and is the one larger load.
PRINCIPLE_BUDGET_BYTES = 8 * 1024
GUIDE_BUDGET_BYTES = 8 * 1024

# How many contributors an oversize report names. Enough to show where the weight
# is, few enough that the finding stays one finding.
OVERSIZE_CONTRIBUTORS = 5

@dataclass(frozen=True)
class LinkUse:
    """One outbound reference the renderer emitted, and the page it emitted it on."""

    target: str
    page: str


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
    """Render the root, every task page, and the profile index and its pages."""
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
    if plan.profiles:
        bundle.pages[PROFILE_INDEX] = _render_profile_index(plan)
        for item in plan.profiles:
            page = profile_path(item.id)
            bundle.pages[page] = _render_profile(skill, item, bundle, page)
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.pages[page] = _render_guide(skill, item, bundle, page)
    _check_budgets(plan, bundle, skill, diagnostics, sources)
    return bundle


def _set_reference_targets(skill, sources, plan, bundle, copied) -> None:
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
    for item in plan.profiles:
        page = profile_path(item.id)
        bundle.source_paths[item.path.relative_to(skill.root).as_posix()] = page
        bundle.inline_targets[("profile", item.id)] = (item.title, page, item.description)
    for _, item in sorted(sources.guides.items()):
        page = guide_path(item.id)
        bundle.source_paths[item.path.relative_to(skill.root).as_posix()] = page
        bundle.inline_targets[("guide", item.id)] = (item.title, page, "")
    for key in ("assets", "scripts"):
        kind = {"assets": "asset", "scripts": "script"}[key]
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

    It carries what a reader needs before knowing which task they are on: what
    the skill is for, how to work whatever the task, which task this request is,
    and, last, where the profiles are. It carries nothing it can point at
    instead, and a section with nothing to carry contributes no heading at all.

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
    _render_router(writer, plan, bundle)
    if plan.profiles:
        writer.heading(2, wording.PROFILES_HEADING)
        writer.line(wording.PROFILES_LEAD.format(index=PROFILE_INDEX))
    return writer.text()


def _render_principles(
    writer: _Writer,
    principles: tuple[Principle, ...],
    bundle: RenderedBundle,
) -> None:
    """Put root principle links before the task routes they can govern."""
    if not principles:
        return
    unconditional = tuple(item for item in principles if not item.activation)
    conditional = tuple(item for item in principles if item.activation)
    if unconditional:
        writer.line(wording.PRINCIPLES_LEAD)
        writer.blank()
    for item in unconditional:
        page = principle_path(item.id)
        writer.line("- " + wording.PRINCIPLE_ROW.format(title=item.title, link=page))
        bundle.links.append(LinkUse(target=page, page=ROOT))
    if unconditional:
        writer.blank()
    if not conditional:
        return
    writer.line(wording.CONDITIONAL_PRINCIPLES_LEAD)
    writer.blank()
    for item in conditional:
        page = principle_path(item.id)
        writer.line(
            "- "
            + wording.CONDITIONAL_PRINCIPLE_ROW.format(
                activation=item.activation, title=item.title, link=page
            )
        )
        bundle.links.append(LinkUse(target=page, page=ROOT))
    writer.blank()


def _render_router(writer: _Writer, plan: Plan, bundle: RenderedBundle) -> None:
    """Route the request straight to the page that answers it.

    The cues are the task's own, because the author who defined the task is the
    one who knows what asking for it sounds like. Nothing is inferred from a
    task's title or its knowledge: a router built out of guesses sends a request
    to a page that does not serve it, and the agent has no way to tell.
    """
    if not plan.tasks:
        return
    writer.heading(2, wording.START_HEADING)
    _render_principles(writer, plan.root_principles, bundle)
    single = len(plan.tasks) == 1
    writer.line(wording.TASKS_SINGLE_LEAD if single else wording.TASKS_LEAD)
    writer.blank()
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
        writer.blank()
        writer.line(wording.TASKS_UNMATCHED)


# --------------------------------------------------------------------------
# A task page
# --------------------------------------------------------------------------


def _render_task(skill: Skill, item: TaskPlan, bundle: RenderedBundle, sources: SourceSet) -> str:
    """One task page, with its complete knowledge closure in one load.

    The order is what an agent reads in: what counts as done, the author's own
    method, knowledge grouped by its declared kind, and last the separately
    loaded guide files. Within each knowledge kind the
    task author's order is preserved. Nothing here is a pointer to knowledge the
    compiler could have placed instead.

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
    _render_task_principles(writer, item, bundle)
    if task.body.strip():
        writer.heading(2, wording.APPROACH_HEADING)
        writer.paragraph(_moved(task.body, task.path, skill, item.page, bundle))
    if item.knowledge:
        writer.heading(2, wording.KNOWLEDGE_HEADING)
        for kind in KNOWLEDGE_KINDS:
            units = item.of_kind(kind)
            if not units:
                continue
            writer.heading(3, wording.KNOWLEDGE_KIND_HEADINGS[kind])
            for unit in units:
                _render_unit(writer, skill, unit, item.page, bundle)
    conditional_guides = tuple(
        guide for identifier in task.guides
        if (guide := sources.guides.get(identifier)) is not None and guide.activation
    )
    unconditional_guides = tuple(
        guide for identifier in task.guides
        if (guide := sources.guides.get(identifier)) is not None and not guide.activation
    )
    if conditional_guides or unconditional_guides:
        writer.heading(2, wording.GUIDES_HEADING)
    if conditional_guides:
        writer.line(wording.CONDITIONAL_GUIDES_LEAD)
        writer.blank()
        for guide in conditional_guides:
            target = guide_path(guide.id)
            link = relative_link(target, item.page)
            writer.line(
                "- "
                + wording.CONDITIONAL_GUIDE_ROW.format(
                    title=guide.title,
                    link=link,
                    activation=guide.activation,
                )
            )
            bundle.links.append(LinkUse(target=target, page=item.page))
    if unconditional_guides:
        if conditional_guides:
            writer.blank()
        writer.line(wording.UNCONDITIONAL_GUIDES_LEAD)
        writer.blank()
        for guide in unconditional_guides:
            target = guide_path(guide.id)
            writer.line(
                "- "
                + wording.GUIDE_ROW.format(
                    title=guide.title, link=relative_link(target, item.page)
                )
            )
            bundle.links.append(LinkUse(target=target, page=item.page))
    return writer.text()


def _render_task_principles(
    writer: _Writer, item: TaskPlan, bundle: RenderedBundle
) -> None:
    """Put a task's own principle links beside its goal."""
    if not item.principles:
        return
    _render_principles_for_task(writer, item, bundle)


def _render_principles_for_task(
    writer: _Writer, item: TaskPlan, bundle: RenderedBundle
) -> None:
    """Render task links with paths relative to the page that owns them.

    Both readings sit under one heading, as they do on the root. A principle
    with an activation is not a second kind of thing to be told about under a
    heading of its own; it is the same guidance with a condition on when it is
    needed, and the condition is already on the row that carries it. Splitting
    them asks a reader who has landed on this page to notice two sections where
    the work has one set of principles.
    """
    unconditional = tuple(link for link in item.principles if not link.activation)
    conditional = tuple(link for link in item.principles if link.activation)
    writer.heading(2, wording.TASK_PRINCIPLES_HEADING)
    if unconditional:
        writer.line(wording.TASK_PRINCIPLES_LEAD)
        writer.blank()
        for link in unconditional:
            page = principle_path(link.id)
            writer.line(
                "- "
                + wording.PRINCIPLE_ROW.format(
                    title=link.title, link=relative_link(page, item.page)
                )
            )
            bundle.links.append(LinkUse(target=page, page=item.page))
        writer.blank()
    if conditional:
        writer.line(wording.TASK_CONDITIONAL_PRINCIPLES_LEAD)
        writer.blank()
        for link in conditional:
            page = principle_path(link.id)
            writer.line(
                "- "
                + wording.CONDITIONAL_PRINCIPLE_ROW.format(
                    activation=link.activation,
                    title=link.title,
                    link=relative_link(page, item.page),
                )
            )
            bundle.links.append(LinkUse(target=page, page=item.page))
        writer.blank()


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
    source,
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
    for target in _targets(authored_body, source, skill, bundle.source_paths):
        bundle.links.append(LinkUse(target=target, page=page))
    return shift_headings(text, base)


def _targets(body: str, source, skill: Skill, paths: dict[str, str]) -> list[str]:
    from .markdown import link_targets

    return link_targets(body, source, skill.root, paths)


def _inline_reference(
    kind: str,
    target: str,
    source,
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
                "profile, guide, asset, or script",
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
# Profiles
# --------------------------------------------------------------------------


def _render_profile_index(plan: Plan) -> str:
    """The one page a reader consults to decide which profiles apply.

    It exists to support a choice, so it carries what a choice needs and nothing
    else: each profile's title, its description where its author wrote one, and
    a link. It never repeats a profile's contents, because a reader who can
    decide from the index has no reason to open the page and a reader who cannot
    has just paid for the page twice.

    Rows group by category only when there are two or more categories to tell
    apart. One category over everything is a heading that separates nothing.
    """
    writer = _Writer()
    writer.line(f"# {wording.PROFILE_INDEX_HEADING}")
    writer.blank()
    writer.line(wording.PROFILE_INDEX_LEAD)
    grouped = plan.categorized
    ordered = sorted(
        plan.profiles,
        key=lambda item: ((item.category if grouped else ""), item.title.casefold()),
    )
    category: str | None = None
    writer.blank()
    for item in ordered:
        if grouped and item.category != category:
            category = item.category
            writer.heading(2, category or "Other")
        link = relative_link(profile_path(item.id), PROFILE_INDEX)
        row = (
            wording.PROFILE_ROW_DESCRIBED.format(
                title=item.title, link=link, description=item.description
            )
            if item.description
            else wording.PROFILE_ROW.format(title=item.title, link=link)
        )
        writer.line(f"- {row}")
    return writer.text()


def _render_profile(
    skill: Skill, item, bundle: RenderedBundle, page: str
) -> str:
    """One profile page: the author's guidance, under the title they gave it.

    The page says nothing of its own about what a profile is or how it ranks
    against a task's constraints. A reader arrives here from the index having
    just been told the first, and the task page states the second where the
    reader is actually holding the constraints.
    """
    writer = _Writer()
    writer.line(f"# {item.title}")
    writer.blank()
    if item.description:
        writer.line(item.description)
        writer.blank()
    writer.paragraph(_moved(item.body, item.path, skill, page, bundle, base=2))
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
