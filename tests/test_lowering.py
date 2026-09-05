"""Lowering semantics independent of generated Markdown layout.

Expectations come from the format rather than from the compiler: a node label is
built from the label algorithm, a scope's placement from what that scope binds,
and a refusal from the check code the format says applies. A test that reads its
expectation out of `lowering.py` records where a value currently sits.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from degardis.lowering import node_label
from tests.support import codes, compiled, copy_skills, edit_workflow, edit_yaml, write_text


ALPHA = Path("tests/fixtures/skills/demo/alpha")
NODE_ID = re.compile(r"^n-[0-9a-f]{10}$")


def find_node(result, **attrs):
    return next(
        node
        for node in result.lowered.all_nodes()
        if all(getattr(node, key) == value for key, value in attrs.items())
    )


class NodeIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.result, cls.diagnostics = compiled(ALPHA)
        cls.nodes = list(cls.result.lowered.all_nodes())

    def test_runtime_ids_are_short_deterministic_and_unique(self):
        """A label costs its length on the node and on every edge to it.

        Spelling out workflow, step, phase, kind, and construct reached a
        hundred characters on a real skill and was paid every time the node
        was named. The digest is over that same identity, so compiling twice
        produces the same labels.
        """
        labels = [node.label for node in self.nodes]
        self.assertTrue(all(NODE_ID.fullmatch(label) for label in labels))
        self.assertEqual(len(labels), len(set(labels)))
        _, second, _ = compiled(ALPHA)
        self.assertEqual(
            labels,
            [node.label for node in second.lowered.all_nodes()],
        )

    def test_full_provenance_remains_available_for_inspection(self):
        """What the label stopped carrying, the node still records.

        A short label is only affordable because nothing needs to read the
        source identity out of it: `source` keeps the whole of it for the
        reports that trace a node back.
        """
        node = find_node(self.result, workflow="run", step="inspect", origin="action")
        self.assertIn("workflow `run`, step `inspect`", node.source)
        self.assertEqual(node_label("run", "inspect"), node.label)

    def test_a_label_is_derived_from_the_identity_it_stands_for(self):
        """Different source identities get different labels, and only those.

        The suffix is part of the identity, so a generated check node and the
        node it constrains never answer to one label; nothing else about the
        compilation reaches the digest.
        """
        plain = node_label("run", "inspect")
        suffixed = node_label("run", "inspect", "before-policy-format-report")
        self.assertNotEqual(plain, suffixed)
        self.assertEqual(plain, node_label("run", "inspect"))
        # The separator is not a character an id may contain, so no two
        # identities can spell the same digest input.
        self.assertNotEqual(node_label("run", "inspect-x"), node_label("run-inspect", "x"))

    def test_pattern_application_expands_without_own_runtime_node(self):
        expanded = [
            node
            for node in self.nodes
            if node.workflow == "run"
            and node.step in {"apply-narrow", "apply-wide"}
            and node.kind == "procedure"
        ]
        self.assertEqual(6, len(expanded))
        self.assertFalse(
            any(
                node.workflow == "run"
                and node.step == "apply-narrow"
                and node.kind == "pattern"
                for node in self.nodes
            )
        )


    def test_pattern_item_checks_are_reached_before_the_next_item(self):
        """A direct procedure edge must not bypass its destination's checks."""
        workflow = next(item for item in self.result.lowered.workflows if item.workflow.id == "run")
        nodes = {node.label: node for node in workflow.nodes}
        seen = set()
        pending = [workflow.entry]
        while pending:
            label = pending.pop()
            if label in seen:
                continue
            seen.add(label)
            pending.extend(edge.target for edge in nodes[label].transitions if not edge.blocked)
        checks = {
            node.label for node in workflow.nodes
            if node.kind == "check" and node.step in {"apply-narrow", "apply-wide"}
        }
        self.assertTrue(checks)
        self.assertEqual(set(), checks - seen)


class DataFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.result, _ = compiled(ALPHA)

    def test_nodes_render_actual_reads_not_all_live_values(self):
        inspect = find_node(cls := self.result, workflow="run", step="inspect", origin="action")
        self.assertEqual(("input.request",), inspect.available)
        authorize = find_node(cls, workflow="run", step="authorization", origin="gate")
        self.assertEqual((), authorize.available)
        self.assertGreater(len(cls.graphs["run"].available["authorization"]), 0)

    def test_pattern_reads_are_translated_through_application_bindings(self):
        inspect_owner = next(
            node
            for node in self.result.lowered.all_nodes()
            if node.workflow == "run"
            and node.step == "apply-narrow"
            and node.kind == "procedure"
            and "inspect-owner" in node.source
        )
        self.assertIn("result.finding", inspect_owner.available)
        self.assertNotIn("input.target", inspect_owner.available)

    def test_effects_belong_to_the_procedure_item_that_performs_them(self):
        procedure = [
            node
            for node in self.result.lowered.all_nodes()
            if node.workflow == "run"
            and node.step == "apply-narrow"
            and node.kind == "procedure"
        ]
        effects = {node.source.split("procedure `", 1)[1].split("`", 1)[0]: node.effects for node in procedure}
        self.assertEqual((), effects["inspect-owner"])
        self.assertEqual((), effects["choose-plan"])
        self.assertEqual(("external.write",), effects["perform-change"])


class ControlFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.result, _ = compiled(ALPHA)
        cls.by_label = {node.label: node for node in cls.result.lowered.all_nodes()}

    def test_every_non_blocking_transition_targets_a_generated_node(self):
        for node in self.by_label.values():
            for transition in node.transitions:
                if transition.blocked:
                    continue
                with self.subTest(node=node.label, edge=transition.label):
                    self.assertIn(transition.target, self.by_label)
                    self.assertEqual(self.by_label[transition.target].command, transition.command)

    def test_binding_checks_fail_closed(self):
        for node in self.by_label.values():
            if node.kind not in {"check", "hook", "accepting"}:
                continue
            with self.subTest(node=node.label):
                self.assertTrue(any(edge.blocked for edge in node.transitions))

    def test_call_nodes_explicitly_name_the_callee(self):
        call = find_node(self.result, workflow="run", step="check-work", origin="use")
        self.assertEqual("verify", call.call_workflow)
        self.assertEqual({"confirmed", "rejected"}, {
            edge.label.split("`")[1] for edge in call.transitions
        })

    def test_before_and_after_obligations_keep_their_boundary_order(self):
        workflow = next(item for item in self.result.lowered.workflows if item.workflow.id == "run")
        positions = {node.label: index for index, node in enumerate(workflow.nodes)}
        action = next(
            node for node in workflow.nodes
            if node.step == "apply-narrow" and node.kind == "procedure" and "perform-change" in node.source
        )
        before = next(
            node for node in workflow.nodes
            if node.step == "apply-narrow" and node.phase == "before" and node.provision == "establish-authority"
        )
        after = next(
            node for node in workflow.nodes
            if node.step == "apply-narrow" and node.phase == "after" and node.provision == "report-effect"
        )
        self.assertLess(positions[before.label], positions[action.label])
        self.assertGreater(positions[after.label], positions[action.label])


class CallPayloadTests(unittest.TestCase):
    def test_a_record_bearing_outcome_can_be_captured_in_the_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "alpha"
            shutil.copytree(ALPHA, root)
            verify = root / "workflows" / "verify.yaml"
            text = verify.read_text()
            text = text.replace("  confirmed: {}", "  confirmed:\n    record: finding")
            text = text.replace(
                "  confirm:\n    return:\n      outcome: confirmed",
                "  confirm:\n    return:\n      outcome: confirmed\n      with:\n"
                "        summary: {from: input.finding.summary}\n"
                "        tags: {from: input.finding.tags}",
            )
            verify.write_text(text)
            run = root / "workflows" / "run.yaml"
            text = run.read_text().replace(
                "      confirmed: report",
                "      confirmed:\n        next: report\n        as: verified-finding",
            )
            run.write_text(text)
            _, result, diagnostics = compiled(root)
            self.assertEqual([], [item for item in diagnostics.records if item.severity == "error"])
            graph = result.graphs["run"]
            self.assertEqual("record finding", graph.types[("result", "verified-finding")].render())
            self.assertIn(("result", "verified-finding"), graph.available["report"])


class BindingReachTests(unittest.TestCase):
    """What a bound construct reached, and what it is when it reached nothing.

    A requirement no node states is a requirement no agent can act on, so each
    of these is the compiler saying the source declared something it could not
    place.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def test_a_bound_provision_matching_no_reachable_node_warns(self):
        with edit_yaml(self.skill / "policies" / "workflow-scope.yaml") as data:
            data["provisions"]["stay-on-subject"]["match"] = {
                "subjects": ["nothing.declares-this"]
            }
        self.assertIn("policy.unmatched-provision", codes(self.skill, "warning"))

    def test_a_selected_construct_nothing_reaches_warns(self):
        write_text(
            self.skill / "heuristics" / "unnamed.yaml",
            "question: Which option should be preferred?\n"
            "advice:\n"
            "  smaller:\n"
            "    prefer: Prefer the smaller option.\n",
        )
        self.assertIn("source.unbound-construct", codes(self.skill, "warning"))

    def test_binding_one_construct_at_two_nested_scopes_is_reported(self):
        """The narrower binding says nothing the wider one has not said."""
        with edit_workflow(self.root, "alpha", "run") as data:
            data["policies"] = ["workflow-scope", "run-authority"]
        self.assertIn("workflow.duplicate-binding", codes(self.skill))

    def test_a_pattern_read_the_pattern_does_not_declare_is_reported(self):
        with edit_yaml(self.skill / "patterns" / "inspect-plan-act.yaml") as data:
            data["procedure"]["choose-plan"]["uses"] = ["input.absent"]
        self.assertIn("pattern.invalid-use", codes(self.skill))

    def test_a_during_provision_matching_only_a_choice_is_reported(self):
        """A `during` item renders beside a command, and a gate states none.

        The selector matches the gate, so the provision is active rather than
        unmatched: reporting it as a selector that found nothing would leave a
        bound policy out of the document behind a warning.
        """
        with edit_yaml(self.skill / "policies" / "run-authority.yaml") as data:
            data["provisions"]["bound-to-a-choice"] = {
                "phase": "during",
                "match": {"forms": ["gate"]},
                "require": "Keep the choice inside the authority established.",
            }
        self.assertIn("policy.unlowered-provision", codes(self.skill))

    def test_an_active_hook_that_reached_no_node_is_reported(self):
        with edit_yaml(self.skill / "protocols" / "run-trail.yaml") as data:
            data["hooks"]["note-nothing"] = {
                "phase": "after",
                "match": {"subjects": ["nothing.declares-this"]},
                "from": list(data["states"]),
                "command": "Note what nothing in this workflow selects.",
            }
        self.assertIn("protocol.unlowered-hook", codes(self.skill, "warning"))

    def test_a_step_applying_a_pattern_nothing_selects_expands_into_nothing(self):
        with edit_workflow(self.root, "alpha", "run") as data:
            data["steps"]["apply-narrow"]["pattern"] = "absent-pattern"
        self.assertIn("pattern.unexpanded", codes(self.skill))


if __name__ == "__main__":
    unittest.main()
