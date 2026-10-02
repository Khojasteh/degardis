"""Decide what goes on which page, and measure what that decision produced.

This is where authoring decisions are compiled away and runtime decisions are
kept. Two placements happen here, and both are decisions the author already made
implicitly but would otherwise have to carry out by hand on every page:

**Task closure.** A task declares the knowledge it needs; each unit declares what
it cannot be understood without. The closure of the two is compiled into the
task's own page, so a running agent reads one page rather than following a chain
of references that exists only because the author decomposed their material. The
decomposition is for whoever maintains the source. It is not a route.

**Principle and guide placement.** The skill declares the principles it holds
across every task, and each task and facet the guides it opens. A principle's or
guide's optional `applicability` list states when its guidance applies, and
each owner renders those same conditions beside its link. A guide may declare
the guides it cannot be understood without, and it owns those itself: its own
page lists them, so a reader meets them on opening the guide that needs them,
and judges their conditions there, rather than on every page that leads to it.
Principle files never name tasks, so neither direction forms a cycle.

A knowledge unit names no owner, because it is written once for every task that
carries it. When its text references a guide, every task page carrying the unit
owns that guide and links it where it links its other guides; the unit's text
names it rather than linking it. The reader then meets every separately loaded
page it may need in the one list a page keeps for them.

A task's, a facet's, and a guide's own text do the same for guides: a guide the
body references joins the guides its page links, after the ones it names or
requires. None of these texts owns a principle, so a principle one references
is left to the skill, the one owner that places it.

What is deliberately *not* decided here is which facets apply. That depends on
the situation in front of the agent, which the compiler cannot see, so the
generated bundle keeps that lookup and keeps it as one index.

Nothing in this module rewrites a body's prose, and the only thing it reads from
one is the inline references of a task, a knowledge unit, a facet, or a guide.
Placement moves authored material; it never edits it.

The plan objects are separate from the source objects on purpose. A `Task` is
what its author wrote; a `TaskPlan` is what this compiler decided to do with it.
Keeping them apart is what stops a placement concern from turning into a field an
author has to fill in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .bundlepaths import task_path
from .markdown import inline_reference_targets
from .sources import (
    CONSTRAINT_KIND,
    KNOWLEDGE_KINDS,
    Guide,
    Knowledge,
    Principle,
    Facet,
    SourceSet,
    Task,
)


@dataclass(frozen=True)
class TaskPlan:
    """One task, everything compiled into its page, and where the page goes.

    `guides` is what the page links: the task's own declarations in authored
    order, then what its body and its knowledge reference, in the order the
    page carries them. What those guides require is on their own pages.
    """

    task: Task
    page: str
    closure: tuple[Knowledge, ...] = ()
    direct: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    guides: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.task.id

    def of_kind(self, kind: str) -> tuple[Knowledge, ...]:
        """The units in one rendered subsection, preserving author order."""
        return tuple(unit for unit in self.closure if unit.kind == kind)

    @property
    def carries_material(self) -> bool:
        """Whether the page says anything beyond the goal it opens with.

        A task with no body, no knowledge, no guide, and no hand-off compiles
        to a page carrying its goal and nothing else, which the router entry
        that led there could have carried instead. That is a load an agent pays
        for one sentence, and it usually means the task was declared before the
        material that justifies it was written.
        """
        return bool(
            self.task.body.strip() or self.closure or self.guides or self.task.handoffs
        )


@dataclass(frozen=True)
class FacetPlan:
    """One facet, and the guides its page links.

    `guides` is the facet's own declarations in authored order, then the guides
    its body references, in the order its text first references them.
    """

    facet: Facet
    guides: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.facet.id


@dataclass(frozen=True)
class GuidePlan:
    """One guide, and the guides its page links.

    `guides` is the guide's `requires` in authored order, then the guides its
    body references, in the order its text first references them. A guide is
    never on its own list.
    """

    guide: Guide
    guides: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.guide.id


@dataclass(frozen=True)
class Plan:
    """One skill's complete placement: its tasks, principles, facets, and guides.

    `principles` is what the skill names, in its order, and the only principle
    placement there is. `guides` holds every selected guide's own list,
    whether or not anything reaches the guide. `cycles` and `unresolved` are
    the knowledge requirements a task closure could not follow; `guide_cycles` and
    `guide_unresolved` are the same for guide requirements, read from every
    selected guide rather than from the ones an owner reaches, because a guide's
    requirements are a fact about its own file.
    """

    tasks: tuple[TaskPlan, ...] = ()
    principles: tuple[Principle, ...] = ()
    facets: tuple[FacetPlan, ...] = ()
    guides: tuple[GuidePlan, ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()
    unresolved: tuple[tuple[str, str], ...] = ()
    guide_cycles: tuple[tuple[str, ...], ...] = ()
    guide_unresolved: tuple[tuple[str, str], ...] = ()

    @property
    def categorized(self) -> bool:
        """Whether the facet index groups its rows.

        One category over every facet is not a grouping: it would add a
        heading that separates nothing. Two or more is, because then the
        category is what tells a reader which rows to read.
        """
        return len(
            {item.facet.category for item in self.facets if item.facet.category}
        ) > 1

    @property
    def reached(self) -> dict[str, Knowledge]:
        """Every knowledge unit some task page carries, keyed by id, once each.

        This is what the bundle ships of the skill's knowledge. A unit outside it
        is an orphan, and each unit in it is paid for once per page that carries
        it, so both measures read this rather than deciding reach again.
        """
        return {unit.key: unit for item in self.tasks for unit in item.closure}

    @property
    def reached_guides(self) -> tuple[str, ...]:
        """Every selected guide a reader can be sent to, once each.

        A reader starts from the lists on task and facet pages and goes on to
        the list on each guide page it opens, so a guide is reached when some
        chain of those lists names it. A guide reached by none is weight no
        reader can use, whatever the guides nobody opens declare.
        """
        lists = {item.id: item.guides for item in self.guides}
        pending = [name for item in (*self.tasks, *self.facets) for name in item.guides]
        reached: dict[str, None] = {}
        while pending:
            name = pending.pop(0)
            if name in reached or name not in lists:
                continue
            reached[name] = None
            pending.extend(lists[name])
        return tuple(reached)

    def task(self, identifier: str) -> TaskPlan | None:
        return next((item for item in self.tasks if item.id == identifier), None)

    def guide(self, identifier: str) -> GuidePlan | None:
        return next((item for item in self.guides if item.id == identifier), None)


@dataclass(frozen=True)
class _Walk:
    """What following one namespace's `requires` from a set of roots produced."""

    reached: tuple[str, ...] = ()
    unresolved: tuple[tuple[str, str], ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()


def _walk_requirements(
    roots: Iterable[str], requires: Mapping[str, tuple[str, ...]]
) -> _Walk:
    """Follow `requires` depth-first from each root, in the order the roots come.

    `requires` holds every selected construct of one namespace, so a name it
    does not hold is a requirement no selected file answers. `reached` is what
    the walk added beyond the roots, in the order the requirement lists first
    introduce it, which is the order a knowledge closure takes. Guide
    requirements are walked only for their findings, since each guide's page
    lists its own. A requirement back onto the walk's own trail is a cycle,
    recorded and not followed, and an edge already followed is not followed
    again, so the walk ends however the requirements loop.
    """
    order = tuple(roots)
    emitted: set[str] = set(order)
    reached: list[str] = []
    unresolved: list[tuple[str, str]] = []
    cycles: list[tuple[str, ...]] = []
    visited_edges: set[tuple[str, str]] = set()

    def follow(name: str, trail: tuple[str, ...]) -> None:
        for target in requires[name]:
            if target in trail:
                cycles.append(_canonical_cycle(trail[trail.index(target) :]))
                continue
            if target not in requires:
                unresolved.append((name, target))
                continue
            if target not in emitted:
                emitted.add(target)
                reached.append(target)
            edge = (name, target)
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            follow(target, (*trail, target))

    for name in order:
        follow(name, (name,))
    return _Walk(
        reached=tuple(reached), unresolved=tuple(unresolved), cycles=tuple(cycles)
    )


@dataclass(frozen=True)
class _Closure:
    """What resolving one task's knowledge produced, named rather than positional.

    The four parts travel together because they come out of one traversal and
    are consumed by one caller, and naming them is what keeps a list of missing
    references from being read as the list of cycles.
    """

    ordered: tuple[Knowledge, ...] = ()
    direct: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    unresolved: tuple[tuple[str, str], ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()


def _resolve_closure(task: Task, sources: SourceSet) -> _Closure:
    """Resolve one task's closure without using dependencies as presentation order.

    The task's own `knowledge` list is the primary authored order. Units reached
    only through `requires` follow the directly selected units, in the order the
    requirement lists first introduce them. Rendering then groups that stable
    sequence by knowledge kind. A dependency therefore changes inclusion, never
    silently rearranges two units the task author explicitly ordered.

    Missing references and cycles are returned rather than reported here; this
    module decides placement, while the validation layer owns the checks.
    """
    direct = tuple(task.knowledge)
    # A missing direct reference is recorded against the task, and has no unit
    # to put into the closure or to walk from.
    unresolved = [
        (f"task:{task.id}", name) for name in direct if name not in sources.knowledge
    ]
    roots = tuple(dict.fromkeys(name for name in direct if name in sources.knowledge))
    walk = _walk_requirements(
        roots, {name: unit.requires for name, unit in sources.knowledge.items()}
    )
    ordered = [sources.knowledge[name] for name in (*roots, *walk.reached)]
    return _Closure(
        ordered=tuple(
            unit for kind in KNOWLEDGE_KINDS for unit in ordered if unit.kind == kind
        ),
        direct=direct,
        required=walk.reached,
        unresolved=(*unresolved, *walk.unresolved),
        cycles=walk.cycles,
    )


def _canonical_cycle(members: tuple[str, ...]) -> tuple[str, ...]:
    """One cycle written from its smallest id, closed back on itself.

    A walk enters a cycle at whichever unit it reaches first, so the same loop
    comes out as `a -> b -> a` from one task and `b -> a -> b` from another.
    Rotating each to one starting point makes them one finding, reported
    against one file, because they are one repair.
    """
    start = members.index(min(members))
    rotated = (*members[start:], *members[:start])
    return (*rotated, rotated[0])


def _place_principles(
    references: tuple[str, ...], sources: SourceSet
) -> tuple[Principle, ...]:
    """Resolve one owner's principle references without changing their order."""
    return tuple(
        sources.principles[item]
        for item in references
        if item in sources.principles
    )


def _body_references(bodies: Iterable[str], kind: str) -> tuple[str, ...]:
    """Every target of one kind the bodies reference, in reading order, once.

    A target no selected file answers is returned like any other. Placement
    skips it, and the renderer reports the reference where it sits.
    """
    return tuple(
        dict.fromkeys(
            target
            for body in bodies
            for found, target in inline_reference_targets(body)
            if found == kind
        )
    )


def _place_guides(owned: Iterable[str]) -> tuple[str, ...]:
    """One owner's guides in the order it states them, each once.

    A guide named more than once keeps its first place. What a listed guide
    requires is not added: that guide owns it, and its own page lists it. A
    name no selected guide answers keeps its place; the renderer skips it and
    the checks report it against the owner that named it.
    """
    return tuple(dict.fromkeys(owned))


def _place_facet(facet: Facet, sources: SourceSet) -> FacetPlan:
    """Link a facet's declared guides, then the selected guides its text references.

    A guide named both ways keeps its declared place, and one referenced more
    than once is linked once, where its text first references it.
    """
    referenced = tuple(
        name
        for name in _body_references((facet.body,), "guide")
        if name in sources.guides
    )
    return FacetPlan(facet=facet, guides=_place_guides((*facet.guides, *referenced)))


def _place_guide(guide: Guide, sources: SourceSet) -> GuidePlan:
    """Link a guide's requirements, then the selected guides its text references.

    The requirements are the guide's declarations, so they come first, as a
    task's or a facet's `guides` do. The guide itself is left off: requiring
    itself is a cycle and referencing itself is a finding, each reported by
    the checks, and neither is a further page for its reader to open.
    """
    referenced = tuple(
        name
        for name in _body_references((guide.body,), "guide")
        if name in sources.guides
    )
    return GuidePlan(
        guide=guide,
        guides=tuple(
            name
            for name in _place_guides((*guide.requires, *referenced))
            if name != guide.id
        ),
    )


def _route_order(
    sources: SourceSet, declared: tuple[str, ...]
) -> tuple[str, ...]:
    """The order the router lists tasks in: the manifest's, then the rest by id.

    The manifest is the whole of the routing order, and a task it does not name
    is reported by `manifest.unrouted-task`. That finding is collected rather
    than raised, so the tail keeps every task reachable on a page that is still
    being compiled while the error is on its way to the reader. It is not a
    second ordering rule an author can rely on: a source that reaches a clean
    build has named them all, and the tail is empty.
    """
    named = tuple(
        name for name in dict.fromkeys(declared) if name in sources.tasks
    )
    rest = tuple(name for name in sorted(sources.tasks) if name not in set(named))
    return named + rest


def plan_skill(
    sources: SourceSet,
    principles: tuple[str, ...] = (),
    tasks: tuple[str, ...] = (),
) -> Plan:
    """Compile each task's and facet's links from their owners' declarations."""
    plans: list[TaskPlan] = []
    unresolved: list[tuple[str, str]] = []
    cycles: list[tuple[str, ...]] = []
    for identifier in _route_order(sources, tasks):
        task = sources.tasks[identifier]
        closure = _resolve_closure(task, sources)
        unresolved.extend(closure.unresolved)
        cycles.extend(closure.cycles)
        bodies = (task.body, *(unit.body for unit in closure.ordered))
        referenced_guides = tuple(
            name
            for name in _body_references(bodies, "guide")
            if name in sources.guides
        )
        plans.append(
            TaskPlan(
                task=task,
                page=task_path(identifier),
                closure=closure.ordered,
                direct=closure.direct,
                required=closure.required,
                guides=_place_guides((*task.guides, *referenced_guides)),
            )
        )
    guides = _walk_requirements(
        sorted(sources.guides),
        {name: guide.requires for name, guide in sources.guides.items()},
    )
    return Plan(
        tasks=tuple(plans),
        principles=_place_principles(principles, sources),
        facets=tuple(
            _place_facet(item, sources) for _, item in sorted(sources.facets.items())
        ),
        guides=tuple(
            _place_guide(item, sources) for _, item in sorted(sources.guides.items())
        ),
        cycles=tuple(dict.fromkeys(cycles)),
        unresolved=tuple(dict.fromkeys(unresolved)),
        guide_cycles=tuple(dict.fromkeys(guides.cycles)),
        guide_unresolved=tuple(dict.fromkeys(guides.unresolved)),
    )


# --------------------------------------------------------------------------
# Quality measures
# --------------------------------------------------------------------------

# Words that carry no subject, so two units that share only these share nothing.
# The list is short on purpose: a longer one starts deciding which domain terms
# matter, and that is not a decision a similarity measure gets to make.
STOP_WORDS = frozenset(
    """a an and are as at be but by for from has have if in into is it its of on or
    that the their then there these this to was were when which while with""".split()
)
WORD = re.compile(r"[a-z0-9]+")

# Two units this similar are almost certainly the same material written twice.
# It is a warning and never an error: the compiler cannot tell deliberate
# repetition from accidental duplication, and only the author can.
NEAR_DUPLICATE_SIMILARITY = 0.8


def _shingles(text: str) -> frozenset[tuple[str, str, str]]:
    """One body as its set of three-word runs, lowercased and stripped of noise.

    Runs rather than single words, because two documents about the same subject
    share most of their vocabulary and almost none of their phrasing. Sharing
    phrasing is what duplication actually looks like.
    """
    words = [word for word in WORD.findall(text.lower()) if word not in STOP_WORDS]
    return frozenset(
        (words[index], words[index + 1], words[index + 2])
        for index in range(len(words) - 2)
    )


def near_duplicates(units: Iterable[Knowledge]) -> list[tuple[str, str, float]]:
    """Every pair of knowledge units whose text is substantially the same.

    Reported so an author can decide; never acted on. Merging two units would
    mean choosing which author's words survive, and that is a judgment about
    expertise rather than about structure.
    """
    measured = [(unit, _shingles(unit.body)) for unit in units]
    found: list[tuple[str, str, float]] = []
    for index, (left, left_shingles) in enumerate(measured):
        for right, right_shingles in measured[index + 1 :]:
            if not left_shingles or not right_shingles:
                continue
            union = len(left_shingles | right_shingles)
            similarity = len(left_shingles & right_shingles) / union if union else 0.0
            if similarity >= NEAR_DUPLICATE_SIMILARITY:
                found.append((left.key, right.key, round(similarity, 3)))
    return found


def orphans(plan: Plan, sources: SourceSet) -> list[str]:
    """Every knowledge unit no task's closure reaches, so no bundle page carries it.

    An orphan is not an error. It is material the skill ships nothing of, which
    is either a task that has not been written yet or a unit that should be
    deleted, and the author is the only one who knows which.
    """
    reached = plan.reached
    return [key for key in sorted(sources.knowledge) if key not in reached]


@dataclass(frozen=True)
class Quality:
    """What the placement produced, in the terms an author decides changes by."""

    tasks: int = 0
    knowledge_units: int = 0
    orphan_knowledge: tuple[str, ...] = ()
    near_duplicates: tuple[tuple[str, str, float], ...] = ()
    constraint_ratio: float = 0.0
    principles: int = 0
    duplicated_bytes: int = 0
    unique_bytes: int = 0


def measure(plan: Plan, sources: SourceSet) -> Quality:
    """Measure the compiled result, for an author deciding what to change.

    Every number here informs; none of them authorizes the compiler to rewrite
    anything. A page that is too long or a unit that is duplicated is a fact
    about the source, and the repair is a decision about expertise that belongs
    to whoever wrote it.
    """
    units = list(sources.knowledge.values())
    unique_bytes = sum(len(unit.body.encode("utf-8")) for unit in units)
    compiled_bytes = sum(
        len(unit.body.encode("utf-8"))
        for item in plan.tasks
        for unit in item.closure
    )
    reached = plan.reached
    constraints = sum(
        1 for unit in reached.values() if unit.kind == CONSTRAINT_KIND
    )
    return Quality(
        tasks=len(plan.tasks),
        knowledge_units=len(units),
        orphan_knowledge=tuple(orphans(plan, sources)),
        near_duplicates=tuple(near_duplicates(units)),
        constraint_ratio=round(constraints / len(reached), 3) if reached else 0.0,
        principles=len(plan.principles),
        duplicated_bytes=max(
            compiled_bytes - sum(len(unit.body.encode("utf-8")) for unit in reached.values()),
            0,
        ),
        unique_bytes=unique_bytes,
    )
