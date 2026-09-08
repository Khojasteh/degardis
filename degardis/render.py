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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path, PurePosixPath

from . import wording
from .dexpr import render_literal
from .lowering import LoweredSkill, LoweredWorkflow, Node, Transition
from .model import BLOCKED_OUTCOME, Diagnostics, Entrypoint
from .progress import Progress
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

# How a Markdown document states its own name, which is what a link to it is
# titled by. Both heading forms are read, because an author who wrote one and
# got a path in the link would have no way to tell which spelling the compiler
# wanted. A fence is tracked so that a `#` comment inside an opening code block
# does not name the document, and front matter is skipped so that its closing
# `---` is not read as the underline of a setext heading.
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
CODE_FENCE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
FRONT_MATTER = "---"

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
    binding_bytes: dict[tuple[str, str], int] = field(default_factory=dict)


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
    diagnostics: Diagnostics,
    progress: Progress | None = None,
) -> RenderedBundle:
    """Render a compact control-plane root plus required execution modules."""
    bundle = RenderedBundle()
    watcher = progress or Progress()
    labels = _collect_labels(lowered, diagnostics)
    bundle.node_labels = labels
    page_constructs = _pages(lowered)
    bundle.auxiliary = _auxiliary_index(page_constructs)
    plans, module_by_label = _execution_plan(lowered, bundle, diagnostics, watcher)
    watcher.phase(f"Rendering {lowered.skill.name}")
    writer = _Writer()
    _render_opening(writer, lowered)
    _render_run_context(writer, lowered, bundle)
    _render_profiles(writer, lowered, bundle)
    _render_start(writer, lowered, module_by_label, diagnostics)
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
    bundle.pages = _render_pages(lowered, bundle, page_constructs, diagnostics)
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
    writer: _Writer,
    node: Node,
    lowered: LoweredSkill,
    bundle: RenderedBundle,
    current_page: str,
) -> None:
    """The auxiliary pages behind what this node carries, named once.

    A guidance unit links from its own context line, because a node can carry
    several and each note already names the unit it belongs to. A heuristic's
    advice and a pattern's procedure render as one block apiece with nothing
    naming the construct beside them, so the link is the whole of what an agent
    decides from, and it is titled by the heading of the page it opens rather
    than by the identifier that page is filed under.
    """
    constructs = (("patterns", node.pattern), *(
        ("heuristics", identifier) for identifier in node.heuristics
    ))
    links = [
        f"[{lowered.sources.kind(kind)[identifier].title}]"
        f"({_relative_link(target, current_page)})"
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


def _profile_text(
    profile: Profile, current_page: str, titles: dict[str, str]
) -> str:
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
    _further_reading(writer, profile.references, current_page, titles)
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
# which nothing ever loads at once.
MODULE_BUDGET_BYTES = 16 * 1024

# The root is loaded every time the skill is selected, before any work begins,
# so it is held to less. The figure is what a routing table costs rather than a
# fraction of the module budget: the compiler-owned floor is fixed at roughly
# 1 KiB — the execution contract alone is 719 bytes and the profiles section
# another 247 — the run-level context reaches about 1.2 KiB on a skill that
# binds several guidance units, and one route costs its condition plus the
# destination's whole command, which measured 317 and 688 bytes on two shipped
# skills carrying a single route each. Worst observed overhead plus eight routes
# at the larger of those two is a little over 8000 bytes, so eight is the number
# of routes this holds before an author hears about it. Raising the ceiling
# costs a skill that does not route anything, because the budget is a warning
# threshold and never a size: a one-route root still renders about 1.5 KiB.
ROOT_BUDGET_BYTES = 8 * 1024


def _execution_plan(
    lowered: LoweredSkill, bundle: RenderedBundle, diagnostics: Diagnostics,
    progress: Progress | None = None,
) -> tuple[list[tuple[str, LoweredWorkflow, list[Node]]], dict[str, str]]:
    """Retain only complete layouts that reduce the skill's actual path cost.

    Search callees before callers, comparing each candidate against the whole
    primary execution including outcome-specific call continuations. Candidate
    sizing is conservative; final ranking uses the renderer's exact bytes.
    The original-order greedy layout remains a candidate throughout, so bounded
    search cannot spend more runtime reading merely because it missed a layout.
    """
    watcher = progress or Progress()
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
        def score(
            first: int = 0, settled: dict[str, dict[str, Cost]] | None = None
        ) -> tuple[tuple[int, int, int], dict[str, dict[str, Cost]]]:
            """Cost the whole skill, reusing the callee results a trial cannot move.

            `ordered` places a workflow after everything it calls, so nothing
            before `first` can reach the workflow being tried, directly or
            through another. Their outcome costs are the same for every
            candidate of that workflow and are carried in rather than recomputed.
            """
            outcomes: dict[str, dict[str, Cost]] = dict(settled or {})
            for identifier in ordered[first:]:
                outcomes[identifier] = path_costs(
                    workflows[identifier], chunks[identifier], sizes[identifier], outcomes
                )
            # Worst path over every root, not over one of them: a run enters
            # whichever entrypoint matched, so a layout ranked on a single root
            # would be free to make another root's route arbitrarily expensive.
            worst = (0, 0)
            for root in lowered.skill.roots:
                for cost in outcomes.get(root, {}).values():
                    worst = maximum(worst, cost)
            return (*worst, sum(sum(item) for item in sizes.values())), outcomes

        best, outcomes = score()
        for position, identifier in enumerate(ordered):
            watcher.phase(f"Planning modules {position + 1}/{len(ordered)}")
            item = workflows[identifier]
            settled = {key: outcomes[key] for key in ordered[:position]}
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
                    current, current_outcomes = score(position, settled)
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


@cache
def module_reference(path: str) -> str:
    """How a module is named on an edge: its stem, without directory or suffix.

    A pure function of the path, cached because the layout search names the
    same handful of modules once per edge per candidate it measures.
    """
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
    writer: _Writer,
    lowered: LoweredSkill,
    module_by_label: dict[str, str],
    diagnostics: Diagnostics,
) -> None:
    """Where a run begins: one load, or the choice among the routes into it.

    This is the only section of the root that decides anything, and it decides
    it from the request alone — nothing has run, so there is no value to read.
    That is why each route is a sentence rather than a condition: an agent
    matches it the way it matches a decision's options.

    A skill with one unconditional route states where to start, because a choice
    with one answer is not a choice. Every other shape renders the table, whose
    last row is the unconditional route where the source declared one and a
    fail-closed return where it did not.
    """
    routes = _start_routes(lowered, module_by_label, diagnostics)
    if not routes:
        return
    catch_all = lowered.skill.default_entrypoint
    writer.heading(2, wording.START_HEADING)
    if len(routes) == 1 and catch_all is not None:
        writer.line(wording.START_SINGLE.format(target=routes[0][1]))
        return
    writer.line(wording.START_LEAD)
    writer.blank()
    writer.bullets(
        [
            f"{condition} -> {target}"
            for condition, target in routes[:-1]
        ]
        + [f"{routes[-1][0]} -> {routes[-1][1]}"]
    )
    if catch_all is None:
        writer.blank()
        writer.line(wording.START_UNMATCHED)


def _start_routes(
    lowered: LoweredSkill, module_by_label: dict[str, str], diagnostics: Diagnostics
) -> list[tuple[str, str]]:
    """Each declared route as the condition to match and the load it leads to.

    A route whose target never reached the execution graph contributes nothing:
    the compilation that dropped it has already reported why, and rendering a
    row pointing at a module no build writes would turn that finding into a
    dead load an agent is told to perform.
    """
    reached = {item.workflow.id: item for item in lowered.workflows}
    catch_all = lowered.skill.default_entrypoint
    found: list[tuple[str, str]] = []
    for route in lowered.skill.entrypoints:
        item = reached.get(route.target)
        entry = _entry_node(item) if item is not None else None
        if entry is None:
            continue
        condition = (
            wording.START_OTHERWISE if route is catch_all or not route.when
            else _route_condition(route, lowered, diagnostics)
        )
        target = crossing_load(
            module_by_label.get(entry.label, ""), entry.label, node_command(entry)
        )
        found.append((condition, target + _route_supplies(route, lowered, diagnostics)))
    return found


def _route_supplies(
    route: Entrypoint, lowered: LoweredSkill, diagnostics: Diagnostics
) -> str:
    """What this route hands its target, stated where the route is chosen.

    The entry node is the same node whichever route reached it, so it cannot
    say which one did; the route line can, and it is in the file the host has
    already loaded. Only the name and the value are stated: the entered module
    declares the input's type on its own header, and the root is held to a
    smaller budget than a module because it is loaded on every run.

    The value renders in an execution position, so it is held to what the
    control plane may carry, exactly as the route's condition is: a literal that
    sent the agent to a document to find out what it was given would put part of
    the route's own meaning outside the file that decides the route.
    """
    if not route.supplied:
        return ""
    path = lowered.skill.root / "skill.yaml"
    for name, binding in route.supplied:
        text = binding.literal if isinstance(binding.literal, str) else ""
        found = [match.group("target") for match in MARKDOWN_LINK.finditer(text)]
        found.extend(match.group(0) for match in BARE_PATH.finditer(text))
        for reference in found:
            diagnostics.error(
                f"{path}: entrypoints.{route.id}.with.{name} puts the reference "
                f"{reference} in the value it supplies, which carries execution; "
                "an outbound reference is supplementary documentation and cannot "
                "hold part of a command",
                "render.load-bearing-reference",
                path,
            )
    stated = ", ".join(
        f"`{name}`: {binding.render()}" for name, binding in route.supplied
    )
    return f" **{wording.SUPPLIES}** {stated}"


def _route_condition(
    route: Entrypoint, lowered: LoweredSkill, diagnostics: Diagnostics
) -> str:
    """One route's discriminator, held to what the root may carry.

    The sentence is the author's, and it renders in an execution position: an
    agent acts on it to choose a module to load. So it is checked the way a
    node's command is — it has to close as a sentence, and it may carry no link
    or bare path, because a route that sent a reader somewhere else to find out
    whether it applies would put required execution outside the control plane.
    """
    path = lowered.skill.root / "skill.yaml"
    text = route.when.rstrip()
    found = [match.group("target") for match in MARKDOWN_LINK.finditer(text)]
    found.extend(match.group(0) for match in BARE_PATH.finditer(text))
    for target in found:
        diagnostics.error(
            f"{path}: entrypoints.{route.id} puts the reference {target} in the "
            "condition it is selected by, which carries execution; an outbound "
            "reference is supplementary documentation and cannot hold part of "
            "a command",
            "render.load-bearing-reference",
            path,
        )
    if len(text.split()) < 2 or not text.endswith(SENTENCE_END):
        diagnostics.error(
            f"{path}: entrypoints.{route.id} states its condition as {text!r}, "
            "which does not close as a sentence an agent can match a request "
            "against",
            "render.incomplete-command",
            path,
        )
    return text


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
    defaults = ", ".join(
        wording.WORKFLOW_DEFAULT.format(
            name=name, type=declared.render(), value=render_literal(value)
        )
        for name, (declared, value) in item.graph.defaults.items()
    )
    if defaults:
        writer.field(wording.WORKFLOW_DEFAULTS, defaults)
    entry = _entry_node(item)
    if carries_entry and entry is not None:
        writer.field(wording.WORKFLOW_ENTRY, f"`{entry.label}` - {node_command(entry)}")
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
    first_line = len(writer.lines)
    invariant_bytes = 0
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
    # A `during` item bounds this node's own command, and a grouped check
    # node's items are its work. Both render as one obligation apiece, because
    # the position is what says which of the two an item is, and an agent acts
    # on the sentence either way.
    for invariant in (*node.invariants, *node.checks):
        label = wording.PROHIBITED if invariant.prohibits else wording.REQUIRED
        # The command is the whole of what the agent acts on. Which construct
        # and provision it was bound from is provenance, and `inspect` already
        # carries it against the item; rendering it here would charge every
        # placement for a citation no run can act on.
        writer.field(label, invariant.command)
        # The activation and the proof follow the sentence they belong to,
        # because adjacency is the whole of what pairs them: a node may carry
        # several invariants, and this is the only position that says which one
        # a condition activates and which one a verification proves.
        first = len(writer.lines) - 1
        if invariant.activation:
            writer.field(wording.ACTIVE, invariant.activation)
        if invariant.verify:
            writer.field(wording.VERIFY, invariant.verify)
        size = sum(
            len((line + "\n").encode("utf-8")) for line in writer.lines[first:]
        )
        identifier = invariant.construct + (f".{invariant.local}" if invariant.local else "")
        key = (invariant.kind, identifier)
        bundle.binding_bytes[key] = bundle.binding_bytes.get(key, 0) + size
        invariant_bytes += size
    if node.verify:
        writer.field(wording.VERIFY, node.verify)
    if node.state_update:
        writer.field(wording.STATE_UPDATE, node.state_update)
    if node.consider:
        writer.blank()
        writer.line(f"**{wording.CONSIDER}**")
        writer.blank()
        writer.bullets(node.consider)
    _render_node_reading(writer, node, lowered, bundle, current_module)
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
    kind, _, identifier = node.origin.partition(":")
    key = None
    # A check node carrying several items charged each of them its own lines
    # above. What is left is the heading, the reads, and the edge pair they
    # share, which belongs to no one item, so it is charged to none.
    if node.kind == "check" and not node.checks:
        key = (kind, identifier + (f".{node.provision}" if node.provision else ""))
    elif node.hook:
        key = ("protocol", f"{identifier}.{node.hook}")
    elif node.kind == "procedure":
        key = ("pattern", f"{node.workflow}.{node.step}")
    if key is not None:
        text = "\n".join(writer.lines[first_line:]).strip("\n") + "\n"
        size = len(text.encode("utf-8")) - invariant_bytes
        bundle.binding_bytes[key] = bundle.binding_bytes.get(key, 0) + size


def node_command(node: Node) -> str:
    """The imperative a node's heading states, which is what an agent acts on.

    A prohibition's own sentence names the thing not to do, so as a heading it
    would read as an instruction to do it. It is rendered as the negative
    command it means, while the source's own sentence stays in the Prohibited
    field below.
    """
    return _executable_command(
        node.command, node.kind == "check" and node.prohibits
    )


def _executable_command(command: str, prohibits: bool) -> str:
    """Spell a raw destination command as the imperative an agent follows."""
    if prohibits:
        return wording.PROHIBITION_COMMAND.format(command=_lower_first(command))
    return command


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
        command = _executable_command(transition.command, transition.prohibits)
        return (
            f"{prefix} -> "
            f"{crossing_load(target_module, transition.target, command)}"
        )
    return f"{prefix} -> `{transition.target}`"


def crossing_load(module: str, label: str, command: str) -> str:
    """How every load names where it goes: the module, the node, and its command.

    The root's routing table and a module's crossing edge are the same act — an
    agent is told to read a file and continue at a node inside it — so the two
    are spelled here rather than separately. Two spellings would be two things
    for a reader to learn, and would let the planner measure an edge in a form
    the renderer never emits.
    """
    return f"`{module_reference(module)}:{label}` — {command}"


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
        for invariant in (*node.invariants, *node.checks):
            fields.append(
                (
                    wording.PROHIBITED if invariant.prohibits else wording.REQUIRED,
                    invariant.command,
                )
            )
            fields.append((wording.VERIFY, invariant.verify))
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
    bundle: RenderedBundle,
    page_constructs: dict[str, object],
    diagnostics: Diagnostics,
) -> dict[str, str]:
    """Generate auxiliary pages for explicit non-binding reference material.

    Reached patterns, heuristics, and guidance may expose auxiliary references or
    points outside the required execution graph. Profiles are handled separately
    as optional guidance with an index of their own, and name a reference the
    same way, so nothing a page links is read here to be inlined into it. Each
    referenced document is opened once for the name it states, because several
    pages may link one document and every link to it reads the same.
    """
    constructs = (*page_constructs.values(), *lowered.sources.profiles.values())
    titles = _reference_titles(
        lowered.skill.root,
        [
            target
            for construct in constructs
            for target in getattr(construct, "references", ())
        ],
        diagnostics,
    )
    pages: dict[str, str] = {}
    for relative, construct in sorted(page_constructs.items()):
        pages[relative] = _page_text(construct, relative, titles)
        for target in getattr(construct, "references", ()):
            bundle.links.append(LinkUse(target, relative))
    profile_pages = _profile_pages(lowered)
    for identifier, profile in sorted(lowered.sources.profiles.items()):
        relative = profile_pages[identifier]
        pages[relative] = _profile_text(profile, relative, titles)
        for target in profile.references:
            bundle.links.append(LinkUse(target, relative))
    pages.update(_profile_index(lowered, profile_pages))
    return pages


def _page_text(construct, current_page: str, titles: dict[str, str]) -> str:
    writer = _Writer()
    writer.line(f"# {construct.title}")
    writer.blank()
    summary = getattr(construct, "summary", "") or getattr(construct, "question", "")
    if summary:
        writer.blank()
        writer.line(summary)
    rationale = getattr(construct, "rationale", "")
    if rationale:
        writer.heading(2, wording.PAGE_RATIONALE)
        writer.line(rationale)
    points = getattr(construct, "points", ())
    if points:
        writer.heading(2, wording.PAGE_POINTS)
        writer.bullets(points)
    _further_reading(
        writer, getattr(construct, "references", ()), current_page, titles
    )
    return writer.text()


def _further_reading(
    writer: _Writer,
    references: tuple[str, ...],
    current_page: str,
    titles: dict[str, str],
) -> None:
    """Link the supplementary Markdown a construct names, without inlining it.

    Every construct that names a reference names it the same way — a path in the
    bundle, resolved from the page that carries the link — so one spelling
    serves the pattern, heuristic, and guidance pages and the profile pages
    alike. A page that inlined the file instead would leave the same document
    reading two ways depending on which construct pointed at it.

    The link is titled by the heading its target states, so an agent decides
    whether to open it from what the document is rather than from where the
    file sits; a document stating none is linked by its path, and reported.
    """
    if not references:
        return
    writer.heading(2, wording.PAGE_FURTHER)
    writer.bullets([
        f"[{titles.get(target, target)}]({_relative_link(target, current_page)})"
        for target in references
    ])


def _reference_titles(
    root: Path, targets: Iterable[str], diagnostics: Diagnostics
) -> dict[str, str]:
    """What each referenced document calls itself, for every link that opens it.

    A link titled by its own path tells an agent where a file sits and nothing
    about what it holds, so the document supplies the name and the link carries
    it, the way the profile index names a page by its title. A target the
    bundle does not ship is left to the check that already names it, and one
    escaping the skill is never opened at all. A shipped document with no
    heading keeps its path, because a title assembled from a filename would
    state what no author wrote; the author is told which file to name instead.
    """
    found: dict[str, str] = {}
    for target in sorted(set(targets)):
        path = root / target
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        title = _markdown_heading(path)
        if title:
            found[target] = title
        elif path.is_file():
            diagnostics.warning(
                f"{path}: the reference states no heading, so a link to it "
                "names only its path",
                "render.untitled-reference",
                path,
            )
    return found


def _markdown_heading(path: Path) -> str:
    """The first heading a document states, read as its own reader would read it.

    A file the compiler cannot decode is one it cannot name, and refusing the
    build there would stop it on a reference nobody has to read rather than on
    anything an author asked the compiler to check.
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    if lines and lines[0].strip() == FRONT_MATTER:
        closing = next(
            (
                index
                for index, line in enumerate(lines[1:], 1)
                if line.strip() == FRONT_MATTER
            ),
            len(lines),
        )
        lines = lines[closing + 1:]
    fenced = False
    previous = ""
    for line in lines:
        if CODE_FENCE.match(line):
            fenced = not fenced
            previous = ""
            continue
        if fenced:
            continue
        heading = ATX_HEADING.match(line)
        if heading and heading.group("text").strip():
            return heading.group("text").strip()
        if previous and SETEXT_UNDERLINE.match(line):
            return previous
        previous = line.strip()
    return ""
