"""The format's conformance cases, one test each.

This file is where the cases live. Each is stated in the comment above the test
that holds it and numbered `test_case_<NN>_...` after it, so a reader checks the
suite by reading it rather than by reading the compiler, and a case with no test
is a gap `test_the_case_numbering_has_no_gaps` reports. Adding a case to the
format means adding its comment and its test here; nothing outside this file
states the list.

Each test takes its expected value from the source under test — the fixture's
own YAML, or an edit this file makes to a copy of it — never from the rendered
output, and a case whose point is a refusal makes that edit and asserts the
check code, so an edit that failed to land cannot pass. A test that reads its
expectation out of the renderer records where a string currently lives.

The fixture's module names and titles are misleading on purpose: a load
operation still has to send the agent to the exact module and entry command
rather than let it infer content from those names.
"""

from __future__ import annotations

import re
import posixpath
import shutil
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from unittest import mock

from degardis import wording
from degardis.build import build_skills
from degardis.explain import checks
from degardis.model import BLOCKED_OUTCOME
from degardis.render import MARKDOWN_LINK, MODULE_BUDGET_BYTES, ROOT_BUDGET_BYTES
from tests.checkcodes import emitted_check_codes
from tests.support import compiled, edit_yaml, folder_names, folder_text
from tests.test_planning import branching_skill, loaded_cost


ALPHA = Path("tests/fixtures/skills/demo/alpha")
NODE_ID = re.compile(r"^n-[0-9a-f]{10}$")
# How a module is named where an agent is sent to one: the stem of a generated
# module path, followed by the node it must continue at.
MODULE_REFERENCE = re.compile(r"`([a-z0-9][a-z0-9-]*-\d{2,}):(n-[0-9a-f]{10})`")
# A node's heading: the label an edge names it by, then the command it states.
NODE_HEADING = re.compile(r"^### \[`(?P<label>n-[0-9a-f]{10})`\] (?P<command>.+)$", re.M)


def module_stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def linear_skill(root: Path, steps: int) -> Path:
    """Write a skill whose one workflow is `steps` ordered actions.

    Each step produces a value nothing later reads, so the set of values live at
    a node grows with its position. A renderer that printed every live value
    would therefore grow quadratically in `steps`, which is what case 16
    measures.
    """
    skill = root / "linear"
    (skill / "workflows").mkdir(parents=True)
    (skill / "skill.yaml").write_text(
        "name: linear\n"
        "format_version: 2\n"
        "version: 1.0.0\n"
        "description: Exercise a long linear workflow.\n"
        "entrypoints:\n"
        "  run:\n"
        "    target: run\n"
        "content:\n"
        "  workflows:\n"
        "  - workflows/*.yaml\n"
        "interface:\n"
        "  display_name: Linear\n"
        "  short_description: Long linear workflow\n"
        "  default_prompt: Use {name} for this task.\n",
        encoding="utf-8",
    )
    lines = [
        "title: Run the long task",
        "description: Perform many ordered steps and report the result.",
        "inputs:",
        "  request:",
        "    type: string",
        "outcomes:",
        "  done: {}",
        "entry: s000",
        "steps:",
    ]
    for index in range(steps):
        following = f"s{index + 1:03d}" if index + 1 < steps else "finish"
        lines += [
            f"  s{index:03d}:",
            f"    action: Perform ordered step {index} of the long task.",
            "    uses: [input.request]",
            "    produces:",
            f"      v{index:03d}:",
            "        type: string",
            f"    next: {following}",
        ]
    lines += ["  finish:", "    return:", "      outcome: done"]
    (skill / "workflows" / "run.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return skill


def routed_skill(root: Path, routes: tuple[str, ...], *, catch_all: bool) -> Path:
    """Write a skill with one workflow per route, and one route per workflow.

    The workflows are deliberately alike: what these cases read is the routing
    table and the module layout, so any difference between the routes would be
    a difference the cases would then have to account for. `catch_all` decides
    whether the last route states a condition, which is the whole of what makes
    it the route taken when no other matched.
    """
    skill = root / "routed"
    (skill / "workflows").mkdir(parents=True)
    lines = ["entrypoints:"]
    for position, name in enumerate(routes):
        last = position == len(routes) - 1
        lines.append(f"  {name}:")
        if not (last and catch_all):
            lines.append(
                f"    when: The request asks for the {name} of supplied material."
            )
        lines.append(f"    target: {name}")
    (skill / "skill.yaml").write_text(
        "name: routed\n"
        "format_version: 2\n"
        "version: 1.0.0\n"
        "description: Exercise several ways into one skill.\n"
        + "\n".join(lines)
        + "\ncontent:\n"
        "  workflows:\n"
        "  - workflows/*.yaml\n"
        "interface:\n"
        "  display_name: Routed\n"
        "  short_description: Several ways in\n"
        "  default_prompt: Use {name} for this task.\n",
        encoding="utf-8",
    )
    for name in routes:
        (skill / "workflows" / f"{name}.yaml").write_text(
            f"title: Perform the {name}\n"
            f"description: Carry out the {name} the request asked for.\n"
            "inputs:\n"
            "  material:\n"
            "    type: string\n"
            "outcomes:\n"
            "  done: {}\n"
            "entry: begin\n"
            "steps:\n"
            "  begin:\n"
            f"    action: Establish what the supplied material offers the {name}.\n"
            "    uses: [input.material]\n"
            "    next: finish\n"
            "  finish:\n"
            "    return:\n"
            "      outcome: done\n",
            encoding="utf-8",
        )
    return skill


def prohibiting_gate_skill(root: Path) -> Path:
    """Write a workflow with prohibitions at its entry and a later gate."""
    skill = root / "prohibiting-gates"
    (skill / "policies").mkdir(parents=True)
    (skill / "workflows").mkdir()
    (skill / "skill.yaml").write_text(
        "name: prohibiting-gates\n"
        "format_version: 2\n"
        "version: 1.0.0\n"
        "description: Exercise every reference to a prohibiting check.\n"
        "entrypoints:\n"
        "  run:\n"
        "    target: run\n"
        "policies: [gate-discipline]\n"
        "content:\n"
        "  policies:\n"
        "  - policies/*.yaml\n"
        "  workflows:\n"
        "  - workflows/*.yaml\n"
        "interface:\n"
        "  display_name: Prohibiting gates\n"
        "  short_description: References to prohibiting checks\n"
        "  default_prompt: Use {name} for this task.\n",
        encoding="utf-8",
    )
    (skill / "policies" / "gate-discipline.yaml").write_text(
        "title: Gate discipline\n"
        "summary: Keep each gate decided on its own checklist.\n"
        "rationale: A substituted result leaves the gate unchecked.\n"
        "provisions:\n"
        "  no-substituted-result:\n"
        "    phase: before\n"
        "    match:\n"
        "      forms: [gate]\n"
        "    prohibit: Pass a gate on a substituted result.\n",
        encoding="utf-8",
    )
    (skill / "workflows" / "run.yaml").write_text(
        "title: Run both gates\n"
        "description: Decide two gates with an action between them.\n"
        "outcomes:\n"
        "  done: {}\n"
        "entry: first\n"
        "steps:\n"
        "  first:\n"
        "    gate: Establish whether the first material is present.\n"
        "    states:\n"
        "      present:\n"
        "        command: Continue with the first material.\n"
        "        next: prepare\n"
        "      absent:\n"
        "        command: Continue without the first material.\n"
        "        next: prepare\n"
        "  prepare:\n"
        "    action: Prepare the second material for its gate.\n"
        "    next: second\n"
        "  second:\n"
        "    gate: Establish whether the second material is present.\n"
        "    states:\n"
        "      present:\n"
        "        command: Continue with the second material.\n"
        "        next: finish\n"
        "      absent:\n"
        "        command: Continue without the second material.\n"
        "        next: finish\n"
        "  finish:\n"
        "    return:\n"
        "      outcome: done\n",
        encoding="utf-8",
    )
    return skill


def dense_skill(root: Path, steps: int) -> Path:
    """The same shape as `linear_skill`, with a command that fills a module.

    Case 19 reads these two against one budget. The only difference between
    them is how much each node renders to, which is exactly what a partition
    that counts nodes cannot see.
    """
    skill = linear_skill(root, steps)
    workflow = skill / "workflows" / "run.yaml"
    filler = (
        "reconciling each supplied record against the register of record and "
        "naming, for every discrepancy, the field, both values, and the source "
        "that decides between them, "
    ) * 3
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            " of the long task.", f" of the long task, {filler}then continue."
        ),
        encoding="utf-8",
    )
    return skill


def error_codes(diagnostics) -> set[str]:
    return {
        record.code for record in diagnostics.records if record.severity == "error"
    }


class ConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill, cls.result, cls.diagnostics = compiled(ALPHA)
        cls.rendered = cls.result.rendered
        cls.lowered = cls.result.lowered
        cls.sources = cls.lowered.sources
        cls.nodes = list(cls.lowered.all_nodes())
        cls.execution_text = "\n".join(cls.rendered.execution_modules.values())

    def test_the_fixture_the_cases_are_read_against_compiles_clean(self):
        self.assertEqual(set(), error_codes(self.diagnostics))

    def test_the_case_numbering_has_no_gaps(self):
        """A case removed from this file leaves a hole a reader could miss.

        The numbering is the format's list, so a gap in it means a case is
        stated nowhere rather than that a test was renamed.
        """
        numbers = sorted(
            {
                int(re.match(r"test_case_(\d+)_", name).group(1))
                for name in dir(self)
                if name.startswith("test_case_")
            }
        )
        self.assertTrue(numbers)
        self.assertEqual(list(range(1, numbers[-1] + 1)), numbers)

    # 1. one policy with `before`, `during`, `after`, and `before-return`
    #    provisions

    def test_case_01_one_policy_with_before_during_after_and_before_return(self):
        """Every phase of one policy reaches the workflow.

        A `during` provision is carried as an invariant on the nodes it
        selects; every other phase generates a check node at that phase, which
        states the provision's own sentence as its heading where the policy
        placed only that one here and lists it as an item where the policy
        placed several. Either way no bound provision is left without somewhere
        to be enforced.
        """
        policy = self.sources.policies["run-authority"]
        phases = {provision.phase for provision in policy.provisions}
        self.assertEqual({"before", "during", "after", "before-return"}, phases)
        for provision in policy.provisions:
            with self.subTest(provision=provision.id):
                self.assertIn(
                    ("run-authority", provision.id), self.lowered.lowered_provisions
                )
        for provision in policy.provisions:
            if provision.phase == "during":
                carried = [
                    node
                    for node in self.nodes
                    if any(
                        item.construct == "run-authority" and item.local == provision.id
                        for item in node.invariants
                    )
                ]
                self.assertTrue(carried, f"{provision.id} carried by no node")
            else:
                checks = [
                    node
                    for node in self.nodes
                    if node.kind == "check"
                    and node.phase == provision.phase
                    and (
                        node.provision == provision.id
                        or any(item.local == provision.id for item in node.checks)
                    )
                ]
                self.assertTrue(checks, f"{provision.id} generated no check node")

    # 2. one atomic rule with `when` and `unless` variants

    def test_case_02_one_atomic_rule_with_when_and_unless_variants(self):
        """A rule is one provision at file scope, conditional or not.

        Both the conditional and the unconditional rule lower, so activation
        conditions change when a rule applies rather than whether it is
        placed at all.
        """
        conditional = self.sources.rules["scoped-change"].provision
        self.assertIsNotNone(conditional.when)
        self.assertIsNotNone(conditional.unless)
        unconditional = self.sources.rules["name-the-gap"].provision
        self.assertIsNone(unconditional.when)
        self.assertIsNone(unconditional.unless)
        self.assertEqual(
            {"scoped-change", "name-the-gap"}, self.lowered.lowered_rules
        )

    # 3. a protocol frame at each of the run, workflow, and step scopes — not
    #    one protocol at all three, which nesting forbids
    #    (`workflow.duplicate-binding`)

    def test_case_03_a_protocol_frame_at_run_workflow_and_step_scope(self):
        """Each scope opens its own frame, and each frame reaches a node.

        A frame that generated nothing would leave its protocol's lifecycle
        unstated at runtime while the source still declares it.
        """
        self.assertEqual(
            {"run", "workflow", "step"}, {frame.scope for frame in self.lowered.frames}
        )
        for frame in self.lowered.frames:
            with self.subTest(scope=frame.scope):
                self.assertTrue(
                    [node for node in self.nodes if node.frame.endswith(
                        f"{frame.scope}-{frame.protocol.id}"
                    )],
                    f"{frame.scope} frame generated no node",
                )

    # 4. one protocol whose state stays open across several source steps

    def test_case_04_one_protocol_whose_state_stays_open_across_steps(self):
        """The hook that opens the state and the one that spends it are apart.

        They sit in different source steps with more than one node between
        them, so the state is genuinely carried across the workflow rather
        than opened and closed at one place.
        """
        protocol = self.sources.protocols["run-trail"]
        opens = next(hook for hook in protocol.hooks if hook.to == "held")
        spends = next(
            hook
            for hook in protocol.hooks
            if "finding" in hook.clears and hook.to == "spent"
        )
        opened = next(node for node in self.nodes if node.hook == opens.id)
        spent = next(node for node in self.nodes if node.hook == spends.id)
        # The workflow that carries the two hooks, found by asking which one
        # holds them rather than by position: the reachable workflows are
        # ordered by the routing table, so the first is whichever entrypoint
        # the fixture happens to declare first.
        carrier = next(
            item
            for item in self.lowered.workflows
            if item.workflow.id == opened.workflow
        )
        order = [node.label for node in carrier.nodes]
        self.assertLess(order.index(opened.label), order.index(spent.label))
        self.assertNotEqual(opened.step, spent.step)
        between = order[order.index(opened.label) + 1 : order.index(spent.label)]
        self.assertGreater(len(between), 1)

    # 5. one pattern expanded twice, with validated input reads and effects only
    #    on the items that declare them

    def test_case_05_one_pattern_expanded_twice_with_per_item_effects(self):
        """Two applications expand into two complete, distinct copies.

        Effects appear on exactly the items that declare them rather than
        spreading over their siblings, and each item reads through the
        caller's own binding rather than the pattern's declared input name.
        """
        pattern = self.sources.patterns["inspect-plan-act"]
        applications = {
            key for key in self.lowered.expanded_patterns if key[0] == "run"
        }
        self.assertEqual(2, len(applications))
        procedure = [node for node in self.nodes if node.kind == "procedure"]
        self.assertEqual(2 * len(pattern.procedure), len(procedure))
        self.assertEqual(len(procedure), len({node.label for node in procedure}))
        declaring = [item for item in pattern.procedure if item.effects]
        self.assertTrue(declaring, "the fixture pattern declares no effects")
        # Spreading one item's effects over its siblings would show up here as
        # more nodes carrying effects than the declaring items can account for.
        self.assertEqual(
            2 * len(declaring), len([node for node in procedure if node.effects])
        )
        for item in pattern.procedure:
            expanded = [node for node in procedure if node.command == item.command]
            with self.subTest(item=item.id):
                self.assertEqual(2, len(expanded))
                for node in expanded:
                    self.assertEqual(bool(item.effects), bool(node.effects))
                    self.assertEqual(
                        item.effects, node.effects if item.effects else ()
                    )
        # A pattern input is read through the caller's binding, so the node names
        # the caller's own reference rather than the pattern's `input.target`.
        for step in self.sources.workflows["run"].steps:
            if step.form != "pattern":
                continue
            for name, binding in step.supplied:
                with self.subTest(step=step.id, input=name):
                    supplied = ".".join(
                        (binding.reference.namespace, *binding.reference.path)
                    )
                    reading = [
                        node
                        for node in procedure
                        if supplied in node.available
                    ]
                    self.assertTrue(reading)
                    self.assertNotIn(
                        f"input.{name}",
                        {value for node in reading for value in node.available},
                    )

    # 6. one heuristic attached to a decision and refused on an action

    def test_case_06_one_heuristic_on_a_decision_and_refused_on_an_action(self):
        """Advice renders where a choice is made, and nowhere else.

        Moving the same heuristic onto an action is reported, so advice
        cannot arrive at a step that states a command rather than a choice.
        """
        advised = [
            node
            for node in self.nodes
            if node.kind in ("decision", "gate") and node.consider
        ]
        self.assertEqual(2, len(advised))
        self.assertEqual(
            {"smallest-change", "prefer-evidence"}, self.lowered.used_heuristics
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            run = root / "workflows" / "run.yaml"
            run.write_text(
                run.read_text(encoding="utf-8").replace(
                    "    subjects: [report.write]",
                    "    subjects: [report.write]\n    heuristics: [smallest-change]",
                ),
                encoding="utf-8",
            )
            _, _, diagnostics = compiled(root)
            self.assertIn("heuristic.invalid-placement", error_codes(diagnostics))

    # 7. guidance whose runtime text is concise and whose references stay
    #    auxiliary

    def test_case_07_guidance_is_concise_and_its_references_stay_auxiliary(self):
        """Run scope carries the summary alone; step scope carries the points.

        A guidance unit's reference targets reach neither the root nor an
        execution module, so opening one is never part of executing the
        skill even though the generated page exists.
        """
        run_scope = self.sources.guidance["run-context"]
        self.assertIn(run_scope.summary, self.rendered.skill_text)
        for point in run_scope.points:
            with self.subTest(point=point):
                self.assertNotIn(point, self.rendered.skill_text)
                self.assertNotIn(point, self.execution_text)
        inline = self.sources.guidance["step-context"]
        self.assertIn(inline.summary, self.execution_text)
        for point in inline.points:
            with self.subTest(point=point):
                self.assertIn(point, self.execution_text)
        for target in run_scope.references:
            with self.subTest(target=target):
                self.assertNotIn(target, self.execution_text)
                self.assertNotIn(target, self.rendered.skill_text)
        self.assertIn("references/guidance/run-context.md", self.rendered.pages)

    # 8. an auxiliary profile catalog whose complete removal leaves `SKILL.md`
    #    and `execution/` byte-for-byte unchanged

    def test_case_08_removing_profiles_leaves_root_and_execution_unchanged(self):
        """A profile is retrieval material, so execution cannot depend on one.

        Nothing a profile says reaches an execution module, and deleting the
        whole generated tree leaves the document identical: a profile miss can
        therefore change nothing about validity or failure.
        """
        said = {
            text
            for profile in self.sources.profiles.values()
            for text in (
                profile.title,
                profile.description,
                *profile.points,
                *profile.references,
            )
            if text
        }
        self.assertTrue(said)
        for text in said:
            with self.subTest(says=text):
                self.assertNotIn(text, self.execution_text)
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(ALPHA, Path(directory))[0]
            before_root = folder_text(artifact, "SKILL.md")
            before_execution = {
                path: folder_text(artifact, path)
                for path in self.rendered.execution_modules
            }
            shutil.rmtree(artifact / "profiles")
            self.assertEqual(before_root, folder_text(artifact, "SKILL.md"))
            self.assertEqual(
                before_execution,
                {
                    path: folder_text(artifact, path)
                    for path in self.rendered.execution_modules
                },
            )

    # 9. a workflow call that explicitly names and enters the callee module

    def test_case_09_a_call_explicitly_names_and_enters_the_callee_module(self):
        """The caller names the module, the entry label, and its command.

        An agent crossing a module boundary is told exactly which module to
        read and what to do on arrival, rather than inferring either from the
        callee's name. What a qualified reference means, and what to return
        when the module cannot be read, is stated once in the root's execution
        contract instead of on every boundary.
        """
        call = next(node for node in self.nodes if node.kind == "call")
        callee = next(
            item
            for item in self.lowered.workflows
            if item.workflow.id == call.call_workflow
        )
        entry = next(node for node in callee.nodes if node.label == callee.entry)
        module = next(
            path
            for path, text in self.rendered.execution_modules.items()
            if f"[`{entry.label}`]" in text
        )
        caller = next(
            text
            for text in self.rendered.execution_modules.values()
            if f"[`{call.label}`]" in text
        )
        self.assertIn(f"`{module_stem(module)}:{entry.label}`", caller)
        self.assertIn(entry.command, caller)
        self.assertIn("blocked", self.rendered.skill_text)

    # 10. a record-bearing callee outcome captured as a caller result on that
    #     edge

    def test_case_10_a_record_bearing_callee_outcome_is_captured_on_its_edge(self):
        """The captured value is typed by the callee's record and scoped.

        It is live on the edge that captured it and not on the sibling edge,
        so a later step cannot read a value the route it took never produced.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            verify = root / "workflows" / "verify.yaml"
            text = verify.read_text(encoding="utf-8")
            text = text.replace("  confirmed: {}", "  confirmed:\n    record: finding")
            text = text.replace(
                "  confirm:\n    return:\n      outcome: confirmed",
                "  confirm:\n    return:\n      outcome: confirmed\n      with:\n"
                "        summary: {from: input.finding.summary}\n"
                "        tags: {from: input.finding.tags}",
            )
            verify.write_text(text, encoding="utf-8")
            run = root / "workflows" / "run.yaml"
            run.write_text(
                run.read_text(encoding="utf-8").replace(
                    "      confirmed: report",
                    "      confirmed:\n        next: report\n        as: verified",
                ),
                encoding="utf-8",
            )
            _, result, diagnostics = compiled(root)
            self.assertEqual(set(), error_codes(diagnostics))
            graph = result.graphs["run"]
            self.assertEqual(
                "record finding", graph.types[("result", "verified")].render()
            )
            self.assertIn(("result", "verified"), graph.available["report"])
            self.assertNotIn(("result", "verified"), graph.available["decline"])

    # 11. every decision, gate, call, and return outcome handled

    def test_case_11_every_decision_gate_call_and_return_outcome_is_handled(self):
        """Every declared outcome is returned, and every mapped one handled.

        Dropping one call outcome from the source is reported, so a route the
        callee can take never leaves the caller with nowhere to go.
        """
        kinds = {node.kind for node in self.nodes}
        self.assertLessEqual({"decision", "gate", "call", "branch", "return"}, kinds)
        returned = {node.outcome for node in self.nodes if node.kind == "return"}
        declared = {
            outcome.id
            for workflow in self.lowered.workflows
            for outcome in workflow.workflow.outcomes
        }
        self.assertEqual(declared, returned)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            run = root / "workflows" / "run.yaml"
            run.write_text(
                run.read_text(encoding="utf-8").replace(
                    "      rejected: decline\n", ""
                ),
                encoding="utf-8",
            )
            _, _, diagnostics = compiled(root)
            self.assertIn("workflow.unhandled-outcome", error_codes(diagnostics))

    # 12. a required script or asset carried by a typed action `resource`

    def test_case_12_a_required_script_is_carried_by_a_typed_resource(self):
        """The node names the operation and the path, and fails closed.

        A resource the manifest stops selecting is reported rather than
        rendered as a path the bundle does not ship.
        """
        carrying = [node for node in self.nodes if node.resource_operation]
        self.assertTrue(carrying, "the fixture declares no action resource")
        for node in carrying:
            with self.subTest(node=node.label):
                self.assertIn(node.resource_operation, ("run", "read", "copy", "fill"))
                module = next(
                    text
                    for text in self.rendered.execution_modules.values()
                    if f"[`{node.label}`]" in text
                )
                self.assertIn(node.resource_path, module)
                self.assertIn("blocked", module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            run = root / "workflows" / "run.yaml"
            run.write_text(
                run.read_text(encoding="utf-8").replace(
                    "      run: scripts/greet.py", "      run: scripts/absent.py"
                ),
                encoding="utf-8",
            )
            _, _, diagnostics = compiled(root)
            self.assertIn("resource.not-selected", error_codes(diagnostics))

    # 13. a missing required execution module making the bundle invalid or
    #     `blocked`

    def test_case_13_a_missing_required_execution_module_fails_closed(self):
        """Every module a reference names is one the build writes, and says blocked.

        Deleting one from a built bundle leaves the instruction that names it
        behind, so the absence is detectable at runtime instead of being
        silently skipped. The disposition for a module that cannot be read is
        stated once, in the contract that defines what a qualified reference
        means, rather than repeated on every boundary that uses one.
        """
        named = set(MODULE_REFERENCE.findall(self.rendered.skill_text))
        named |= set(MODULE_REFERENCE.findall(self.execution_text))
        self.assertTrue(named)
        written = {module_stem(path) for path in self.rendered.execution_modules}
        placed = {
            label
            for text in self.rendered.execution_modules.values()
            for label in re.findall(r"^### \[`(n-[0-9a-f]{10})`\]", text, re.M)
        }
        for module, node in named:
            with self.subTest(reference=f"{module}:{node}"):
                # A reference names a module the build writes, at a node that
                # module carries, so neither can go missing unnoticed.
                self.assertIn(module, written)
                self.assertIn(node, placed)
        contract = self.rendered.skill_text.split("## Execution contract", 1)[1]
        self.assertIn("blocked", contract.split("\n## ", 1)[0])
        start = self.rendered.skill_text.split("## Start", 1)[1]
        self.assertRegex(start, MODULE_REFERENCE)
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(ALPHA, Path(directory))[0]
            stem = sorted(module for module, _ in named)[0]
            victim = f"execution/{stem}.md"
            self.assertIn(victim, folder_names(artifact))
            (artifact / victim).unlink()
            self.assertNotIn(victim, folder_names(artifact))
            remaining = folder_text(artifact, "SKILL.md") + "\n".join(
                folder_text(artifact, path)
                for path in self.rendered.execution_modules
                if path != victim
            )
            # The reference that sent an agent there is still in the bundle, so
            # the module's absence is met by an instruction rather than silence.
            self.assertIn(f"{stem}:", remaining)

    # 14. deleting supplementary references leaving binding behavior intact

    def test_case_14_deleting_supplementary_references_keeps_execution(self):
        """Removing the whole references tree changes no executed byte.

        Supplementary documentation can go missing in an installed bundle
        without changing what the skill requires of the agent.
        """
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(ALPHA, Path(directory))[0]
            before = {
                path: folder_text(artifact, path)
                for path in self.rendered.execution_modules
            }
            before_root = folder_text(artifact, "SKILL.md")
            shutil.rmtree(artifact / "references")
            self.assertEqual(before_root, folder_text(artifact, "SKILL.md"))
            self.assertEqual(
                before,
                {
                    path: folder_text(artifact, path)
                    for path in self.rendered.execution_modules
                },
            )

    # 15. deterministic source-readable node ids and output bytes

    def test_case_15_readable_node_ids_and_output_bytes_are_deterministic(self):
        """Compiling twice and building twice both produce the same result.

        Labels are unique, source-readable, and content-derived rather than
        order-derived, and
        two archives built from one source compare equal byte for byte.
        """
        labels = [node.label for node in self.nodes]
        self.assertEqual(len(labels), len(set(labels)))
        for label in labels:
            with self.subTest(label=label):
                self.assertRegex(label, NODE_ID)
        _, again, _ = compiled(ALPHA)
        self.assertEqual(labels, [node.label for node in again.lowered.all_nodes()])
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = build_skills(ALPHA, Path(first), as_zip=True)[0]
            two = build_skills(ALPHA, Path(second), as_zip=True)[0]
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                names = set(archive.namelist())
            self.assertIn("SKILL.md", names)
            self.assertTrue(any(name.startswith("execution/") for name in names))

    # 16. a large linear workflow whose generated size grows about linearly

    def test_case_16_a_large_linear_workflow_grows_about_linearly(self):
        """Doubling the steps roughly doubles the bytes, and no worse.

        Each step leaves a value live that nothing later reads, so a renderer
        printing the live set instead of the actual reads would grow with the
        square of the step count.
        """
        sizes: dict[int, int] = {}
        for steps in (40, 80):
            with tempfile.TemporaryDirectory() as directory:
                skill = linear_skill(Path(directory), steps)
                _, result, diagnostics = compiled(skill)
                self.assertEqual(set(), error_codes(diagnostics))
                sizes[steps] = sum(
                    len(text.encode("utf-8"))
                    for text in result.rendered.execution_modules.values()
                )
        doubled = sizes[80] / sizes[40]
        self.assertLess(doubled, 2.5, f"doubling the steps multiplied bytes by {doubled:.2f}")
        per_step = sizes[80] / 80
        self.assertLess(per_step, (sizes[40] / 40) * 1.1)

    # 17. a bounded root with large reachable execution moved into `execution/`

    def test_case_17_a_bounded_root_holds_large_execution_in_modules(self):
        """The root stays small while the execution it points at does not.

        A workflow far larger than the root's budget compiles with every node
        under `execution/`, each module within its own larger budget.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = linear_skill(Path(directory), 250)
            _, result, diagnostics = compiled(skill)
            self.assertEqual(set(), error_codes(diagnostics))
            rendered = result.rendered
            root_bytes = len(rendered.skill_text.encode("utf-8"))
            module_bytes = [
                len(text.encode("utf-8"))
                for text in rendered.execution_modules.values()
            ]
            self.assertLess(root_bytes, ROOT_BUDGET_BYTES)
            self.assertGreater(sum(module_bytes), ROOT_BUDGET_BYTES)
            self.assertLessEqual(max(module_bytes), MODULE_BUDGET_BYTES)
            self.assertTrue(
                all(
                    path.startswith("execution/")
                    for path in rendered.execution_modules
                )
            )

    def test_case_17_the_fixture_root_also_stays_within_budget(self):
        """The same two budgets over the fixture every other case reads."""
        self.assertLess(
            len(self.rendered.skill_text.encode("utf-8")), ROOT_BUDGET_BYTES
        )
        for path, text in self.rendered.execution_modules.items():
            with self.subTest(path=path):
                self.assertLessEqual(
                    len(text.encode("utf-8")), MODULE_BUDGET_BYTES
                )

    # 18. every diagnostic and `explain` entry

    def test_case_18_every_diagnostic_has_an_explanation_and_the_reverse(self):
        """The emitted codes and the explained codes are the same set.

        A code with no entry cannot be looked up, and an entry with no
        emitter describes a check the compiler never runs.
        """
        emitted = emitted_check_codes()
        explained = set(checks())
        self.assertEqual(set(), emitted - explained)
        self.assertEqual(set(), explained - emitted)

    # 19. a dense workflow partitioned by what a module costs to load

    def test_case_19_dense_nodes_partition_by_bytes_not_by_node_count(self):
        """What decides a module boundary is the size of the load it creates.

        Case 17 holds thin nodes to the budget, which a fixed node count also
        satisfies by accident. Nodes carrying long commands are what separate
        the two: the same count of them is several times the budget, so a
        partition that counted nodes emitted a module no agent could read in
        one go. Both shapes must land under the same limit, and the dense one
        must reach more modules to do it.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = dense_skill(Path(directory), 60)
            _, result, diagnostics = compiled(skill)
            self.assertEqual(set(), error_codes(diagnostics))
            modules = result.rendered.execution_modules
            self.assertGreater(len(modules), 1)
            for path, text in modules.items():
                with self.subTest(path=path):
                    self.assertLessEqual(
                        len(text.encode("utf-8")), MODULE_BUDGET_BYTES
                    )
            # Every node still reaches exactly one module, so partitioning
            # loses none of them on the way.
            placed = sum(text.count("\n### ") for text in modules.values())
            self.assertEqual(len(list(result.lowered.all_nodes())), placed)

    # 20. a module entered in the middle, stating no entry it does not hold

    def test_case_20_only_the_module_holding_the_entry_node_names_one(self):
        """A partitioned workflow never sends an agent to a node it lacks.

        Every module repeats its workflow's header, so a continuation that
        repeated the entry field would name a node that file does not carry.
        An agent arriving there by an explicit load would look for it, fail,
        and return `blocked` at a workflow with nothing wrong with it. What a
        continuation states instead is which part of the workflow it is, so a
        reader knows more of it exists; where to enter is settled once, in the
        root's execution contract.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = dense_skill(Path(directory), 60)
            _, result, _ = compiled(skill)
            modules = result.rendered.execution_modules
            self.assertGreater(len(modules), 1)
            entries = {item.workflow.id: item.entry for item in result.lowered.workflows}
            parts = Counter(
                module_stem(path).rsplit("-", 1)[0] for path in modules
            )
            named = 0
            for path, text in sorted(modules.items()):
                identifier, _, number = module_stem(path).rpartition("-")
                with self.subTest(path=path):
                    held = set(re.findall(r"^### \[`([^`]+)`\]", text, re.M))
                    declared = re.search(
                        rf"\*\*{re.escape(wording.WORKFLOW_ENTRY)}\*\* `([^`]+)`", text
                    )
                    if parts[identifier] > 1:
                        self.assertIn(
                            f"({int(number)}/{parts[identifier]})", text
                        )
                    if declared is None:
                        continue
                    named += 1
                    self.assertIn(declared.group(1), held)
                    self.assertIn(declared.group(1), entries.values())
            # Exactly the modules holding a workflow entry name one.
            self.assertEqual(len(entries), named)

    # 21. every generated page reachable from the root by following links

    def test_case_21_every_generated_page_is_reachable_from_the_root(self):
        """A bundle ships no page the contract forbids an agent to open.

        Execution starts at `SKILL.md` and goes where it is sent, so a page
        nothing points at is weight that ships and never opens. Reachability is
        walked rather than counted: a page linked only from another unreachable
        page satisfies a link count and still arrives nowhere.
        """
        corpus = {
            "SKILL.md": self.rendered.skill_text,
            **self.rendered.execution_modules,
            **self.rendered.pages,
            **{
                path.relative_to(self.skill.root).as_posix(): path.read_text(encoding="utf-8")
                for path in self.result.content.copied("references")
            },
        }
        seen, frontier = {"SKILL.md"}, ["SKILL.md"]
        while frontier:
            source = frontier.pop()
            text = corpus[source]
            # The three ways generated text names a file it sends a reader to:
            # a qualified node reference for a module, a link for a page —
            # written relative to the page carrying it — and a bare path for
            # the profile index.
            targets = [
                f"execution/{module}.md"
                for module, _ in MODULE_REFERENCE.findall(text)
            ]
            targets += [
                posixpath.normpath(posixpath.join(posixpath.dirname(source), link))
                for link in re.findall(r"\]\(([^)]+)\)", text)
            ]
            if source == "SKILL.md" and "`profiles/index.md`" in text:
                targets.append("profiles/index.md")
            for target in targets:
                if target in corpus and target not in seen:
                    seen.add(target)
                    frontier.append(target)
        self.assertTrue(self.rendered.pages)
        self.assertEqual(set(), set(corpus) - seen)

    # 22. partitioning reduces reading along mutually exclusive execution paths

    def test_case_22_partitioning_optimizes_the_path_an_agent_reads(self):
        """Interleaved branches must not make every run read both bodies."""
        with tempfile.TemporaryDirectory() as directory:
            _, result, diagnostics = compiled(branching_skill(Path(directory)))
            self.assertEqual(set(), error_codes(diagnostics))
            worst, loads, total, largest = loaded_cost(result)
            self.assertLess(worst, total * 0.8)
            self.assertLessEqual(largest, MODULE_BUDGET_BYTES)
            self.assertEqual(worst, result.rendered.execution_path_bytes)
            self.assertEqual(loads, result.rendered.execution_path_loads)

    # 23. a prohibiting provision renders as the negative command it means

    def test_case_23_a_prohibiting_check_states_the_negative_it_means(self):
        """A prohibition's own sentence names the thing not to do.

        Rendered as a heading that sentence reads as an instruction to perform
        it, and an agent skimming headings would act on the very thing the
        provision refuses. So the heading states the negative, and the source's
        own sentence is kept in the field beneath it, which is what a blocked
        run reports as refused. Both halves are the guarantee: a heading that
        merely labels the node loses the command, and a negative heading alone
        loses the wording the author wrote.

        This is the shape a prohibition placed alone at a boundary takes, which
        is the shape that has a heading to get wrong. Where a construct placed
        several obligations here, the node's heading is the compiler's own and
        each prohibition keeps its sentence under its own label instead; case
        31 reads that shape.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = prohibiting_gate_skill(Path(directory))
            # A one-byte budget makes every edge between nodes cross a module,
            # so the later gate exercises the load form as well as its heading.
            with mock.patch("degardis.render.MODULE_BUDGET_BYTES", 1):
                _, result, _ = compiled(skill)
            modules = result.rendered.execution_modules
            checks = [
                item
                for item in result.lowered.all_nodes()
                if item.kind == "check" and item.prohibits
            ]
            self.assertEqual(2, len(checks))
            all_text = "\n".join(modules.values())
            for node in checks:
                with self.subTest(node=node.label):
                    self.assertEqual((), node.checks)
                    block = next(
                        part for part in re.split(r"(?m)(?=^### )", all_text)
                        if part.startswith(f"### [`{node.label}`]")
                    )
                    heading = NODE_HEADING.search(block)["command"]
                    # The negative of a sentence carries the sentence, so the
                    # command's own words past its first letter have to survive
                    # into the heading; only its opening case may move. A
                    # heading equal to the command would be the instruction to
                    # do it, and one that dropped these words would name no
                    # command at all.
                    self.assertNotEqual(node.command, heading)
                    self.assertIn(node.command[1:], heading)
                    self.assertTrue(heading.endswith("."), heading)
                    self.assertIn(f"**{wording.PROHIBITED}** {node.command}", block)
            headings = {
                match["label"]: match["command"]
                for text in modules.values()
                for match in NODE_HEADING.finditer(text)
            }
            workflow = result.lowered.workflows[0]
            entry = next(item for item in workflow.nodes if item.label == workflow.entry)
            all_modules = "\n".join(modules.values())
            self.assertIn(
                f"**{wording.WORKFLOW_ENTRY}** `{entry.label}` - "
                f"{headings[entry.label]}",
                all_modules,
            )
            self.assertIn(
                f":{entry.label}` — {headings[entry.label]}",
                result.rendered.skill_text,
            )
            later = next(item for item in checks if item is not entry)
            self.assertIn(
                f":{later.label}` — {headings[later.label]}",
                all_modules,
            )

    # 24. routing a request costs the root and one module, whatever the shape
    #     of the workflow the route enters

    def test_case_24_routing_reads_no_module_to_decide_where_to_begin(self):
        """The root names each route's first node, so nothing is read to choose.

        Routing expressed as ordinary execution costs an agent every module it
        has to read before the work starts, and how many that is depends on how
        the author shaped the entered workflow and how the partitioner split
        it. Here every route's own first node is named in the file the host has
        already loaded, so the first additional read is the module that does
        the work rather than one that decides which work it is.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = routed_skill(
                Path(directory), ("audit", "gaps", "summary"), catch_all=True
            )
            _, result, diagnostics = compiled(skill)
            self.assertEqual(set(), error_codes(diagnostics))
            start = result.rendered.skill_text.split(
                f"## {wording.START_HEADING}", 1
            )[1]
            named = MODULE_REFERENCE.findall(start)
            self.assertEqual(3, len(named))
            entries = {
                item.entry: item.workflow.id for item in result.lowered.workflows
            }
            for module, label in named:
                with self.subTest(route=module):
                    # The node named is the entered workflow's own entry, and
                    # the module named is one the build actually writes.
                    self.assertIn(label, entries)
                    self.assertIn(
                        f"execution/{module}.md", result.rendered.execution_modules
                    )
                    self.assertIn(
                        label, result.rendered.execution_modules[f"execution/{module}.md"]
                    )

    # 25. a request no route recognizes stops the run

    def test_case_25_an_unmatched_request_returns_blocked(self):
        """Routing fails closed, the way every compiler-generated edge does.

        A skill whose routes all state a condition may be handed a request none
        of them describes. Falling through to whichever route came last would
        start work the source never said applied to it, so the table ends by
        returning the compiler's own outcome instead.
        """
        with tempfile.TemporaryDirectory() as directory:
            skill = routed_skill(Path(directory), ("audit", "gaps"), catch_all=False)
            _, result, diagnostics = compiled(skill)
            self.assertEqual(set(), error_codes(diagnostics))
            start = result.rendered.skill_text.split(
                f"## {wording.START_HEADING}", 1
            )[1]
            self.assertEqual(2, len(MODULE_REFERENCE.findall(start)))
            self.assertIn(BLOCKED_OUTCOME, start)
            self.assertNotIn(wording.START_OTHERWISE, start)

    # 26. routing does not decide how execution is partitioned

    def test_case_26_adding_a_route_leaves_module_layout_unchanged(self):
        """What an entrypoint changes is where a run starts, not what it reads.

        A route is chosen before any module is loaded, so it cannot be allowed
        to move a boundary inside the workflow it enters. If it could, adding a
        second way in would rewrite the first one's modules and every node id
        an existing bundle had already published.
        """
        with tempfile.TemporaryDirectory() as directory:
            one = Path(directory) / "one"
            two = Path(directory) / "two"
            one.mkdir()
            two.mkdir()
            _, single, _ = compiled(routed_skill(one, ("audit",), catch_all=True))
            _, both, _ = compiled(
                routed_skill(two, ("audit", "gaps"), catch_all=True)
            )
            shared = set(single.rendered.execution_modules) & set(
                both.rendered.execution_modules
            )
            self.assertIn("execution/audit-01.md", shared)
            for path in sorted(shared):
                with self.subTest(module=path):
                    self.assertEqual(
                        single.rendered.execution_modules[path],
                        both.rendered.execution_modules[path],
                    )

    # 27. every protocol frame opens with its declared state and data

    def test_case_27_protocol_frames_render_their_initial_state_and_data(self):
        """A generated frame begins with the values its hooks are checked against.

        Both ways a field can begin are stated: one with a declared `default`
        holds it from the moment the frame opens, and an optional one with none
        begins cleared. A frame that stated neither would leave a hook checked
        against data the run was never told it had.
        """
        protocol = self.sources.protocols["run-trail"]
        initialized = [
            node
            for node in self.nodes
            if node.kind == "initialize" and node.origin == f"protocol:{protocol.id}"
        ]
        self.assertTrue(initialized)
        for node in initialized:
            self.assertIn(f"state `{protocol.initial}`", node.command)
            self.assertIn("state.finding", node.state_update)
            self.assertIn(node.command, self.execution_text)
            self.assertIn(node.state_update, self.execution_text)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            with edit_yaml(root / "protocols" / "run-trail.yaml") as data:
                # A list is the case a scalar-only literal could not state at
                # all, so a field that begins holding one had to be assigned by
                # a hook before anything could read it.
                data["data"]["seen"] = {"type": {"list": "string"}, "default": []}
                data["hooks"]["open-trail"]["verify"] = {
                    "expression": "length(state.seen) == 0"
                }
            _, result, diagnostics = compiled(root)
            self.assertEqual(set(), error_codes(diagnostics))
            text = "\n".join(result.rendered.execution_modules.values())
            opened = [
                node
                for node in result.lowered.all_nodes()
                if node.kind == "initialize" and node.origin == "protocol:run-trail"
            ]
            self.assertTrue(opened)
            for node in opened:
                self.assertIn("`state.seen`", node.state_update)
                self.assertIn("`[]`", node.state_update)
                self.assertIn("`state.finding`", node.state_update)
                self.assertIn(node.state_update, text)

    # 28. a `during` requirement carries its activation and its verification to
    #     the command it renders beside, and both are checked there

    def test_case_28_a_during_requirement_carries_its_proof_to_the_command(self):
        """An invariant has no node of its own, so its proof sits on the command.

        Every other phase generates a check node that states the verification
        the author declared and is refused when that verification names a gate
        no path reaches. A `during` item renders beside the command instead, so
        that node is where the verification has to appear and where the same
        refusal has to happen. A proof dropped on the way there is worse than a
        missing one: the checks that police it never run, so a verification
        naming a step that does not exist compiles clean.
        """
        provision = next(
            item
            for item in self.sources.policies["run-authority"].provisions
            if item.phase == "during"
        )
        self.assertIsNotNone(provision.verify, "the fixture states no `during` proof")
        gate = provision.verify.gate
        self.assertTrue(gate, "the fixture's `during` proof names no gate")
        carried = [
            node
            for node in self.nodes
            if any(item.local == provision.id for item in node.invariants)
        ]
        self.assertTrue(carried)
        for node in carried:
            invariant = next(
                item for item in node.invariants if item.local == provision.id
            )
            block = next(
                part
                for page in self.rendered.execution_modules.values()
                for part in re.split(r"(?m)(?=^### )", page)
                if part.startswith(f"### [`{node.label}`]")
            )
            lines = block.splitlines()
            label = wording.PROHIBITED if invariant.prohibits else wording.REQUIRED
            with self.subTest(node=node.label):
                # The proof is read off the line under the command it proves,
                # so an agent acting on one has the other in view.
                stated = lines.index(f"**{label}** {provision.command}")
                self.assertEqual(
                    f"**{wording.VERIFY}** {invariant.verify}", lines[stated + 1]
                )
                self.assertIn(f"gate.{gate}", invariant.verify)
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "alpha"
            shutil.copytree(ALPHA, copy, ignore=shutil.ignore_patterns("__pycache__"))
            policy = copy / "policies" / "run-authority.yaml"
            policy.write_text(
                policy.read_text(encoding="utf-8").replace(
                    f"gate: {gate}", "gate: reached-on-no-path"
                ),
                encoding="utf-8",
            )
            _, _, diagnostics = compiled(copy)
            self.assertIn("workflow.missing-gate", error_codes(diagnostics))

    # 29. a route states the value it supplies to the workflow it enters

    def test_case_29_a_route_states_the_value_it_supplies(self):
        """Two routes into one workflow are told apart by what each supplied.

        The entry node is the same node whichever route reached it, so it
        cannot say which one did. The route line can, and it is in the file the
        host has already loaded. A binding accepted and checked but rendered
        nowhere leaves the agent that took the route unable to learn what the
        route settled, which is the whole of what the binding is for.
        """
        declared = self.skill.manifest["entrypoints"]
        bound = {
            identifier: body["with"]
            for identifier, body in declared.items()
            if body.get("with")
        }
        self.assertTrue(bound, "the fixture declares no route binding")
        start = self.rendered.skill_text.split(f"## {wording.START_HEADING}", 1)[1]
        for identifier, supplied in bound.items():
            for name, binding in supplied.items():
                with self.subTest(route=identifier, input=name):
                    self.assertIn("literal", binding)
                    self.assertIn(f"`{name}`: `", start)
        # Only a route that binds something carries the field: a label on every
        # route would read as a value each of them settled.
        self.assertEqual(len(bound), start.count(f"**{wording.SUPPLIES}** "))

    # 30. a value produced on an optional path is read without a fallback step

    def test_case_30_a_defaulted_value_is_read_where_no_step_produced_it(self):
        """A default is what lets a workflow read what an optional stage found.

        Without one, a value produced on one arm of a branch is undefined at
        every reader past the join, and the only repair is a second step on the
        other arm whose whole job is to write the empty case. That step is not
        scaffolding a reader can skip: an author who will not write it composes
        from what the agent remembers instead, which is what declared values
        exist to prevent. The declaration states the empty case once, beside the
        description it has to agree with, and the header states it in every
        module of the workflow, so an agent that skipped the producing step
        still meets the value in the file it is already holding.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            run = root / "workflows" / "run.yaml"
            with edit_yaml(run) as data:
                steps = data["steps"]
                steps["route"]["branch"][0]["next"] = "widen"
                steps["widen"] = {
                    "action": "Name every neighbouring surface the wide change reaches.",
                    "produces": {"reached": {"type": {"list": "string"}}},
                    "next": "apply-wide",
                }
                steps["report"]["uses"] = ["result.reached"]
            _, result, diagnostics = compiled(root)
            self.assertIn("expr.undefined-value", error_codes(diagnostics))
            self.assertNotIn(("result", "reached"), result.graphs["run"].available["report"])

            with edit_yaml(run) as data:
                data["steps"]["widen"]["produces"]["reached"]["default"] = []
            _, result, diagnostics = compiled(root)
            self.assertEqual(set(), error_codes(diagnostics))
            graph = result.graphs["run"]
            # The narrow arm produces nothing, and the reader past the join
            # still holds the value, because the default defined it at entry.
            self.assertIn(("result", "reached"), graph.available["report"])
            self.assertIn(("result", "reached"), graph.available["apply-narrow"])
            self.assertEqual(
                (),
                result.lowered.sources.workflows["run"].step("apply-narrow").produces,
            )
            stated = "**{label}** {item}".format(
                label=wording.WORKFLOW_DEFAULTS,
                item=wording.WORKFLOW_DEFAULT.format(
                    name="reached", type="list of string", value="[]"
                ),
            )
            carrying = [
                text
                for text in result.rendered.execution_modules.values()
                if f"**{wording.WORKFLOW_ID}** `run`" in text
            ]
            self.assertTrue(carrying)
            for text in carrying:
                self.assertIn(stated, text)

    # 31. several checks from one construct at one boundary are one node

    def test_case_31_adjacent_checks_of_one_construct_are_one_node(self):
        """A boundary states its obligations once, and a failure names the item.

        One node per provision made an agent read a heading, a label, and an
        edge pair for each of them to reach a single boundary. Grouping moves
        the granularity from the node to the item inside it, which the blocked
        edge already asks for: it names the command or verification that
        failed, not the node's own sentence. What may not be lost is any item —
        every provision still renders its own sentence verbatim, keeps its own
        obligation, and is still reported as lowered — nor the construct that
        placed it, which is why grouping stops at one construct.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            policy = root / "policies" / "workflow-scope.yaml"
            extra = {
                "name-the-reader": (
                    "require",
                    "Name the reader this report is written for.",
                ),
                "no-second-subject": (
                    "prohibit",
                    "Carry a second subject into the report.",
                ),
            }
            with edit_yaml(policy) as data:
                for identifier, (obligation, sentence) in extra.items():
                    data["provisions"][identifier] = {
                        "phase": "before",
                        "match": {"subjects": ["report.write"]},
                        obligation: sentence,
                    }
                declared = data["provisions"]
            _, result, diagnostics = compiled(root)
            self.assertEqual(set(), error_codes(diagnostics))
            nodes = [
                node
                for node in result.lowered.all_nodes()
                if node.kind == "check"
                and node.origin == "policy:workflow-scope"
                and node.phase == "before"
            ]
            self.assertEqual(1, len(nodes))
            (node,) = nodes
            self.assertEqual(len(declared), len(node.checks))

            text = "\n".join(result.rendered.execution_modules.values())
            block = next(
                part for part in re.split(r"(?m)(?=^### )", text)
                if part.startswith(f"### [`{node.label}`]")
            )
            for identifier, body in declared.items():
                with self.subTest(provision=identifier):
                    prohibits = "prohibit" in body
                    sentence = (body.get("require") or body["prohibit"]).replace("\n", " ")
                    label = wording.PROHIBITED if prohibits else wording.REQUIRED
                    self.assertIn(f"**{label}** {sentence}", block)
                    self.assertIn(
                        ("workflow-scope", identifier), result.lowered.lowered_provisions
                    )
            # The failure edge is what carries per-item diagnosability, and it
            # asks for the command that failed rather than for the node's own.
            self.assertIn(f"- {wording.ON_FAILURE}", block)
            # A rule at the same boundary is its own node, so which construct
            # placed an obligation survives the grouping.
            at_change = {
                found.origin
                for found in result.lowered.all_nodes()
                if found.kind == "check"
                and found.step == "apply-narrow"
                and found.phase == "before"
            }
            self.assertEqual({"policy:run-authority", "rule:scoped-change"}, at_change)

    # 32. a link to a supplementary document is named by that document

    def test_case_32_a_link_to_a_reference_states_what_it_opens(self):
        """An agent decides whether to open a document from what it is called.

        A link naming its own path leaves that decision to a directory and a
        filename, so the reference states its name in a heading and the link
        carries it. The path stays in the link target, where following it is
        what a path is for.
        """
        targets = {
            target
            for construct in (
                *self.sources.patterns.values(),
                *self.sources.heuristics.values(),
                *self.sources.guidance.values(),
                *self.sources.profiles.values(),
            )
            for target in construct.references
        }
        self.assertTrue(targets, "the fixture names no reference, so nothing is tested")
        linked = set()
        for path, page in self.rendered.pages.items():
            for match in MARKDOWN_LINK.finditer(page):
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(path), match.group("target"))
                )
                if resolved not in targets:
                    continue
                linked.add(resolved)
                heading = (self.skill.root / resolved).read_text(
                    encoding="utf-8"
                ).splitlines()[0]
                with self.subTest(page=path, target=resolved):
                    self.assertTrue(heading.startswith("# "), heading)
                    self.assertEqual(heading[2:].strip(), match.group("text"))
        self.assertEqual(targets, linked)

    def test_a_required_load_is_not_labeled_as_optional_documentation(self):
        """A load the agent must perform is never dressed as further reading.

        The fixture's titles are misleading on purpose, so the start section
        has to name the module and the entry node rather than invite the agent
        to judge the module by its name. The blocked disposition is stated
        once, in the contract above it.
        """
        skill_text = self.rendered.skill_text
        start = skill_text.split("## Start", 1)[1]
        self.assertRegex(start, MODULE_REFERENCE)
        self.assertNotIn("optional", start.casefold())
        contract = skill_text.split("## Execution contract", 1)[1]
        self.assertIn("blocked", contract.split("\n## ", 1)[0])


if __name__ == "__main__":
    unittest.main()
