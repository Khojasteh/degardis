"""Choose document boundaries by the reading cost of executable paths.

A topological order makes each module a contiguous interval that a path enters
at most once per workflow invocation. Different paths can skip different
intervals, so a partition's total bytes are not its execution cost. The search
keeps costs at every open continuation instead of collapsing those paths into
one prefix total. A bounded frontier avoids exponential compilation on wide
graphs; the renderer compares complete candidates using their actual text.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lowering import LoweredWorkflow, Node
from .model import BLOCKED_OUTCOME


Cost = tuple[int, int]
ZERO: Cost = (0, 0)
# These bound search breadth, not runtime document size. Three orders times
# eight surviving states also bounds the number of complete layouts to render.
SEARCH_WIDTH = 8


def add(left: Cost, right: Cost) -> Cost:
    return left[0] + right[0], left[1] + right[1]


def maximum(left: Cost, right: Cost) -> Cost:
    """Bytes and loads have independent worst paths; neither hides the other."""
    return max(left[0], right[0]), max(left[1], right[1])


@dataclass(frozen=True)
class Route:
    target: str = ""
    outcome: str = ""
    cost: Cost = ZERO


def workflow_routes(
    workflow: LoweredWorkflow, callees: dict[str, dict[str, Cost]]
) -> dict[str, tuple[Route, ...]]:
    """Pair each call result with only the continuation that handles it.

    Taking a callee's most expensive outcome and adding the caller's most
    expensive continuation could invent a path no invocation can take.
    Source outcome order survives lowering, including inserted after-checks.
    """
    routes: dict[str, tuple[Route, ...]] = {}
    steps = {step.id: step for step in workflow.workflow.steps}
    for node in workflow.nodes:
        if node.kind == "return":
            routes[node.label] = (Route(outcome=node.outcome),)
        elif node.call_workflow:
            costs = callees.get(node.call_workflow, {})
            step = steps[node.step]
            edges = [
                Route(edge.target, cost=costs[outcome.id])
                for outcome, edge in zip(step.on, node.transitions)
                if outcome.id in costs
            ]
            if BLOCKED_OUTCOME in costs:
                edges.append(Route(outcome=BLOCKED_OUTCOME, cost=costs[BLOCKED_OUTCOME]))
            routes[node.label] = tuple(edges)
        else:
            routes[node.label] = tuple(
                Route(outcome=BLOCKED_OUTCOME) if edge.blocked else Route(edge.target)
                for edge in node.transitions
            )
    return routes


def path_costs(
    workflow: LoweredWorkflow,
    chunks: list[list[Node]],
    sizes: list[int],
    callees: dict[str, dict[str, Cost]],
) -> dict[str, Cost]:
    """Charge each explicit module load, including every callee invocation.

    The caller's current module is already loaded when a call returns. Its
    continuation pays another load only if the edge names a different module.
    Failure paths terminate instead of inheriting the success continuation.
    """
    placed = {node.label: index for index, chunk in enumerate(chunks) for node in chunk}
    if workflow.entry not in placed:
        return {}
    arrivals = {workflow.entry: (sizes[placed[workflow.entry]], 1)}
    outcomes: dict[str, Cost] = {}
    routes = workflow_routes(workflow, callees)
    for node in workflow.nodes:
        if node.label not in arrivals:
            continue
        for route in routes[node.label]:
            cost = add(arrivals[node.label], route.cost)
            if route.outcome:
                outcomes[route.outcome] = maximum(outcomes.get(route.outcome, ZERO), cost)
            elif route.target in placed:
                target = placed[route.target]
                if target != placed[node.label]:
                    cost = add(cost, (sizes[target], 1))
                arrivals[route.target] = maximum(arrivals.get(route.target, ZERO), cost)
    return outcomes


@dataclass
class ModuleCosts:
    """Renderer-measured node bytes and the extra cost of crossing each edge.

    Header and destination widths conservatively bound every final numbering.
    Exact rendered sizes decide which complete candidate is actually retained.
    """
    body: dict[str, int]
    crossing: dict[str, tuple[tuple[str, int], ...]]
    header: tuple[int, int]
    entry: str
    budget: int

    def intervals(self, order: list[Node], start: int) -> list[tuple[int, int]]:
        """Return fitting ends, including a singleton that cannot be divided.

        Do not stop at the first overflow: adding a destination can remove
        enough crossing-edge prose to make a larger interval fit again. Only
        the local body, which grows monotonically, is a safe stopping bound.
        """
        incoming: dict[str, int] = {}
        body = 0
        extra = 0
        header = self.header[0]
        found: list[tuple[int, int]] = []
        for index in range(start, len(order)):
            label = order[index].label
            body += self.body[label]
            if label == self.entry:
                header = self.header[1]
            extra -= incoming.get(label, 0)
            for target, size in self.crossing[label]:
                incoming[target] = incoming.get(target, 0) + size
                extra += size
            # Each separately measured section includes its following blank
            # line. The final section has no neighbour and pays one byte less.
            size = header + body + extra - 1
            if size <= self.budget or index == start:
                found.append((index + 1, size))
            if header + body - 1 > self.budget:
                break
        return found


def greedy_partition(order: list[Node], costs: ModuleCosts) -> list[list[Node]]:
    """Keep a cheap complete candidate even when the bounded search prunes it."""
    chunks: list[list[Node]] = []
    start = 0
    while start < len(order):
        end = costs.intervals(order, start)[-1][0]
        chunks.append(order[start:end])
        start = end
    return chunks or [[]]


def candidate_orders(workflow: LoweredWorkflow) -> list[list[Node]]:
    """Try source order and both deterministic depth-first branch preferences.

    A preferred successor still waits for every predecessor. Only document
    order changes; labels, commands, decisions, and execution edges do not.
    """
    nodes = {node.label: node for node in workflow.nodes}
    rank = {node.label: index for index, node in enumerate(workflow.nodes)}
    successors = {
        node.label: tuple(dict.fromkeys(
            edge.target for edge in node.transitions if not edge.blocked
        ))
        for node in workflow.nodes
    }
    if len(nodes) != len(workflow.nodes) or any(
        target not in rank or rank[target] <= rank[source]
        for source, targets in successors.items() for target in targets
    ):
        # Invalid graphs still reach the renderer's own collision/edge checks.
        return []
    orders = [workflow.nodes]
    for reverse in (False, True):
        priority: dict[str, int] = {}
        stack = [workflow.entry]
        while stack:
            label = stack.pop()
            if label in priority or label not in nodes:
                continue
            priority[label] = len(priority)
            stack.extend(sorted(successors[label], key=rank.__getitem__, reverse=not reverse))
        if len(priority) != len(nodes):
            return []
        incoming = dict.fromkeys(nodes, 0)
        for targets in successors.values():
            for target in targets:
                incoming[target] += 1
        ready = [label for label in nodes if incoming[label] == 0]
        order: list[Node] = []
        while ready:
            label = min(ready, key=lambda item: (priority.get(item, len(nodes)), rank[item]))
            ready.remove(label)
            order.append(nodes[label])
            for target in successors[label]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)
        if [node.label for node in order] not in [[node.label for node in item] for item in orders]:
            orders.append(order)
    return orders


@dataclass
class _State:
    ends: tuple[int, ...]
    arrivals: dict[str, Cost]
    outcomes: dict[str, Cost]
    total: int = 0


def _extend(
    state: _State, nodes: list[Node], end: int, size: int,
    routes: dict[str, tuple[Route, ...]],
) -> _State:
    arrivals = state.arrivals.copy()
    outcomes = state.outcomes.copy()
    # Every arrival already recorded came from an earlier module. Propagation
    # within this module below must not charge its bytes a second time.
    for node in nodes:
        if node.label in arrivals:
            arrivals[node.label] = add(arrivals[node.label], (size, 1))
    for node in nodes:
        cost = arrivals.pop(node.label, None)
        if cost is None:
            continue
        for route in routes[node.label]:
            following = add(cost, route.cost)
            if route.outcome:
                outcomes[route.outcome] = maximum(outcomes.get(route.outcome, ZERO), following)
            else:
                arrivals[route.target] = maximum(arrivals.get(route.target, ZERO), following)
    return _State((*state.ends, end), arrivals, outcomes, state.total + size)


def _rank(state: _State, remaining: dict[str, Cost]) -> tuple[int, int, int]:
    worst = ZERO
    for cost in state.outcomes.values():
        worst = maximum(worst, cost)
    for label, cost in state.arrivals.items():
        worst = maximum(worst, add(cost, remaining[label]))
    return *worst, state.total


def _dominates(left: _State, right: _State) -> bool:
    if left.total > right.total:
        return False
    for first, second in ((left.arrivals, right.arrivals), (left.outcomes, right.outcomes)):
        if first.keys() != second.keys():
            return False
        if any(a > b for key in first for a, b in zip(first[key], second[key])):
            return False
    return True


def candidate_partitions(
    workflow: LoweredWorkflow, order: list[Node], costs: ModuleCosts,
    callees: dict[str, dict[str, Cost]],
) -> list[list[list[Node]]]:
    """Search boundaries with a bounded dynamic-programming frontier.

    States with no better cost at any open continuation can be discarded.
    When incomparable states exceed the bound, rank them by a lower bound on
    their completed paths. This is a deterministic search, not a claim of a
    global optimum for arbitrary branching DAGs.
    """
    routes = workflow_routes(workflow, callees)
    remaining: dict[str, Cost] = {}
    for node in reversed(order):
        tail = ZERO
        for route in routes[node.label]:
            tail = maximum(tail, add(route.cost, remaining.get(route.target, ZERO)))
        remaining[node.label] = add((costs.body[node.label], 0), tail)
    states: list[list[_State]] = [[] for _ in range(len(order) + 1)]
    states[0] = [_State((), {workflow.entry: ZERO}, {})]
    for start in range(len(order)):
        for end, size in costs.intervals(order, start):
            group = order[start:end]
            pool = states[end]
            for state in states[start]:
                candidate = _extend(state, group, end, size, routes)
                if any(_dominates(other, candidate) for other in pool):
                    continue
                pool[:] = [other for other in pool if not _dominates(candidate, other)]
                pool.append(candidate)
                pool.sort(key=lambda item: (_rank(item, remaining), item.ends))
                del pool[SEARCH_WIDTH:]
    found: list[list[list[Node]]] = []
    for state in states[-1]:
        starts = (0, *state.ends[:-1])
        found.append([order[start:end] for start, end in zip(starts, state.ends)])
    return found
