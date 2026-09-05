"""Measure loaded documents along real routes, independently of the planner.

The small branching sources have only two routes, so enumeration is a useful
oracle here even though production planning must not enumerate execution paths.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis.graph import WorkflowGraph
from degardis.lowering import LoweredWorkflow, Node, Transition
from degardis.planning import ModuleCosts, candidate_orders, candidate_partitions, greedy_partition, path_costs
from degardis.sources import CallOutcome, Step, Workflow

from tests.support import compiled, write_text


def branching_skill(root: Path, *, steps: int = 12, calls: bool = False) -> Path:
    skill = root / "branching"
    write_text(
        skill / "skill.yaml",
        "name: branching\nformat_version: 2\nversion: 1.0.0\n"
        "description: Exercise mutually exclusive execution routes.\n"
        "primary_workflow: run\ncontent:\n  workflows: [workflows/*.yaml]\n"
        "interface:\n  display_name: Branching\n"
        "  short_description: Exercise execution routes\n"
        "  default_prompt: Use {name} for this task.\n",
    )
    lines = [
        "title: Perform the selected work",
        "description: Perform the work on the chosen route.",
        "outcomes:", "  done: {}", "entry: choose", "steps:",
        "  choose:", "    decide: Choose the applicable route.", "    choices:",
        "      left:", "        command: Perform the left route.", "        next: left-0",
        "      right:", "        command: Perform the right route.", "        next: right-0",
    ]
    for index in range(steps):
        for route in ("left", "right"):
            following = f"{route}-{index + 1}" if index + 1 < steps else "finish"
            lines += [
                f"  {route}-{index}:",
                f"    action: Inspect the {route} record {index}, "
                + "reconcile its evidence against the supplied source, " * 12
                + "then record the result.",
                f"    next: {following}",
            ]
    lines += ["  finish:", "    return:", "      outcome: done"]
    name = "choose-work" if calls else "run"
    write_text(skill / "workflows" / f"{name}.yaml", "\n".join(lines) + "\n")
    if calls:
        write_text(
            skill / "workflows" / "run.yaml",
            "title: Perform both tasks\ndescription: Perform each task and return.\n"
            "outcomes:\n  done: {}\nentry: first\nsteps:\n"
            "  first:\n    use: choose-work\n    on:\n      done: second\n"
            "  second:\n    use: choose-work\n    on:\n      done: finish\n"
            "  finish:\n    return:\n      outcome: done\n",
        )
    return skill


def loaded_cost(result) -> tuple[int, int, int, int]:
    """Enumerate routes and charge a whole module on each explicit load.

    Calls pay again on each invocation, but returning to an already loaded
    caller does not. Each callee outcome follows only its matching continuation.
    """
    rendered = result.rendered
    sizes = {path: len(text.encode("utf-8")) for path, text in rendered.execution_modules.items()}
    placed = {
        label: path
        for path, text in rendered.execution_modules.items()
        for label in re.findall(r"^### \[`([^`]+)`\]", text, re.M)
    }
    workflows = {item.workflow.id: item for item in result.lowered.workflows}
    nodes = {node.label: node for node in result.lowered.all_nodes()}

    def walk(label, current=""):
        node = nodes[label]
        module = placed[label]
        size, loads = (sizes[module], 1) if module != current else (0, 0)
        if node.kind == "return":
            yield node.outcome, size, loads
            return
        if node.call_workflow:
            callee = workflows[node.call_workflow]
            step = workflows[node.workflow].workflow.step(node.step)
            targets = {outcome.id: edge.target for outcome, edge in zip(step.on, node.transitions)}
            for outcome, call_size, call_loads in walk(callee.entry):
                if outcome == "blocked":
                    yield outcome, size + call_size, loads + call_loads
                else:
                    for final, tail_size, tail_loads in walk(targets[outcome], module):
                        yield final, size + call_size + tail_size, loads + call_loads + tail_loads
            return
        for edge in node.transitions:
            if edge.blocked:
                yield "blocked", size, loads
            else:
                for outcome, tail_size, tail_loads in walk(edge.target, module):
                    yield outcome, size + tail_size, loads + tail_loads

    primary = workflows[result.lowered.skill.primary_workflow]
    routes = list(walk(primary.entry))
    return max(row[1] for row in routes), max(row[2] for row in routes), sum(sizes.values()), max(sizes.values())


class ExecutionPlanningTests(unittest.TestCase):
    def test_mutually_exclusive_routes_do_not_load_each_others_bodies(self):
        """A run through either branch should avoid most of the other branch."""
        with tempfile.TemporaryDirectory() as directory:
            _, result, diagnostics = compiled(branching_skill(Path(directory)))
            self.assertEqual([], diagnostics.errors)
            worst, _, total, largest = loaded_cost(result)
            self.assertLess(worst, total * 0.8)
            self.assertLessEqual(largest, 16 * 1024)

    def test_reported_path_cost_matches_enumerated_execution(self):
        """The cost includes repeated calls, and binding failures stop the path."""
        with tempfile.TemporaryDirectory() as directory:
            paths = [
                branching_skill(Path(directory), calls=True),
                Path("tests/fixtures/skills/demo/alpha"),
                Path("examples/structured-summary"),
            ]
            for path in paths:
                with self.subTest(skill=path.name):
                    _, result, diagnostics = compiled(path)
                    self.assertEqual([], diagnostics.errors)
                    self.assertEqual(
                        loaded_cost(result)[:2],
                        (result.rendered.execution_path_bytes, result.rendered.execution_path_loads),
                    )

    def test_reordering_keeps_every_node_and_every_edge(self):
        """Grouping branches changes placement, never the lowered instructions."""
        with tempfile.TemporaryDirectory() as directory:
            path = branching_skill(Path(directory))
            _, result, _ = compiled(path)
            placed = {}
            for index, text in enumerate(result.rendered.execution_modules.values()):
                for position, label in enumerate(re.findall(r"^### \[`([^`]+)`\]", text, re.M)):
                    self.assertNotIn(label, placed)
                    placed[label] = index, position
            self.assertEqual({node.label for node in result.lowered.all_nodes()}, set(placed))
            for node in result.lowered.all_nodes():
                for edge in node.transitions:
                    if not edge.blocked:
                        self.assertLess(placed[node.label], placed[edge.target])
            _, again, _ = compiled(path)
            self.assertEqual(result.rendered.execution_modules, again.rendered.execution_modules)

    def test_numbering_above_ninety_nine_stays_within_budget(self):
        """Search and final rendering must agree when module names gain a digit."""
        with tempfile.TemporaryDirectory() as directory:
            path = branching_skill(Path(directory), steps=100)
            with mock.patch("degardis.render.MODULE_BUDGET_BYTES", 2048):
                _, result, diagnostics = compiled(path)
            self.assertEqual([], diagnostics.errors)
            modules = result.rendered.execution_modules
            self.assertGreater(len(modules), 99)
            self.assertTrue(all(len(text.encode("utf-8")) <= 2048 for text in modules.values()))

    def test_complete_layout_never_loses_to_its_greedy_candidate(self):
        """A pruned search frontier must not make the retained layout worse."""
        with tempfile.TemporaryDirectory() as directory:
            path = branching_skill(Path(directory), calls=True)
            with mock.patch("degardis.render.candidate_partitions", return_value=[]), mock.patch(
                "degardis.render.candidate_orders", side_effect=lambda item: [item.nodes]
            ):
                _, baseline, _ = compiled(path)
            _, optimized, _ = compiled(path)
            self.assertLess(loaded_cost(optimized)[:3], loaded_cost(baseline)[:3])


def workflow_with(nodes: list[Node], steps: tuple[Step, ...] = ()) -> LoweredWorkflow:
    source = Workflow("run", Path("run.yaml"), "Run the task", "Perform the task.", nodes[0].step, steps)
    return LoweredWorkflow(source, WorkflowGraph(source), entry=nodes[0].label, nodes=nodes)


def node(label: str, *targets: str, outcome: str = "") -> Node:
    return Node(
        label, "return" if outcome else "action", "Perform the step.", "run", label,
        transitions=tuple(Transition("Next", target) for target in targets), outcome=outcome,
    )


class PathCostTests(unittest.TestCase):
    def test_call_outcomes_are_not_combined_into_an_impossible_path(self):
        """The slow callee route need not lead to the expensive caller route."""
        call = node("call", "expensive", "cheap")
        call.call_workflow = "callee"
        step = Step("call", "use", call="callee", on=(
            CallOutcome("short", "expensive"), CallOutcome("long", "cheap"),
        ))
        workflow = workflow_with(
            [call, node("expensive", outcome="done"), node("cheap", outcome="done")], (step,)
        )
        costs = path_costs(workflow, [[item] for item in workflow.nodes], [10, 1000, 20], {
            "callee": {"short": (30, 1), "long": (500, 5), "blocked": (800, 3)},
        })
        self.assertEqual({"done": (1040, 7), "blocked": (810, 4)}, costs)

    def test_each_call_pays_again_but_returning_to_the_caller_does_not(self):
        first, second = node("first", "second"), node("second", "finish")
        first.call_workflow = second.call_workflow = "callee"
        workflow = workflow_with([first, second, node("finish", outcome="done")], (
            Step("first", "use", call="callee", on=(CallOutcome("done", "second"),)),
            Step("second", "use", call="callee", on=(CallOutcome("done", "finish"),)),
        ))
        self.assertEqual({"done": (200, 5)}, path_costs(
            workflow, [workflow.nodes], [100], {"callee": {"done": (50, 2)}}
        ))


class PartitionSearchTests(unittest.TestCase):
    def test_small_branching_partitions_match_exhaustive_search(self):
        """A cheaper prefix cannot discard a better continuation at a join."""
        cases = [
            ([(1, 2), (3,), (4,), (5,), (5,), ()], [1, 3, 3, 3, 3, 1], 8),
            ([(1, 5), (2,), (3, 4), (5,), (5,), ()], [2, 3, 2, 4, 1, 2], 8),
            ([(1, 2), (3,), (3,), (4, 5), (6,), (6,), ()], [1, 4, 2, 1, 2, 4, 1], 9),
        ]
        for edges, weights, budget in cases:
            labels = [str(index) for index in range(len(edges))]
            workflow = workflow_with([
                node(label, *(str(target) for target in targets), outcome="done" if not targets else "")
                for label, targets in zip(labels, edges)
            ])
            costs = ModuleCosts(
                dict(zip(labels, weights)),
                {label: tuple((str(target), 1) for target in targets) for label, targets in zip(labels, edges)},
                (1, 1), "0", budget,
            )

            def score(groups, weights=weights, budget=budget, edges=edges):
                placed = {item.label: index for index, group in enumerate(groups) for item in group}
                sizes = [sum(weights[int(item.label)] for item in group) + sum(
                    placed[item.label] != placed[edge.target] for item in group for edge in item.transitions
                ) for group in groups]
                if max(sizes) > budget:
                    return float("inf"), float("inf"), float("inf")
                paths = []
                pending = [(0, {placed["0"]})]
                while pending:
                    source, visited = pending.pop()
                    if not edges[source]:
                        paths.append((sum(sizes[index] for index in visited), len(visited)))
                    for target in edges[source]:
                        pending.append((target, visited | {placed[str(target)]}))
                return max(cost[0] for cost in paths), max(cost[1] for cost in paths), sum(sizes)

            exhaustive = []
            for mask in range(1 << (len(labels) - 1)):
                groups = [[]]
                for index, item in enumerate(workflow.nodes):
                    if index and mask & (1 << (index - 1)):
                        groups.append([])
                    groups[-1].append(item)
                exhaustive.append(score(groups))
            with self.subTest(edges=edges):
                candidates = candidate_partitions(workflow, workflow.nodes, costs, {})
                self.assertEqual(min(exhaustive), min(score(groups) for groups in candidates))

    def test_boundaries_are_compared_beyond_the_greedy_cut(self):
        """Cutting a linear run at a cheaper edge beats filling its first file."""
        workflow = workflow_with([
            node("a", "b"), node("b", "c"), node("c", "d"), node("d", outcome="done"),
        ])
        costs = ModuleCosts(
            dict.fromkeys("abcd", 2),
            {"a": (("b", 0),), "b": (("c", 0),), "c": (("d", 1),), "d": ()},
            (1, 1), "a", 7,
        )
        greedy = greedy_partition(workflow.nodes, costs)
        self.assertEqual([["a", "b", "c"], ["d"]], [[item.label for item in group] for group in greedy])
        candidates = candidate_partitions(workflow, workflow.nodes, costs, {})
        # Four two-byte nodes can fit in two files without any crossing prose.
        self.assertTrue(any(
            len(groups) == 2 and any(group[-1].label == "d" and group[0].label != "d" for group in groups)
            for groups in candidates
        ))

    def test_a_larger_interval_can_fit_after_an_overflow(self):
        """Including a destination removes the prose on a crossing edge."""
        workflow = workflow_with([node("a", "c"), node("b", "c"), node("c", outcome="done")])
        costs = ModuleCosts(
            dict.fromkeys("abc", 2), {"a": (("c", 10),), "b": (("c", 0),), "c": ()},
            (1, 1), "a", 6,
        )
        self.assertIn((3, 6), costs.intervals(workflow.nodes, 0))

    def test_branch_orders_wait_for_all_predecessors(self):
        """A join cannot be pulled ahead of a branch that also reaches it."""
        workflow = workflow_with([
            node("start", "a", "b"), node("a", "a2"), node("b", "b2"),
            node("a2", "finish"), node("b2", "finish"), node("finish", outcome="done"),
        ])
        orders = candidate_orders(workflow)
        self.assertGreater(len(orders), 1)
        for order in orders:
            rank = {item.label: index for index, item in enumerate(order)}
            self.assertEqual(6, len(rank))
            for item in order:
                for edge in item.transitions:
                    self.assertLess(rank[item.label], rank[edge.target])


if __name__ == "__main__":
    unittest.main()
