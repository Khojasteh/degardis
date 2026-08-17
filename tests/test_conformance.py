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

from degardis import wording
from degardis.build import build_skills
from degardis.explain import CHECKS
from degardis.render import MODULE_BUDGET_BYTES, ROOT_BUDGET_BYTES
from tests.checkcodes import emitted_check_codes
from tests.support import compiled, folder_names, folder_text
from tests.test_planning import branching_skill, loaded_cost


ALPHA = Path("tests/fixtures/skills/demo/alpha")
NODE_ID = re.compile(r"^n-[0-9a-f]{10}$")
# How a module is named where an agent is sent to one: the stem of a generated
# module path, followed by the node it must continue at.
MODULE_REFERENCE = re.compile(r"`([a-z0-9][a-z0-9-]*-\d{2,}):(n-[0-9a-f]{10})`")


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
        "primary_workflow: run\n"
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
        selects; every other phase generates a check node of its own at that
        phase, so no bound provision is left without somewhere to be enforced.
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
                    and node.provision == provision.id
                    and node.phase == provision.phase
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
        order = [node.label for node in self.lowered.workflows[0].nodes]
        opened = next(node for node in self.nodes if node.hook == opens.id)
        spent = next(node for node in self.nodes if node.hook == spends.id)
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
            for text in (profile.title, profile.description, *profile.points)
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
        explained = set(CHECKS)
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
