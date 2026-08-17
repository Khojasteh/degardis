"""The source workflow graph: what execution is possible, and what values exist.

Everything the compiler can say about a workflow before any policy, rule, or
protocol is lowered into it is decided here: which steps a run can reach, that
every reachable path ends in a return, that every closed choice is exhaustive,
which values are available at each step, and which gate decisions every path to
a step has already made.

Format 2 workflows are acyclic. That is what lets one pass in topological order
answer all four questions exactly rather than approximately: definite assignment
is the intersection over a step's predecessors, and gate dominance is the
intersection of the gates each predecessor was itself dominated by. A backward
edge would turn both into fixed-point problems whose answers a generated node
could only state conservatively, so the compiler rejects one instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dexpr import (
    ExpressionError,
    Reference,
    TypeEnvironment,
    ValueType,
    check_binding,
    check_expression,
    parse_reference,
)
from .model import BLOCKED_OUTCOME, Diagnostics
from .sources import Outcome, SourceSet, Step, Workflow


# One available value, named by the namespace it is read through and the root
# name under it: ("result", "inspection") is read as `result.inspection`.
ValueKey = tuple[str, str]


@dataclass
class WorkflowGraph:
    """One workflow's reachable execution, with the facts every later pass needs."""

    workflow: Workflow
    order: tuple[str, ...] = ()
    reachable: frozenset[str] = frozenset()
    predecessors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    types: dict[ValueKey, ValueType] = field(default_factory=dict)
    available: dict[str, frozenset[ValueKey]] = field(default_factory=dict)
    produced: dict[str, frozenset[ValueKey]] = field(default_factory=dict)
    edge_produced: dict[tuple[str, str], frozenset[ValueKey]] = field(default_factory=dict)
    gates: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)
    usable: bool = True

    def environment(
        self,
        records: dict[str, dict[str, ValueType]],
        step: str,
        *,
        after: bool = False,
        state: dict[str, ValueType] | None = None,
    ) -> TypeEnvironment:
        """The values an expression may read at one point in this workflow.

        `after` moves the boundary past the step's own production, which is where
        an `after` provision and an `after` hook are evaluated. `state` adds one
        protocol frame's declared data, which only that frame's hooks may read.
        """
        defined = set(self.available.get(step, frozenset()))
        if after:
            defined |= set(self.produced.get(step, frozenset()))
        values = dict(self.types)
        if state:
            for name, declared in state.items():
                values[("state", name)] = declared
                defined.add(("state", name))
        return TypeEnvironment(values=values, records=records, defined=defined)


def build_graph(
    workflow: Workflow,
    sources: SourceSet,
    diagnostics: Diagnostics,
) -> WorkflowGraph:
    """Check one workflow's control flow and value flow, and report every problem."""
    graph = WorkflowGraph(workflow=workflow)
    path = workflow.path

    def error(message: str, code: str) -> None:
        diagnostics.error(f"{path}: {message}", code, path)
        graph.usable = False

    steps = {step.id: step for step in workflow.steps}
    _check_reserved_outcomes(workflow, error)
    _check_edges(workflow, steps, error)
    if not graph.usable:
        return graph

    graph.reachable = _reachable(workflow, steps)
    unreachable = sorted(set(steps) - set(graph.reachable))
    if unreachable:
        error(
            f"steps {', '.join(unreachable)} cannot be reached from entry "
            f"{workflow.entry}",
            "workflow.unreachable",
        )
    order = _topological_order(workflow, steps, graph.reachable, error)
    if order is None:
        return graph
    graph.order = order
    graph.predecessors = _predecessors(workflow, steps, graph.reachable)
    for identifier in graph.reachable:
        step = steps[identifier]
        if step.form != "return" and not step.successors:
            error(
                f"steps.{identifier}: a {step.form} step continues somewhere; "
                "only a return ends a workflow",
                "workflow.invalid-edge",
            )
    _check_calls(workflow, steps, sources, graph, error)
    _check_returns(workflow, steps, sources, graph, error)
    _declare_values(workflow, steps, sources, graph, error)
    _flow(workflow, steps, graph)
    _check_conditions(workflow, steps, sources, graph, diagnostics)
    _check_supplied_values(workflow, steps, sources, graph, diagnostics)
    return graph


def _check_reserved_outcomes(workflow: Workflow, error) -> None:
    """Keep the compiler's own outcome out of the source's declarations.

    Every workflow returns `blocked` when a binding check cannot be satisfied,
    and that return is generated. A source declaring the same name would have
    two meanings for one outcome, and a call mapping it would claim to handle a
    transition the compiler owns.
    """
    if workflow.outcome(BLOCKED_OUTCOME) is not None:
        error(
            f"outcomes declares {BLOCKED_OUTCOME}, which the compiler owns: "
            "every workflow returns it when a binding check fails",
            "workflow.reserved-outcome",
        )
    for step in workflow.steps:
        if step.form == "use" and any(
            item.id == BLOCKED_OUTCOME for item in step.on
        ):
            error(
                f"steps.{step.id}.on maps {BLOCKED_OUTCOME}, which the compiler "
                "owns: a called workflow that blocks blocks this one too",
                "workflow.reserved-outcome",
            )
        if step.form == "return" and step.outcome == BLOCKED_OUTCOME:
            error(
                f"steps.{step.id}.return names {BLOCKED_OUTCOME}, which the "
                "compiler owns; declare an outcome of this workflow's own",
                "workflow.reserved-outcome",
            )


def _check_edges(workflow: Workflow, steps: dict[str, Step], error) -> None:
    identifiers = [step.id for step in workflow.steps]
    repeated = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if repeated:
        error(f"steps declares {', '.join(repeated)} more than once", "workflow.invalid-edge")
    if workflow.entry and workflow.entry not in steps:
        error(
            f"entry names {workflow.entry}, which is not a step of this workflow",
            "workflow.invalid-edge",
        )
    for step in workflow.steps:
        for target in step.successors:
            if target not in steps:
                error(
                    f"steps.{step.id} continues at {target}, which is not a step "
                    "of this workflow",
                    "workflow.invalid-edge",
                )


def _reachable(workflow: Workflow, steps: dict[str, Step]) -> frozenset[str]:
    if workflow.entry not in steps:
        return frozenset()
    seen: set[str] = set()
    pending = [workflow.entry]
    while pending:
        identifier = pending.pop()
        if identifier in seen:
            continue
        seen.add(identifier)
        pending.extend(
            target for target in steps[identifier].successors if target in steps
        )
    return frozenset(seen)


def _topological_order(
    workflow: Workflow,
    steps: dict[str, Step],
    reachable: frozenset[str],
    error,
) -> tuple[str, ...] | None:
    """Order the reachable steps so every edge points forward, or report a cycle.

    Source order is followed wherever the edges allow it, so a generated document
    reads in the order its author wrote and a rebuild is byte-identical.
    """
    source_order = [step.id for step in workflow.steps if step.id in reachable]
    incoming = dict.fromkeys(source_order, 0)
    for identifier in source_order:
        for target in steps[identifier].successors:
            if target in incoming:
                incoming[target] += 1
    ordered: list[str] = []
    ready = [identifier for identifier in source_order if incoming[identifier] == 0]
    while ready:
        # Source order among the steps whose predecessors are all placed.
        ready.sort(key=source_order.index)
        identifier = ready.pop(0)
        ordered.append(identifier)
        for target in steps[identifier].successors:
            if target not in incoming:
                continue
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if len(ordered) != len(source_order):
        remaining = sorted(set(source_order) - set(ordered))
        error(
            f"steps {', '.join(remaining)} form a cycle; Format 2 workflows run "
            "forward, so a repeated stage is a step of its own",
            "workflow.invalid-edge",
        )
        return None
    return tuple(ordered)


def _predecessors(
    workflow: Workflow, steps: dict[str, Step], reachable: frozenset[str]
) -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {identifier: [] for identifier in reachable}
    for identifier in sorted(reachable):
        for target in steps[identifier].successors:
            if target in found and identifier not in found[target]:
                found[target].append(identifier)
    return {key: tuple(value) for key, value in found.items()}


def _check_calls(
    workflow: Workflow,
    steps: dict[str, Step],
    sources: SourceSet,
    graph: WorkflowGraph,
    error,
) -> None:
    for identifier in graph.reachable:
        step = steps[identifier]
        if step.form != "use":
            continue
        callee = sources.workflows.get(step.call)
        if callee is None:
            error(
                f"steps.{identifier}.use names workflow {step.call}, which this "
                "skill does not select",
                "workflow.invalid-edge",
            )
            continue
        declared = {outcome.id for outcome in callee.outcomes}
        mapped = {item.id for item in step.on}
        missing = sorted(declared - mapped)
        if missing:
            error(
                f"steps.{identifier}.on leaves {', '.join(missing)} unhandled; "
                f"workflow {step.call} can return it",
                "workflow.unhandled-outcome",
            )
        extra = sorted(mapped - declared)
        if extra:
            error(
                f"steps.{identifier}.on maps {', '.join(extra)}, which workflow "
                f"{step.call} does not declare",
                "workflow.unhandled-outcome",
            )


def _check_returns(
    workflow: Workflow,
    steps: dict[str, Step],
    sources: SourceSet,
    graph: WorkflowGraph,
    error,
) -> None:
    returned: set[str] = set()
    for identifier in graph.order:
        step = steps[identifier]
        if step.form != "return":
            continue
        outcome = workflow.outcome(step.outcome)
        if outcome is None:
            error(
                f"steps.{identifier}.return names outcome {step.outcome}, which "
                "this workflow does not declare",
                "workflow.unhandled-outcome",
            )
            continue
        returned.add(outcome.id)
        _check_return_values(workflow, step, outcome, sources, error)
    unreturned = sorted(
        {outcome.id for outcome in workflow.outcomes if outcome.id not in returned}
    )
    if unreturned:
        error(
            f"outcomes {', '.join(unreturned)} are declared and never returned, "
            "so a caller must handle a transition that cannot happen",
            "workflow.unhandled-outcome",
        )


def _check_return_values(
    workflow: Workflow, step: Step, outcome: Outcome, sources: SourceSet, error
) -> None:
    supplied = {name for name, _ in step.supplied}
    if not outcome.record:
        if supplied:
            error(
                f"steps.{step.id}.return supplies {', '.join(sorted(supplied))}, "
                f"and outcome {outcome.id} carries no record",
                "value.unknown-binding",
            )
        return
    record = sources.records.get(outcome.record)
    if record is None:
        # Already reported against the outcome that names it, as an unknown
        # reference. Reporting it again here would give one missing record two
        # codes and send the author looking for a second repair.
        return
    declared = set(record.types())
    missing = sorted(declared - supplied)
    if missing:
        error(
            f"steps.{step.id}.return leaves {', '.join(missing)} unsupplied; "
            f"record {record.id} declares it",
            "value.missing-binding",
        )
    extra = sorted(supplied - declared)
    if extra:
        error(
            f"steps.{step.id}.return supplies {', '.join(extra)}, which record "
            f"{record.id} does not declare",
            "value.unknown-binding",
        )


def _declare_values(
    workflow: Workflow,
    steps: dict[str, Step],
    sources: SourceSet,
    graph: WorkflowGraph,
    error,
) -> None:
    """Collect every value this workflow can hold, and reject two meanings for one."""
    types: dict[ValueKey, ValueType] = {}

    def declare(key: ValueKey, declared: ValueType, where: str) -> None:
        existing = types.get(key)
        if existing is not None and existing != declared:
            error(
                f"{where} declares {key[0]}.{key[1]} as a {declared.render()}, "
                f"and it is already a {existing.render()}",
                "workflow.conflicting-value",
            )
            return
        types[key] = declared

    for name, declared in workflow.inputs:
        declare(("input", name), declared, f"inputs.{name}")
    for identifier in graph.order:
        step = steps[identifier]
        if step.form == "action":
            for name, declared in step.produces:
                declare(("result", name), declared, f"steps.{identifier}.produces")
        elif step.form == "decide":
            declare(
                ("decision", identifier),
                ValueType("enum", values=tuple(option.id for option in step.options)),
                f"steps.{identifier}",
            )
        elif step.form == "gate":
            declare(
                ("gate", identifier),
                ValueType("enum", values=tuple(option.id for option in step.options)),
                f"steps.{identifier}",
            )
        elif step.form == "use":
            declare(
                ("call", identifier),
                ValueType("enum", values=tuple(item.id for item in step.on)),
                f"steps.{identifier}",
            )
            callee = sources.workflows.get(step.call)
            if callee is not None:
                for item in step.on:
                    if not item.capture:
                        continue
                    outcome = callee.outcome(item.id)
                    if outcome is None or not outcome.record:
                        error(
                            f"steps.{identifier}.on.{item.id}.as captures a payload, "
                            f"but workflow {step.call} outcome {item.id} carries no record",
                            "value.invalid-capture",
                        )
                        continue
                    declare(
                        ("result", item.capture),
                        ValueType("record", record=outcome.record),
                        f"steps.{identifier}.on.{item.id}.as",
                    )
    graph.types = types


def _flow(workflow: Workflow, steps: dict[str, Step], graph: WorkflowGraph) -> None:
    """Definite assignment and gate dominance, in one forward pass over the DAG."""
    produced: dict[str, frozenset[ValueKey]] = {}
    for identifier in graph.order:
        step = steps[identifier]
        if step.form == "action":
            produced[identifier] = frozenset(
                ("result", name) for name, _ in step.produces
            )
        elif step.form == "decide":
            produced[identifier] = frozenset({("decision", identifier)})
        elif step.form == "gate":
            produced[identifier] = frozenset({("gate", identifier)})
        elif step.form == "use":
            produced[identifier] = frozenset({("call", identifier)})
        else:
            produced[identifier] = frozenset()
    graph.produced = produced
    edge_produced: dict[tuple[str, str], frozenset[ValueKey]] = {}
    for identifier in graph.order:
        step = steps[identifier]
        if step.form != "use":
            continue
        for target in {item.next for item in step.on}:
            variants = [
                frozenset({("result", item.capture)}) if item.capture else frozenset()
                for item in step.on
                if item.next == target
            ]
            definite = variants[0] if variants else frozenset()
            for variant in variants[1:]:
                definite &= variant
            edge_produced[(identifier, target)] = definite
    graph.edge_produced = edge_produced

    entry_values = frozenset(("input", name) for name, _ in workflow.inputs)
    available: dict[str, frozenset[ValueKey]] = {}
    gates: dict[str, dict[str, frozenset[str]]] = {}
    for identifier in graph.order:
        incoming = graph.predecessors.get(identifier, ())
        if not incoming:
            available[identifier] = entry_values
            gates[identifier] = {}
            continue
        value_sets = []
        gate_sets = []
        for previous in incoming:
            value_sets.append(
                available[previous]
                | produced[previous]
                | edge_produced.get((previous, identifier), frozenset())
            )
            gate_sets.append(_gates_after(steps[previous], gates[previous], identifier))
        merged = value_sets[0]
        for other in value_sets[1:]:
            merged = merged & other
        available[identifier] = merged
        gates[identifier] = _merge_gates(gate_sets)
    graph.available = available
    graph.gates = gates


def _gates_after(
    step: Step, inherited: dict[str, frozenset[str]], target: str
) -> dict[str, frozenset[str]]:
    """The gate decisions every path through this step to the target has made."""
    carried = dict(inherited)
    if step.form == "gate":
        reached = frozenset(
            option.id for option in step.options if option.next == target
        )
        if reached:
            carried[step.id] = reached
    return carried


def _merge_gates(
    sets: list[dict[str, frozenset[str]]],
) -> dict[str, frozenset[str]]:
    """Keep a gate only where every incoming path passed through it."""
    if not sets:
        return {}
    shared = set(sets[0])
    for other in sets[1:]:
        shared &= set(other)
    merged: dict[str, frozenset[str]] = {}
    for gate in sorted(shared):
        states: frozenset[str] = frozenset()
        for other in sets:
            states |= other[gate]
        merged[gate] = states
    return merged


def _check_conditions(
    workflow: Workflow,
    steps: dict[str, Step],
    sources: SourceSet,
    graph: WorkflowGraph,
    diagnostics: Diagnostics,
) -> None:
    """Type-check every condition and declared read at the point it is evaluated."""
    records = sources.record_types()
    path = workflow.path
    for identifier in graph.order:
        step = steps[identifier]
        environment = graph.environment(records, identifier)
        for reference in step.uses:
            _check_reference(reference, environment, path, f"steps.{identifier}.uses", diagnostics)
        if step.form == "branch":
            for index, case in enumerate(step.cases):
                if case.when is not None:
                    _report(
                        check_expression(case.when, environment),
                        path,
                        f"steps.{identifier}.branch[{index}].when",
                        diagnostics,
                    )
        for heuristic_id in step.heuristics:
            heuristic = sources.heuristics.get(heuristic_id)
            if heuristic is None:
                continue
            for advice in heuristic.advice:
                if advice.when is not None:
                    _report(
                        check_expression(advice.when, environment),
                        path,
                        f"steps.{identifier}: heuristic {heuristic_id} advice "
                        f"{advice.id} when",
                        diagnostics,
                    )


def _check_reference(
    text: str,
    environment: TypeEnvironment,
    path,
    location: str,
    diagnostics: Diagnostics,
) -> Reference | None:
    try:
        reference = parse_reference(text)
    except ExpressionError as exc:
        diagnostics.error(f"{path}: {location}: {exc}", exc.code, path)
        return None
    found, problem = environment.lookup(reference)
    if found is None and problem is not None:
        diagnostics.error(f"{path}: {location}: {problem.message}", problem.code, path)
        return None
    return reference


def _report(problems, path, location: str, diagnostics: Diagnostics) -> None:
    for problem in problems:
        diagnostics.error(
            f"{path}: {location}: {problem.message}", problem.code, path
        )


def _check_supplied_values(
    workflow: Workflow,
    steps: dict[str, Step],
    sources: SourceSet,
    graph: WorkflowGraph,
    diagnostics: Diagnostics,
) -> None:
    """Check every `with` against what its destination declares."""
    records = sources.record_types()
    path = workflow.path
    for identifier in graph.order:
        step = steps[identifier]
        environment = graph.environment(records, identifier)
        if step.form == "use":
            callee = sources.workflows.get(step.call)
            expected = dict(callee.inputs) if callee is not None else None
            label = f"workflow {step.call}"
        elif step.form == "pattern":
            pattern = sources.patterns.get(step.pattern)
            expected = dict(pattern.inputs) if pattern is not None else None
            label = f"pattern {step.pattern}"
        elif step.form == "return":
            outcome = workflow.outcome(step.outcome)
            record = (
                sources.records.get(outcome.record)
                if outcome is not None and outcome.record
                else None
            )
            expected = record.types() if record is not None else None
            label = f"record {outcome.record}" if outcome is not None else ""
        else:
            continue
        if expected is None:
            continue
        supplied = dict(step.supplied)
        if step.form != "return":
            missing = sorted(set(expected) - set(supplied))
            if missing:
                diagnostics.error(
                    f"{path}: steps.{identifier}.with leaves "
                    f"{', '.join(missing)} unsupplied; {label} declares it",
                    "value.missing-binding",
                    path,
                )
            extra = sorted(set(supplied) - set(expected))
            if extra:
                diagnostics.error(
                    f"{path}: steps.{identifier}.with supplies "
                    f"{', '.join(extra)}, which {label} does not declare",
                    "value.unknown-binding",
                    path,
                )
        for name, binding in step.supplied:
            declared = expected.get(name)
            if declared is None:
                continue
            _report(
                check_binding(binding, declared, environment),
                path,
                f"steps.{identifier}.with.{name}",
                diagnostics,
            )


def call_order(
    primary: str, sources: SourceSet, diagnostics: Diagnostics
) -> tuple[tuple[str, ...], dict[str, tuple[str, str]]]:
    """The workflows a run can reach, in first-call order, and who calls each.

    A generated document renders the primary workflow and then each supporting
    workflow in the order a run first reaches it, so an agent reading forward
    meets a callee after the call that named it. A cycle is rejected: a call
    frame that could re-enter itself has no bound the compiler can render.
    """
    ordered: list[str] = []
    callers: dict[str, tuple[str, str]] = {}
    if primary not in sources.workflows:
        return (), {}
    pending = [primary]
    while pending:
        current = pending.pop(0)
        if current in ordered:
            continue
        ordered.append(current)
        workflow = sources.workflows.get(current)
        if workflow is None:
            continue
        for step in workflow.steps:
            if step.form != "use" or step.call not in sources.workflows:
                continue
            if step.call not in callers and step.call != primary:
                callers[step.call] = (current, step.id)
            if step.call not in ordered and step.call not in pending:
                pending.append(step.call)
    _reject_call_cycles(primary, sources, diagnostics)
    return tuple(ordered), callers


def _reject_call_cycles(
    primary: str, sources: SourceSet, diagnostics: Diagnostics
) -> None:
    state: dict[str, int] = {}

    def visit(identifier: str, stack: list[str]) -> None:
        state[identifier] = 1
        workflow = sources.workflows.get(identifier)
        if workflow is not None:
            for step in workflow.steps:
                if step.form != "use" or step.call not in sources.workflows:
                    continue
                if state.get(step.call) == 1:
                    cycle = [*stack[stack.index(step.call) :], step.call]
                    diagnostics.error(
                        f"{workflow.path}: steps.{step.id} calls "
                        f"{step.call}, closing the call cycle "
                        f"{' -> '.join(cycle)}; a call frame cannot re-enter "
                        "itself",
                        "workflow.invalid-edge",
                        workflow.path,
                    )
                    continue
                if state.get(step.call) is None:
                    visit(step.call, [*stack, step.call])
        state[identifier] = 2

    if primary in sources.workflows:
        visit(primary, [primary])
