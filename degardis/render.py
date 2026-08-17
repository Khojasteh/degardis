"""Render one lowered skill as a compact control plane plus execution modules.

The root names the execution contract and exact primary module/entry. Required
workflow bodies live under ``execution/``. Profiles live beside that execution
model as optional auxiliary guidance with a compiler-generated index; no
workflow edge or validity check depends on them.
"""

from __future__ import annotations

import re
import posixpath
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import wording
from .lowering import LoweredSkill, LoweredWorkflow, Node, Transition
from .model import BLOCKED_OUTCOME, Diagnostics
from .planning import (
    Cost, ModuleCosts, candidate_orders, candidate_partitions, greedy_partition,
    maximum, path_costs,
)
from .sources import Guidance, Profile


# What an outbound Markdown reference looks like in rendered text, and what a
# bare relative path to a Markdown page looks like when nobody wrapped it in a
# link. Both are references a reader can follow, so both are found.
MARKDOWN_LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)")
# A path written as prose or as inline code. The backtick is deliberately not
# excluded: `references/policies/exceptions.md` is the way an author most
# naturally writes a path, so excluding it would catch the careless spelling
# and miss the idiomatic one.
BARE_PATH = re.compile(
    r"(?<![\w/.])(?:\./)?(?:[\w.-]+/)+[\w.-]+\.(?:md|markdown)(?![\w.])"
)

# A command has to read as a command. The compiler cannot tell whether prose is
# genuinely complete, so it holds each one to what it can check: more than one
# word, and a sentence's own closing punctuation.
SENTENCE_END = (".", "?", "!", ":")


@dataclass(frozen=True)
class LinkUse:
    """One outbound reference the renderer emitted, and where it emitted it."""

    target: str
    node: str


@dataclass
class BundleContent:
    """The copied files the renderer has to read, by the construct that owns them.

    A bundle ships references, scripts, and assets too, but the renderer never
    opens those: they are copied byte for byte, and the pages that point at
    them are built from the constructs rather than from the copied set.
    """

    profile_guides: dict[str, str] = field(default_factory=dict)


@dataclass
class RenderedBundle:
    skill_text: str = ""
    execution_modules: dict[str, str] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)
    links: list[LinkUse] = field(default_factory=list)
    node_labels: tuple[str, ...] = ()
    # Which constructs earned an auxiliary page, by kind. Pages are written
    # last, but the nodes rendered before them have to know which construct has
    # one to link, so the set is settled up front.
    auxiliary: dict[str, frozenset[str]] = field(default_factory=dict)
    execution_path_bytes: int = 0
    execution_path_loads: int = 0


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

    def field(self, label: str, value: str) -> None:
        self.lines.append(f"**{label}** {value}")

    def bullets(self, items: tuple[str, ...] | list[str]) -> None:
        for item in items:
            self.lines.append(f"- {item}")

    def text(self) -> str:
        body = "\n".join(self.lines).strip("\n")
        return body + "\n" if body else ""


def render_skill(
    lowered: LoweredSkill,
    content: BundleContent,
    diagnostics: Diagnostics,
) -> RenderedBundle:
    """Render a compact control-plane root plus required execution modules."""
    bundle = RenderedBundle()
    labels = _collect_labels(lowered, diagnostics)
    bundle.node_labels = labels
    page_constructs = _pages(lowered)
    bundle.auxiliary = _auxiliary_index(page_constructs)
    plans, module_by_label = _execution_plan(lowered, bundle, diagnostics)
    writer = _Writer()
    _render_opening(writer, lowered)
    _render_run_context(writer, lowered, bundle)
    _render_profiles(writer, lowered, bundle)
    _render_start(writer, lowered, module_by_label)
    parts = Counter(workflow.workflow.id for _, workflow, _ in plans)
    seen: Counter[str] = Counter()
    for path, workflow, nodes in plans:
        seen[workflow.workflow.id] += 1
        module = _Writer()
        _render_workflow(
            module, workflow, lowered, bundle, labels, diagnostics,
            nodes=nodes, current_module=path, module_by_label=module_by_label,
            part=seen[workflow.workflow.id], total=parts[workflow.workflow.id],
        )
        bundle.execution_modules[path] = module.text()
    check_rendered_roles(lowered, diagnostics)
    bundle.skill_text = writer.text()
    bundle.pages = _render_pages(lowered, content, bundle, page_constructs)
    return bundle


def _collect_labels(
    lowered: LoweredSkill, diagnostics: Diagnostics
) -> tuple[str, ...]:
    """Every node label, rejecting a collision rather than renaming one node.

    A transition names its destination by label, so two nodes answering to one
    label make one of them unreachable and the other ambiguous. Nothing appends
    a numeric suffix to break the tie: a label built from source ids is stable
    across rebuilds, and a generated one would not be.
    """
    seen: dict[str, Node] = {}
    for node in lowered.all_nodes():
        existing = seen.get(node.label)
        if existing is not None:
            path = lowered.sources.workflows[node.workflow].path
            diagnostics.error(
                f"{path}: two generated nodes answer to `{node.label}`: "
                f"{existing.source}; and {node.source}",
                "render.node-label-collision",
                path,
            )
            continue
        seen[node.label] = node
    return tuple(seen)


def _render_opening(writer: _Writer, lowered: LoweredSkill) -> None:
    skill = lowered.skill
    writer.line("---")
    writer.line(f"name: {skill.name}")
    writer.line(f"description: {skill.description}")
    writer.line("---")
    writer.heading(1, skill.title)
    writer.heading(2, wording.CONTRACT_HEADING)
    writer.line(wording.CONTRACT_SCOPE)
    writer.blank()
    writer.line(wording.MODULE_READING)


def _render_run_context(
    writer: _Writer, lowered: LoweredSkill, bundle: RenderedBundle
) -> None:
    names = lowered.skill.bound("guidance")
    units = [lowered.sources.guidance[name] for name in names if name in lowered.sources.guidance]
    if not units:
        return
    writer.heading(2, wording.CONTEXT_HEADING)
    writer.line(wording.CONTEXT_LEAD)
    writer.blank()
    for unit in units:
        writer.line(f"- {_context_line(unit, bundle, 'run context')}")


def _context_line(
    unit: Guidance, bundle: RenderedBundle, node: str, points: tuple[str, ...] = (),
    current_page: str = "SKILL.md",
) -> str:
    label = wording.CONTEXT_NOTE.format(id=unit.id)
    text = f"**{label}** {unit.summary}"
    page = _auxiliary_page(bundle, "guidance", unit.id, node)
    if page:
        text += f" [{wording.CONTEXT_NOTE_LINK}]({_relative_link(page, current_page)})"
    if points:
        text += "".join(f"\n  - {point}" for point in points)
    return text


def _render_node_reading(
    writer: _Writer, node: Node, bundle: RenderedBundle, current_page: str
) -> None:
    """The auxiliary pages behind what this node carries, named once.

    A guidance unit links from its own context line, because a node can carry
    several and each note already names the unit it belongs to. A heuristic's
    advice and a pattern's procedure render as one block apiece with nothing
    naming the construct beside them, so each link is titled by the construct
    it opens rather than by the field it sits under.
    """
    constructs = (("patterns", node.pattern), *(
        ("heuristics", identifier) for identifier in node.heuristics
    ))
    links = [
        f"[{identifier}]({_relative_link(target, current_page)})"
        for kind, identifier in constructs
        if identifier
        for target in (_auxiliary_page(bundle, kind, identifier, node.label),)
        if target
    ]
    if links:
        writer.field(f"{wording.PAGE_FURTHER}:", ", ".join(links))


def page_target(kind: str, identifier: str) -> str:
    """Where the auxiliary page for one construct is written in the bundle."""
    return f"references/{_PAGE_FOLDERS[kind]}/{identifier}.md"


def _relative_link(target: str, current_page: str) -> str:
    """Markdown resolves links from the containing page, on every host."""
    return posixpath.relpath(target, posixpath.dirname(current_page) or ".")


def _auxiliary_page(
    bundle: RenderedBundle, kind: str, identifier: str, node: str
) -> str:
    """The one route to a construct's auxiliary page, from where it renders.

    A page nothing points at is weight the bundle ships and the contract
    forbids opening: execution runs from `SKILL.md` outwards, so material with
    no route in is material no agent reaches. The route goes beside the text
    the construct already renders, which is the only place a reader has reason
    to follow it, and never inside a field that carries execution, which is what
    keeps it advisory: `check_rendered_roles` proves that from where a link sits
    rather than from anything the link records about itself. What comes back is
    the target, or nothing where the construct earned no page; how it reads is
    left to the caller, which knows what already names the construct beside it.
    """
    if identifier not in bundle.auxiliary.get(kind, ()):
        return ""
    target = page_target(kind, identifier)
    bundle.links.append(LinkUse(target, node))
    return target


def _render_profiles(
    writer: _Writer, lowered: LoweredSkill, bundle: RenderedBundle
) -> None:
    """Mention the optional profile lookup without enumerating the catalog.

    Profiles are deliberately outside the workflow graph.  The root pays a
    constant-size hint when any profiles exist; choosing among them is delegated
    to the auxiliary index under ``profiles/``.
    """
    if not lowered.sources.profiles:
        return
    writer.heading(2, wording.PROFILES_HEADING)
    writer.line(wording.PROFILES_LEAD)


def profile_page(profile: Profile, root: Path) -> str:
    """Return the default page path that follows one profile's source path."""
    relative = profile.path.relative_to(root).with_suffix(".md")
    if relative.parts[0] == "profiles":
        return relative.as_posix()
    return (Path("profiles") / relative).as_posix()


def _profile_pages(lowered: LoweredSkill) -> dict[str, str]:
    """Name pages from source paths, disambiguating only generated conflicts."""
    occupied = {"profiles/index.md"}
    found: dict[str, str] = {}
    for identifier, profile in sorted(lowered.sources.profiles.items()):
        candidate = profile_page(profile, lowered.skill.root)
        page = candidate
        number = 1
        while page.casefold() in occupied:
            path = PurePosixPath(candidate)
            suffix = "profile" if number == 1 else f"profile-{number}"
            page = str(path.with_name(f"{path.stem}-{suffix}{path.suffix}"))
            number += 1
        occupied.add(page.casefold())
        found[identifier] = page
    return found


def _profile_text(profile: Profile, guides: str) -> str:
    """One optional profile page: guidance only, never an execution contract."""
    writer = _Writer()
    writer.line(f"# {profile.title}")
    writer.blank()
    writer.line(
        "Auxiliary guidance only. Missing or ignoring this profile does not change "
        "requirements, validity, or failure behavior."
    )
    writer.blank()
    writer.bullets(profile.points)
    if guides.strip():
        writer.blank()
        writer.line(guides.strip())
    return writer.text()


def _profile_index(lowered: LoweredSkill, pages: dict[str, str]) -> dict[str, str]:
    """The one page listing every profile, keyed by its path in the bundle.

    A profile is chosen by the reader rather than selected by any workflow, so
    all the index owes is enough to tell the candidates apart. Every row opens
    with the link, so the titles read as one column and the description
    annotates the page it belongs to; a row for a profile that declares no
    description is then that same row without its annotation, rather than a row
    that begins with something else. Rows are ordered by id within each category
    when grouped, or across the flat list otherwise, so the page is
    identical on every host, and a miss or a false positive is harmless either
    way. A skill with no profiles contributes no page at all.
    """
    profiles = lowered.sources.profiles
    if not profiles:
        return {}

    index = _Writer()
    index.line(f"# {wording.PROFILE_INDEX_HEADING}")
    index.blank()
    index.line(wording.PROFILE_INDEX_LEAD)
    index.blank()
    grouped = len({profile.category for profile in profiles.values() if profile.category}) > 1
    ordered = sorted(
        profiles.items(),
        key=lambda item: (item[1].category if grouped else "", item[0]),
    )
    category = ""
    for identifier, profile in ordered:
        if grouped and profile.category != category:
            index.blank()
            index.line(f"## {profile.category}")
            index.blank()
            category = profile.category
        link = f"[{profile.title}]({pages[identifier].removeprefix('profiles/')})"
        row = f"{link} - {profile.description}" if profile.description else link
        index.line(f"- {row}")
    return {"profiles/index.md": index.text()}


# What one required load costs the agent performing it. A module is read whole
# and then executed, so its budget is the size of a single read on a host whose
# own output limit the compiler cannot know — not the size of the workflow,
# which nothing ever loads at once. The root is loaded every time the skill is
# selected, before any work begins, so it is held to a quarter of that.
MODULE_BUDGET_BYTES = 16 * 1024
ROOT_BUDGET_BYTES = 4 * 1024


def _execution_plan(
    lowered: LoweredSkill, bundle: RenderedBundle, diagnostics: Diagnostics
) -> tuple[list[tuple[str, LoweredWorkflow, list[Node]]], dict[str, str]]:
    """Retain only complete layouts that reduce the skill's actual path cost.

    Search callees before callers, comparing each candidate against the whole
    primary execution including outcome-specific call continuations. Candidate
    sizing is conservative; final ranking uses the renderer's exact bytes.
    The original-order greedy layout remains a candidate throughout, so bounded
    search cannot spend more runtime reading merely because it missed a layout.
    """
    workflows = {item.workflow.id: item for item in lowered.workflows}
    # A valid workflow's entry precedes all its reachable nodes in every order.
    call_modules = {
        item.entry: f"execution/{module_stem(item.workflow.id, 1)}.md"
        for item in lowered.workflows
    }
    costs = {
        identifier: _module_costs(item, lowered, bundle, call_modules)
        for identifier, item in workflows.items()
    }
    chunks = {
        identifier: greedy_partition(item.nodes, costs[identifier])
        for identifier, item in workflows.items()
    }
    sizes = {
        identifier: _layout_sizes(item, chunks[identifier], lowered, bundle, call_modules)
        for identifier, item in workflows.items()
    }
    orders = {identifier: candidate_orders(item) for identifier, item in workflows.items()}
    dependencies = {
        identifier: {node.call_workflow for node in item.nodes if node.call_workflow}
        for identifier, item in workflows.items()
    }
    ordered: list[str] = []
    pending = set(workflows)
    while pending:
        ready = sorted(identifier for identifier in pending if dependencies[identifier] <= set(ordered))
        if not ready:
            break
        ordered.extend(ready)
        pending.difference_update(ready)
    if not pending and all(orders.values()):
        def score() -> tuple[tuple[int, int, int], dict[str, dict[str, Cost]]]:
            outcomes: dict[str, dict[str, Cost]] = {}
            for identifier in ordered:
                outcomes[identifier] = path_costs(
                    workflows[identifier], chunks[identifier], sizes[identifier], outcomes
                )
            worst = (0, 0)
            for cost in outcomes.get(lowered.skill.primary_workflow, {}).values():
                worst = maximum(worst, cost)
            return (*worst, sum(sum(item) for item in sizes.values())), outcomes

        best, outcomes = score()
        for identifier in ordered:
            item = workflows[identifier]
            seen: set[tuple[tuple[str, ...], ...]] = set()
            for order in orders[identifier]:
                candidates = [greedy_partition(order, costs[identifier])]
                candidates.extend(candidate_partitions(item, order, costs[identifier], outcomes))
                for candidate in candidates:
                    identity = tuple(tuple(node.label for node in group) for group in candidate)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    candidate_sizes = _layout_sizes(item, candidate, lowered, bundle, call_modules)
                    if any(size > MODULE_BUDGET_BYTES and len(group) > 1
                           for size, group in zip(candidate_sizes, candidate)):
                        continue
                    previous_chunks, previous_sizes = chunks[identifier], sizes[identifier]
                    chunks[identifier], sizes[identifier] = candidate, candidate_sizes
                    current, current_outcomes = score()
                    if current < best:
                        best, outcomes = current, current_outcomes
                    else:
                        chunks[identifier], sizes[identifier] = previous_chunks, previous_sizes
        bundle.execution_path_bytes, bundle.execution_path_loads = best[:2]

    plans: list[tuple[str, LoweredWorkflow, list[Node]]] = []
    by_label: dict[str, str] = {}
    for workflow in lowered.workflows:
        for index, nodes in enumerate(chunks[workflow.workflow.id], start=1):
            path = f"execution/{module_stem(workflow.workflow.id, index)}.md"
            plans.append((path, workflow, nodes))
            for node in nodes:
                by_label[node.label] = path
    # Only the selected layout can report a budget finding. Trial layouts must
    # neither add diagnostics nor count advisory links in the emitted bundle.
    for path, _, nodes in plans:
        for node in nodes:
            size = _measure(lambda writer, node=node, path=path: _render_node(
                writer, node, lowered, RenderedBundle(auxiliary=bundle.auxiliary), (),
                Diagnostics(), current_module=path, module_by_label=by_label,
            )) - 1
            if size > MODULE_BUDGET_BYTES:
                _report_oversized_node(node, size, lowered, diagnostics)
    return plans, by_label


def _layout_sizes(
    workflow: LoweredWorkflow, chunks: list[list[Node]], lowered: LoweredSkill,
    bundle: RenderedBundle, call_modules: dict[str, str],
) -> list[int]:
    modules = {
        node.label: f"execution/{module_stem(workflow.workflow.id, index)}.md"
        for index, group in enumerate(chunks, 1) for node in group
    }
    modules = {**call_modules, **modules}
    sizes: list[int] = []
    for index, group in enumerate(chunks, 1):
        writer = _Writer()
        _render_workflow(
            writer, workflow, lowered, RenderedBundle(auxiliary=bundle.auxiliary), (),
            Diagnostics(), nodes=group,
            current_module=f"execution/{module_stem(workflow.workflow.id, index)}.md",
            module_by_label=modules, part=index, total=len(chunks),
        )
        sizes.append(len(writer.text().encode("utf-8")))
    return sizes


def module_stem(workflow: str, part: int) -> str:
    """The name one module answers to, which is also how an edge names it.

    Parts are numbered from one so that a module's own name and the `(2/3)` in
    its heading say the same thing.
    """
    return f"{workflow}-{part:02d}"


def module_reference(path: str) -> str:
    """How a module is named on an edge: its stem, without directory or suffix."""
    return PurePosixPath(path).stem


def _module_costs(
    workflow: LoweredWorkflow,
    lowered: LoweredSkill,
    bundle: RenderedBundle,
    call_modules: dict[str, str],
) -> ModuleCosts:
    """Measure the same node text for every order and partition under search."""
    nodes = workflow.nodes
    identifier = workflow.workflow.id
    # Reserve the widest possible part number, including workflows with more
    # than 99 modules. Local transitions remain local during body measurement;
    # call destinations use their own workflow's maximum width.
    here = f"execution/{identifier}-00.md"
    elsewhere = f"execution/{module_stem(identifier, len(nodes))}.md"
    measured_modules = {**call_modules, **dict.fromkeys((node.label for node in nodes), here)}
    # Measuring renders advisory links too, but those are not emitted links.
    measured_bundle = RenderedBundle(auxiliary=bundle.auxiliary)
    header = tuple(
        _measure(
            lambda writer, carries=carries: _render_workflow_header(
                writer, workflow, lowered, measured_bundle, carries_entry=carries,
                part=len(nodes), total=len(nodes), current_module=here,
            )
        )
        for carries in (False, True)
    )
    body: dict[str, int] = {}
    crossing: dict[str, tuple[tuple[str, int], ...]] = {}
    for node in nodes:
        whole = _measure(
            lambda writer, node=node: _render_node(
                writer, node, lowered, measured_bundle, (), Diagnostics(), current_module=here,
                module_by_label=measured_modules,
            )
        )
        near = [len(_transition_line(node, edge, here, here).encode("utf-8")) + 1
                for edge in node.transitions]
        far = [len(_transition_line(node, edge, elsewhere, here).encode("utf-8")) + 1
               for edge in node.transitions]
        body[node.label] = whole
        crossing[node.label] = tuple(
            (edge.target, distant - nearby)
            for edge, nearby, distant in zip(node.transitions, near, far)
            if not edge.blocked
        )
    return ModuleCosts(body, crossing, header, workflow.entry, MODULE_BUDGET_BYTES)


def _measure(render: Callable[[_Writer], None]) -> int:
    """Rendered bytes, plus the newline the section costs once it has a neighbour."""
    writer = _Writer()
    render(writer)
    return len(writer.text().encode("utf-8")) + 1


def _report_oversized_node(
    node: Node, size: int, lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """One node the partition cannot place, named so the author can shorten it.

    `render.module-budget` says a module is too large, which several nodes
    together can cause and a partition can then fix. One node over the budget
    on its own is the case no partition reaches, and its repair is a shorter
    command or less bound to that step, so it is worth its own code even
    though the module holding it reports as well.

    It warns rather than fails because a skill can legitimately have neither
    repair available. The bundle still builds; what it costs to load is the
    author's to weigh.
    """
    path = lowered.sources.workflows[node.workflow].path
    diagnostics.warning(
        f"{path}: generated node `{node.label}` renders to {size} bytes, above the "
        f"{MODULE_BUDGET_BYTES}-byte budget for one loaded module; no partition can "
        "divide one node, so shorten its command or reduce what is bound to that step",
        "render.node-budget",
        path,
    )


def _render_start(
    writer: _Writer, lowered: LoweredSkill, module_by_label: dict[str, str]
) -> None:
    primary = next(
        (item for item in lowered.workflows if item.workflow.id == lowered.skill.primary_workflow),
        None,
    )
    if primary is None:
        return
    entry = _entry_node(primary)
    if entry is None:
        return
    path = module_by_label.get(entry.label, "")
    writer.heading(2, wording.START_HEADING)
    writer.line(
        f"Start at `{module_reference(path)}:{entry.label}` — {node_command(entry)}"
    )


def _entry_node(item: LoweredWorkflow) -> Node | None:
    return next((node for node in item.nodes if node.label == item.entry), None)


def _carries_entry(item: LoweredWorkflow, nodes: list[Node]) -> bool:
    """Whether this module holds the node its workflow is entered at."""
    return any(node.label == item.entry for node in nodes)


def _render_workflow_header(
    writer: _Writer,
    item: LoweredWorkflow,
    lowered: LoweredSkill,
    bundle: RenderedBundle,
    *,
    carries_entry: bool,
    part: int = 1,
    total: int = 1,
    current_module: str = "",
) -> None:
    """What every module of one workflow states before its own nodes.

    A workflow larger than one module repeats this header in each of them, so
    the last field has to differ: only the module holding the entry node may
    name it. A continuation omits the entry field, because an agent
    that arrived here by an explicit load already knows the node it was sent
    to, and the alternative readings — the named entry, or the first node in
    the file — are both wrong.
    """
    workflow = item.workflow
    heading = (
        wording.WORKFLOW_HEADING.format(title=workflow.title)
        if total == 1
        else wording.WORKFLOW_HEADING_PART.format(
            title=workflow.title, part=part, total=total
        )
    )
    writer.heading(2, heading)
    writer.field(wording.WORKFLOW_ID, f"`{workflow.id}`")
    writer.field(wording.WORKFLOW_PURPOSE, workflow.description)
    inputs = ", ".join(
        f"`{name}: {declared.render()}`" for name, declared in workflow.inputs
    )
    writer.field(wording.WORKFLOW_INPUTS, inputs or wording.WORKFLOW_NO_INPUTS)
    outcomes = ", ".join(
        f"`{outcome.id}: {outcome.record}`" if outcome.record else f"`{outcome.id}`"
        for outcome in workflow.outcomes
    )
    writer.field(
        wording.WORKFLOW_OUTCOMES,
        f"{outcomes}, `{BLOCKED_OUTCOME}`" if outcomes else f"`{BLOCKED_OUTCOME}`",
    )
    entry = _entry_node(item)
    if carries_entry and entry is not None:
        writer.field(wording.WORKFLOW_ENTRY, f"`{entry.label}` - {entry.command}")
    if item.context:
        writer.blank()
        for note in item.context:
            unit = lowered.sources.guidance.get(note.id)
            if unit is not None:
                writer.line(_context_line(unit, bundle, workflow.id, note.points, current_module))


def _render_workflow(
    writer: _Writer,
    item: LoweredWorkflow,
    lowered: LoweredSkill,
    bundle: RenderedBundle,
    labels: tuple[str, ...],
    diagnostics: Diagnostics,
    *,
    nodes: list[Node] | None = None,
    current_module: str = "",
    module_by_label: dict[str, str] | None = None,
    part: int = 1,
    total: int = 1,
) -> None:
    rendered = item.nodes if nodes is None else nodes
    _render_workflow_header(
        writer, item, lowered, bundle,
        carries_entry=_carries_entry(item, rendered), part=part, total=total,
        current_module=current_module,
    )
    for node in rendered:
        _render_node(
            writer, node, lowered, bundle, labels, diagnostics,
            current_module=current_module, module_by_label=module_by_label or {},
        )


def _render_node(
    writer: _Writer,
    node: Node,
    lowered: LoweredSkill,
    bundle: RenderedBundle,
    labels: tuple[str, ...],
    diagnostics: Diagnostics,
    *,
    current_module: str = "",
    module_by_label: dict[str, str] | None = None,
) -> None:
    command = node_command(node)
    _check_command(node, command, lowered, diagnostics)
    writer.heading(3, f"[`{node.label}`] {command}")
    if node.available:
        writer.field(wording.READS, ", ".join(f"`{name}`" for name in node.available))
    if node.activation:
        writer.field(wording.ACTIVE, node.activation)
    if node.resource_operation:
        verbs = {"run": "Run", "read": "Read", "copy": "Copy", "fill": "Fill"}
        writer.field(
            "Resource",
            f"{verbs.get(node.resource_operation, node.resource_operation.title())} "
            f"`{node.resource_path}`. If the resource is unavailable or the "
            "operation fails, return `blocked`.",
        )
    if node.produces:
        writer.field(wording.PRODUCES, ", ".join(node.produces))
    if node.call_workflow:
        callee = next(
            (item for item in lowered.workflows if item.workflow.id == node.call_workflow),
            None,
        )
        entry = _entry_node(callee) if callee is not None else None
        if entry is not None:
            target = module_reference((module_by_label or {}).get(entry.label, ""))
            writer.field(
                "Call",
                f"`{target}:{entry.label}` — {node_command(entry)}",
            )
    if node.supplies:
        writer.field(wording.SUPPLIES, ", ".join(node.supplies))
    if node.kind == "check" and node.prohibits:
        # The heading renders the prohibition as the negative command it means,
        # which loses the source's own sentence; this keeps it.
        writer.field(wording.PROHIBITED, node.command)
    for invariant in node.invariants:
        label = wording.PROHIBITED if invariant.prohibits else wording.REQUIRED
        writer.field(label, f"{invariant.command} ({invariant.source})")
    if node.verify:
        writer.field(wording.VERIFY, node.verify)
    if node.state_update:
        writer.field(wording.STATE_UPDATE, node.state_update)
    if node.consider:
        writer.blank()
        writer.line(f"**{wording.CONSIDER}**")
        writer.blank()
        writer.bullets(node.consider)
    _render_node_reading(writer, node, bundle, current_module)
    if node.context:
        writer.blank()
        for note in node.context:
            unit = lowered.sources.guidance.get(note.id)
            if unit is None:
                continue
            writer.line(_context_line(unit, bundle, node.label, note.points, current_module))
    writer.blank()
    _render_transitions(
        writer, node, labels, lowered, diagnostics,
        current_module=current_module, module_by_label=module_by_label or {},
    )


def node_command(node: Node) -> str:
    """The imperative a node's heading states, which is what an agent acts on.

    A prohibition's own sentence names the thing not to do, so as a heading it
    would read as an instruction to do it. It is rendered as the negative
    command it means, while the source's own sentence stays in the Prohibited
    field below.
    """
    if node.kind == "check" and node.prohibits:
        return wording.PROHIBITION_COMMAND.format(command=_lower_first(node.command))
    return node.command


def _lower_first(text: str) -> str:
    """Lowercase a sentence's first letter, unless that word is a name.

    `Treat inferred benefit ...` becomes `treat inferred benefit ...`, while
    `SKILL.md must ...` and `Degardis reports ...` keep the capital they carry
    for their own reasons.
    """
    words = text.split(" ", 1)
    first = words[0]
    stripped = first.rstrip(".,;:")
    if len(stripped) > 1 and not stripped[1:].islower():
        return text
    return first[0].lower() + text[1:]


def _render_transitions(
    writer: _Writer,
    node: Node,
    labels: tuple[str, ...],
    lowered: LoweredSkill,
    diagnostics: Diagnostics,
    *,
    current_module: str = "",
    module_by_label: dict[str, str] | None = None,
) -> None:
    if node.kind == "return":
        writer.line(wording.RETURN_LINE)
        return
    if node.kind in ("decision", "gate"):
        lead = wording.CHOOSE_ONE if node.kind == "decision" else wording.GATE_STATES
        writer.line(lead)
        writer.blank()
    for transition in node.transitions:
        if not transition.blocked:
            _check_transition(node, transition, labels, lowered, diagnostics)
        target_module = (module_by_label or {}).get(transition.target, "")
        writer.line(_transition_line(node, transition, target_module, current_module))


def _transition_line(
    node: Node, transition: Transition, target_module: str, current_module: str
) -> str:
    """One edge as the reader meets it, in the one place that decides its text.

    The module planner has to know what an edge costs both ways before it can
    choose where a module ends, so the local and the crossing form are written
    here rather than inside the render loop: a planner that measured an edge
    differently from the renderer would size a module against text nobody
    emits.
    """
    if transition.blocked:
        return f"- {wording.ON_FAILURE}"
    if node.kind in ("decision", "gate"):
        option, _, command = transition.label.partition(" — ")
        prefix = f"- {option} — {command}"
    elif transition.label == "On success":
        prefix = "- On success"
    else:
        prefix = f"- {transition.label}"
    if target_module and current_module and target_module != current_module:
        # The destination command stays: it is what keeps an agent from
        # deciding whether to follow an edge from a module name and an opaque
        # id. What loading a module means, and what to do when it cannot be
        # read, is stated once in the execution contract instead of here.
        return (
            f"{prefix} -> `{module_reference(target_module)}:{transition.target}` "
            f"— {transition.command}"
        )
    return f"{prefix} -> `{transition.target}`"


def _check_command(
    node: Node, command: str, lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    path = lowered.sources.workflows[node.workflow].path
    if not command.strip() or len(command.split()) < 2:
        diagnostics.error(
            f"{path}: node `{node.label}` states no complete command; its "
            f"heading would read {command!r}. Source: {node.source}",
            "render.incomplete-command",
            path,
        )
        return
    if not command.rstrip().endswith(SENTENCE_END):
        diagnostics.error(
            f"{path}: node `{node.label}` states {command!r}, which does not "
            "close as a sentence; a heading an agent skims has to read as the "
            f"command it performs. Source: {node.source}",
            "render.incomplete-command",
            path,
        )


def _check_transition(
    node: Node,
    transition,
    labels: tuple[str, ...],
    lowered: LoweredSkill,
    diagnostics: Diagnostics,
) -> None:
    path = lowered.sources.workflows[node.workflow].path
    if not transition.target or transition.target not in labels:
        diagnostics.error(
            f"{path}: node `{node.label}` continues at "
            f"{transition.target or 'nothing'!r}, which is not a node defined in "
            "the generated execution graph",
            "render.external-execution-link",
            path,
        )
        return
    if not transition.command.strip():
        diagnostics.error(
            f"{path}: the transition from `{node.label}` to "
            f"`{transition.target}` states no destination command, so an agent "
            "reading it learns only a label",
            "render.incomplete-command",
            path,
        )
    _check_execution_text(
        node, "transition", f"{transition.label} {transition.command}", lowered, diagnostics
    )


def _check_execution_text(
    node: Node, role: str, text: str, lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """Reject an outbound reference inside a role that carries execution.

    The proof is the role, not the prose: this is called from the renderer's own
    execution-bearing fields, so a link found here is load-bearing by where it
    sits rather than by what it says.
    """
    found = [match.group("target") for match in MARKDOWN_LINK.finditer(text)]
    found.extend(match.group(0) for match in BARE_PATH.finditer(text))
    if not found:
        return
    path = lowered.sources.workflows[node.workflow].path
    for target in found:
        diagnostics.error(
            f"{path}: node `{node.label}` puts the reference {target} in its "
            f"{role.rstrip(':').lower()}, which carries execution; an outbound "
            "reference is supplementary documentation and cannot hold part of a command",
            "render.load-bearing-reference",
            path,
        )


def check_rendered_roles(
    lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """Scan every execution-bearing field of every node for an outbound reference."""
    for node in lowered.all_nodes():
        fields = [
            (wording.REQUIRED if not node.prohibits else wording.PROHIBITED, node.command),
            (wording.VERIFY, node.verify),
            (wording.STATE_UPDATE, node.state_update),
            (wording.PRODUCES, " ".join(node.produces)),
            (wording.SUPPLIES, " ".join(node.supplies)),
        ]
        fields.extend(
            (
                wording.PROHIBITED if invariant.prohibits else wording.REQUIRED,
                invariant.command,
            )
            for invariant in node.invariants
        )
        for role, text in fields:
            if text:
                _check_execution_text(node, role, text, lowered, diagnostics)


def _pages(lowered: LoweredSkill) -> dict[str, object]:
    """Which construct each supplementary page carries, keyed by its bundle path.

    A page is earned twice over: the construct has to carry material the
    execution nodes deliberately leave out, and the run has to reach the
    construct at all. A page for a construct nothing names is a file the bundle
    ships and no reader is sent to.
    """
    reached = lowered.reached_constructs()
    found: dict[str, object] = {}
    for kind, folder in _PAGE_FOLDERS.items():
        for identifier, construct in lowered.sources.kind(kind).items():
            if identifier not in reached.get(kind, set()):
                continue
            if not construct.has_auxiliary_material:
                continue
            found[f"references/{folder}/{identifier}.md"] = construct
    return found


_PAGE_FOLDERS = {
    "patterns": "patterns",
    "heuristics": "heuristics",
    "guidance": "guidance",
}


def _auxiliary_index(page_constructs: dict[str, object]) -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {kind: set() for kind in _PAGE_FOLDERS}
    for relative, construct in page_constructs.items():
        kind = next(
            key for key, folder in _PAGE_FOLDERS.items()
            if relative.startswith(f"references/{folder}/")
        )
        index[kind].add(construct.id)
    return {kind: frozenset(ids) for kind, ids in index.items()}


def _render_pages(
    lowered: LoweredSkill,
    content: BundleContent,
    bundle: RenderedBundle,
    page_constructs: dict[str, object],
) -> dict[str, str]:
    """Generate auxiliary pages for explicit non-binding reference material.

    Reached patterns, heuristics, and guidance may expose auxiliary references or
    points outside the required execution graph. Profiles are handled separately
    as optional guidance with an index of their own.
    """
    pages: dict[str, str] = {}
    for relative, construct in sorted(page_constructs.items()):
        pages[relative] = _page_text(construct, relative)
        for target in getattr(construct, "references", ()):
            bundle.links.append(LinkUse(target, relative))
    profile_pages = _profile_pages(lowered)
    for identifier, profile in sorted(lowered.sources.profiles.items()):
        pages[profile_pages[identifier]] = _profile_text(
            profile, content.profile_guides.get(identifier, "")
        )
    pages.update(_profile_index(lowered, profile_pages))
    return pages


def _page_text(construct, current_page: str) -> str:
    writer = _Writer()
    writer.line(f"# {construct.title}")
    writer.blank()
    summary = getattr(construct, "summary", "") or getattr(construct, "question", "")
    if summary:
        writer.blank()
        writer.line(summary)
    points = getattr(construct, "points", ())
    if points:
        writer.heading(2, wording.PAGE_POINTS)
        writer.bullets(points)
    references = getattr(construct, "references", ())
    if references:
        writer.heading(2, wording.PAGE_FURTHER)
        writer.bullets([
            f"[{target}]({_relative_link(target, current_page)})" for target in references
        ])
    return writer.text()
