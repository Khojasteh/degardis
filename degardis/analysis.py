"""Decide what goes on which page, and measure what that decision produced.

This is where authoring decisions are compiled away and runtime decisions are
kept. Two placements happen here, and both are decisions the author already made
implicitly but would otherwise have to carry out by hand on every page:

**Task closure.** A task declares the knowledge it needs; each unit declares what
it cannot be understood without. The closure of the two is compiled into the
task's own page, so a running agent reads one page rather than following a chain
of references that exists only because the author decomposed their material. The
decomposition is for whoever maintains the source. It is not a route.

**Principle placement.** The skill and each task declare the principles they
use. A principle's optional activation states when its guidance applies, and
each owner renders that same condition beside its link. Principle files never
name tasks, so neither direction forms a cycle.

What is deliberately *not* decided here is which facets apply. That depends on
the situation in front of the agent, which the compiler cannot see, so the
generated bundle keeps that lookup and keeps it as one index.

Nothing in this module reads or rewrites a body's prose. Placement moves authored
material; it never edits it.

The plan objects are separate from the source objects on purpose. A `Task` is
what its author wrote; a `TaskPlan` is what this compiler decided to do with it.
Keeping them apart is what stops a placement concern from turning into a field an
author has to fill in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .bundlepaths import task_path
from .sources import (
    CONSTRAINT_KIND,
    KNOWLEDGE_KINDS,
    Knowledge,
    Principle,
    Facet,
    SourceSet,
    Task,
)
@dataclass(frozen=True)
class TaskPlan:
    """One task, everything compiled into its page, and where the page goes."""

    task: Task
    page: str
    closure: tuple[Knowledge, ...] = ()
    direct: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    principles: tuple[Principle, ...] = ()

    @property
    def id(self) -> str:
        return self.task.id

    def of_kind(self, kind: str) -> tuple[Knowledge, ...]:
        """The units in one rendered subsection, preserving author order."""
        return tuple(unit for unit in self.closure if unit.kind == kind)

    @property
    def carries_material(self) -> bool:
        """Whether the page says anything beyond the goal it opens with.

        A task with no body, no knowledge, and no guide compiles to a page
        carrying its goal and nothing else, which the router entry that led
        there could have carried instead. That is a load an agent pays for one
        sentence, and it usually means the task was declared before the material
        that justifies it was written.
        """
        return bool(
            self.task.body.strip()
            or self.closure
            or self.task.guides
            or self.principles
        )


@dataclass(frozen=True)
class Plan:
    """One skill's complete placement: its tasks, its principles, its facets."""

    tasks: tuple[TaskPlan, ...] = ()
    principles: tuple[Principle, ...] = ()
    root_principles: tuple[Principle, ...] = ()
    facets: tuple[Facet, ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()
    unresolved: tuple[tuple[str, str], ...] = ()

    @property
    def categorized(self) -> bool:
        """Whether the facet index groups its rows.

        One category over every facet is not a grouping: it would add a
        heading that separates nothing. Two or more is, because then the
        category is what tells a reader which rows to read.
        """
        return len({item.category for item in self.facets if item.category}) > 1

    def task(self, identifier: str) -> TaskPlan | None:
        return next((item for item in self.tasks if item.id == identifier), None)


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
    ordered: list[Knowledge] = []
    emitted: set[str] = set()
    direct = list(task.knowledge)
    required: list[str] = []
    unresolved: list[tuple[str, str]] = []
    cycles: list[tuple[str, ...]] = []

    # Establish direct order first. A missing direct reference is still recorded
    # in place but has no unit to put into the closure.
    for name in direct:
        unit = sources.knowledge.get(name)
        if unit is None:
            unresolved.append((f"task:{task.id}", name))
            continue
        if name not in emitted:
            emitted.add(name)
            ordered.append(unit)

    visited_edges: set[tuple[str, str]] = set()

    def requirements(unit: Knowledge, trail: tuple[str, ...]) -> None:
        for name in unit.requires:
            edge = (unit.id, name)
            if name in trail:
                cycle = (*trail[trail.index(name) :], name)
                cycles.append(cycle)
                continue
            target = sources.knowledge.get(name)
            if target is None:
                unresolved.append((unit.id, name))
                continue
            if name not in emitted:
                emitted.add(name)
                ordered.append(target)
                required.append(name)
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            requirements(target, (*trail, name))

    for name in direct:
        unit = sources.knowledge.get(name)
        if unit is not None:
            requirements(unit, (name,))

    return _Closure(
        ordered=tuple(
            unit for kind in KNOWLEDGE_KINDS for unit in ordered if unit.kind == kind
        ),
        direct=tuple(direct),
        required=tuple(required),
        unresolved=tuple(unresolved),
        cycles=tuple(cycles),
    )


def _place_principles(
    references: tuple[str, ...], sources: SourceSet
) -> tuple[Principle, ...]:
    """Resolve one owner's principle references without changing their order."""
    return tuple(
        sources.principles[item]
        for item in references
        if item in sources.principles
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
    """Compile each task's knowledge and principle links from their owners."""
    root_principles = _place_principles(principles, sources)
    plans: list[TaskPlan] = []
    unresolved: list[tuple[str, str]] = []
    cycles: list[tuple[str, ...]] = []
    for identifier in _route_order(sources, tasks):
        task = sources.tasks[identifier]
        closure = _resolve_closure(task, sources)
        unresolved.extend(closure.unresolved)
        cycles.extend(closure.cycles)
        plans.append(
            TaskPlan(
                task=task,
                page=task_path(identifier),
                closure=closure.ordered,
                direct=closure.direct,
                required=closure.required,
                principles=_place_principles(task.principles, sources),
            )
        )
    return Plan(
        tasks=tuple(plans),
        principles=tuple(
            dict.fromkeys(
                item
                for item in (
                    *root_principles,
                    *(item for plan in plans for item in plan.principles),
                )
            )
        ),
        root_principles=root_principles,
        facets=tuple(item for _, item in sorted(sources.facets.items())),
        cycles=tuple(dict.fromkeys(cycles)),
        unresolved=tuple(dict.fromkeys(unresolved)),
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
    mean choosing which author's words survive, and that is a judgement about
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
    reached = {
        unit.key for item in plan.tasks for unit in item.closure
    }
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
    reached = {unit.key: unit for item in plan.tasks for unit in item.closure}
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
