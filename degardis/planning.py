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
# How many rival partitions of the same prefix survive at one boundary. The
# search cannot keep them all, so it keeps this many and discards the rest by
# the ranking below. It bounds search breadth, not runtime document size, and
# together with the number of candidate orders it bounds how many complete
# layouts the renderer has to measure. Widening it buys nothing measurable:
# on a 1086-node skill every width from here to sixty-four chose the same
# layout, and narrowing it to one costs bytes, loads, and a module.
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
    """One partition of a prefix, with the cost standing at every open edge.

    `order` ranks this state against its siblings at the same boundary. It is a
    pure function of the state and of the remaining-cost table the whole search
    shares, so `_extend` computes it once instead of the frontier rebuilding it
    on every sort. Only the starting state keeps the default, having no sibling.
    """
    ends: tuple[int, ...]
    arrivals: dict[str, Cost]
    outcomes: dict[str, Cost]
    total: int = 0
    order: tuple[int, int, int] = (0, 0, 0)


def _extend(
    state: _State, group: list[str], emitted: frozenset[str], end: int, size: int,
    routes: dict[str, tuple[tuple[str, bool, int, int], ...]],
    remaining: dict[str, Cost],
) -> _State:
    """The search's innermost step, so `add` and `maximum` are spelled out here.

    Both are two integer operations on a pair, and this runs once per surviving
    partition per candidate interval: on a skill with a binding for every node
    the call overhead of the named helpers costs more than the arithmetic they
    perform. A cost is a count, so it is never negative, which is what lets a
    missing entry stand in for `ZERO` without a maximum against it. The routes
    arrive pre-flattened for the same reason, and the labels arrive already
    separated from their nodes: the frontier is what varies here, and anything
    that depends only on the interval is settled once by the caller.
    """
    arrivals = state.arrivals.copy()
    outcomes = state.outcomes.copy()
    # Every arrival already recorded came from an earlier module. Propagation
    # within this module below must not charge its bytes a second time, which
    # is why the charge is settled for the whole frontier before any of it
    # propagates. The open frontier is narrower than the interval, so this
    # walks the frontier and asks which of it lands here.
    for label in state.arrivals:
        if label in emitted:
            standing = arrivals[label]
            arrivals[label] = (standing[0] + size, standing[1] + 1)
    for label in group:
        cost = arrivals.pop(label, None)
        if cost is None:
            continue
        bytes_here, loads_here = cost
        for key, terminal, route_bytes, route_loads in routes[label]:
            bytes_there = bytes_here + route_bytes
            loads_there = loads_here + route_loads
            reached = outcomes if terminal else arrivals
            standing = reached.get(key)
            if standing is None:
                reached[key] = (bytes_there, loads_there)
            else:
                standing_bytes, standing_loads = standing
                reached[key] = (
                    standing_bytes if standing_bytes > bytes_there else bytes_there,
                    standing_loads if standing_loads > loads_there else loads_there,
                )
    following = _State((*state.ends, end), arrivals, outcomes, state.total + size)
    following.order = _rank(following, remaining)
    return following


def _rank(state: _State, remaining: dict[str, Cost]) -> tuple[int, int, int]:
    worst_bytes = 0
    worst_loads = 0
    for cost in state.outcomes.values():
        if cost[0] > worst_bytes:
            worst_bytes = cost[0]
        if cost[1] > worst_loads:
            worst_loads = cost[1]
    for label, cost in state.arrivals.items():
        rest = remaining[label]
        total_bytes = cost[0] + rest[0]
        total_loads = cost[1] + rest[1]
        if total_bytes > worst_bytes:
            worst_bytes = total_bytes
        if total_loads > worst_loads:
            worst_loads = total_loads
    return worst_bytes, worst_loads, state.total


def _dominates(left: _State, right: _State) -> bool:
    """Compare two partitions of the same prefix at every open continuation.

    Both states have emitted the same nodes, so which continuations are open,
    and which outcomes have been reached, follow from the prefix alone and are
    the same keys on each side. Only the costs standing at them differ.
    """
    if left.total > right.total:
        return False
    for first, second in ((left.arrivals, right.arrivals), (left.outcomes, right.outcomes)):
        for key, cost in first.items():
            other = second[key]
            if cost[0] > other[0] or cost[1] > other[1]:
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
    # A route's destination, its terminal-or-not, and its two cost numbers are
    # read once per surviving partition per interval, so they are unpacked into
    # a plain tuple here rather than fetched off a dataclass in that loop.
    flattened = {
        label: tuple(
            (route.outcome or route.target, bool(route.outcome), *route.cost)
            for route in items
        )
        for label, items in routes.items()
    }
    labels = [node.label for node in order]
    states: list[list[_State]] = [[] for _ in range(len(order) + 1)]
    # The starting state is the only one that is never ranked: nothing competes
    # with it at boundary zero, so it keeps the unranked default.
    states[0] = [_State((), {workflow.entry: ZERO}, {})]
    for start in range(len(order)):
        # No partition of this prefix survived, so no interval starting here
        # can extend one. Enumerating the intervals anyway costs a walk to the
        # budget for every boundary the frontier never reached.
        if not states[start]:
            continue
        for end, size in costs.intervals(order, start):
            group = labels[start:end]
            emitted = frozenset(group)
            pool = states[end]
            for state in states[start]:
                candidate = _extend(
                    state, group, emitted, end, size, flattened, remaining
                )
                if any(_dominates(other, candidate) for other in pool):
                    continue
                pool[:] = [other for other in pool if not _dominates(candidate, other)]
                pool.append(candidate)
                pool.sort(key=lambda item: (item.order, item.ends))
                del pool[SEARCH_WIDTH:]
    found: list[list[list[Node]]] = []
    for state in states[-1]:
        starts = (0, *state.ends[:-1])
        found.append([order[start:end] for start, end in zip(starts, state.ends)])
    return found
