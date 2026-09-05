"""Workflow control flow and value flow, checked over the source graph."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support import codes, copy_skills, edit_workflow, edit_yaml, write_text


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def run_workflow(self):
        return edit_workflow(self.root, "alpha", "run")

    def test_an_entry_that_is_not_a_step_is_reported(self):
        with self.run_workflow() as data:
            data["entry"] = "absent"
        self.assertIn("workflow.invalid-edge", codes(self.skill))

    def test_a_successor_that_is_not_a_step_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["report"]["next"] = "absent"
        self.assertIn("workflow.invalid-edge", codes(self.skill))

    def test_a_step_nothing_reaches_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["orphan"] = {
                "action": "Do something nothing reaches.",
                "next": "finish",
            }
        self.assertIn("workflow.unreachable", codes(self.skill))

    def test_a_cycle_is_reported(self):
        """Format 2 workflows run forward, so a repeated stage is a step of its
        own rather than an edge back."""
        with self.run_workflow() as data:
            data["steps"]["report"]["next"] = "inspect"
        self.assertIn("workflow.invalid-edge", codes(self.skill))

    def test_a_call_cycle_is_reported(self):
        with edit_workflow(self.root, "alpha", "verify") as data:
            data["steps"]["recheck"] = {
                "use": "run",
                "with": {"request": {"literal": "again"}, "wide": {"literal": False}},
                "on": {"reported": "decide-verdict", "declined": "decide-verdict"},
            }
        self.assertIn("workflow.invalid-edge", codes(self.skill))

    def test_a_callee_outcome_left_unmapped_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["on"].pop("rejected")
        self.assertIn("workflow.unhandled-outcome", codes(self.skill))

    def test_a_mapped_outcome_the_callee_does_not_declare_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["on"]["invented"] = "report"
        self.assertIn("workflow.unhandled-outcome", codes(self.skill))

    def test_a_return_naming_an_undeclared_outcome_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["finish"]["return"]["outcome"] = "invented"
        self.assertIn("workflow.unhandled-outcome", codes(self.skill))

    def test_a_declared_outcome_no_return_produces_is_reported(self):
        with self.run_workflow() as data:
            data["outcomes"]["unused"] = {}
        self.assertIn("workflow.unhandled-outcome", codes(self.skill))

    def test_the_compiler_owned_outcome_cannot_be_declared(self):
        with self.run_workflow() as data:
            data["outcomes"]["blocked"] = {}
        self.assertIn("workflow.reserved-outcome", codes(self.skill))

    def test_the_compiler_owned_outcome_cannot_be_returned(self):
        with self.run_workflow() as data:
            data["steps"]["decline"]["return"]["outcome"] = "blocked"
        self.assertIn("workflow.reserved-outcome", codes(self.skill))

    def test_the_compiler_owned_outcome_cannot_be_mapped_by_a_call(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["on"]["blocked"] = "decline"
        self.assertIn("workflow.reserved-outcome", codes(self.skill))

    def test_a_call_naming_a_workflow_nothing_selects_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["use"] = "absent"
        found = codes(self.skill)
        self.assertIn("source.unknown-reference", found)
        self.assertIn("workflow.invalid-edge", found)

    def test_a_workflow_no_call_reaches_warns(self):
        write_text(
            self.skill / "workflows" / "spare.yaml",
            """title: Spare
description: A workflow nothing calls.
outcomes:
  done: {}
entry: act
steps:
  act:
    action: Do the spare thing.
    next: finish
  finish:
    return:
      outcome: done
""",
        )
        self.assertIn("workflow.unreached", codes(self.skill, "warning"))


class ValueFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def run_workflow(self):
        return edit_workflow(self.root, "alpha", "run")

    def test_a_read_of_a_value_no_step_produces_is_reported(self):
        with self.run_workflow() as data:
            data["steps"]["inspect"]["uses"] = ["result.absent"]
        self.assertIn("expr.unknown-value", codes(self.skill))

    def test_a_read_before_every_path_produced_it_is_reported(self):
        """`result.report` is produced on the reporting route only, so reading
        it on the declining route has no answer there."""
        with self.run_workflow() as data:
            data["steps"]["decline"]["return"] = {"outcome": "declined"}
            data["steps"]["authorization"]["states"]["refused"]["next"] = "report"
            data["steps"]["inspect"]["uses"] = ["result.report"]
        self.assertIn("expr.undefined-value", codes(self.skill))

    def test_a_call_must_supply_every_declared_input(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"].pop("with")
        self.assertIn("value.missing-binding", codes(self.skill))

    def test_a_call_cannot_supply_what_the_callee_does_not_declare(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["with"]["extra"] = {"literal": 1}
        self.assertIn("value.unknown-binding", codes(self.skill))

    def test_a_supplied_value_must_fit_its_destination(self):
        with self.run_workflow() as data:
            data["steps"]["check-work"]["with"]["finding"] = {"literal": "text"}
        self.assertIn("value.mistyped-binding", codes(self.skill))

    def test_an_outcome_naming_an_unselected_record_is_reported_once(self):
        """One missing record is one problem, so it carries one code.

        The reference check owns it: `source.unknown-reference` names what the
        manifest does not select, and a second finding under a value code would
        send the author looking for a second repair.
        """
        with self.run_workflow() as data:
            data["outcomes"]["reported"]["record"] = "absent-record"
        found = codes(self.skill)
        self.assertIn("source.unknown-reference", found)
        self.assertNotIn("value.unknown-binding", found)

    def test_a_return_must_supply_every_field_of_its_record(self):
        with self.run_workflow() as data:
            data["steps"]["finish"]["return"]["with"].pop("count")
        self.assertIn("value.missing-binding", codes(self.skill))

    def test_a_return_cannot_supply_a_field_the_record_lacks(self):
        with self.run_workflow() as data:
            data["steps"]["finish"]["return"]["with"]["extra"] = {"literal": 1}
        self.assertIn("value.unknown-binding", codes(self.skill))

    def test_a_return_with_no_record_supplies_nothing(self):
        with self.run_workflow() as data:
            data["steps"]["decline"]["return"]["with"] = {"summary": {"literal": "x"}}
        self.assertIn("value.unknown-binding", codes(self.skill))

    def test_two_steps_declaring_one_value_differently_are_reported(self):
        with self.run_workflow() as data:
            data["steps"]["report"]["produces"]["finding"] = {"type": "string"}
        self.assertIn("workflow.conflicting-value", codes(self.skill))

    def test_a_record_nothing_selects_is_reported(self):
        with self.run_workflow() as data:
            data["outcomes"]["reported"]["record"] = "absent"
        self.assertIn("source.unknown-reference", codes(self.skill))

    def test_a_branch_condition_is_type_checked(self):
        with self.run_workflow() as data:
            data["steps"]["route"]["branch"][0]["when"] = "input.request == 1"
        self.assertIn("expr.type-mismatch", codes(self.skill))


class GateVerificationTests(unittest.TestCase):
    """A check verified by a gate reads that gate's decision, so the gate has
    to lie on every path to the node the check constrains."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def test_a_gate_that_does_not_dominate_is_reported(self):
        with edit_yaml(self.skill / "policies" / "run-authority.yaml") as data:
            data["provisions"]["establish-authority"]["verify"] = {"gate": "absent"}
        self.assertIn("workflow.missing-gate", codes(self.skill))

    def test_a_verification_naming_a_heuristic_is_reported(self):
        with edit_yaml(self.skill / "policies" / "run-authority.yaml") as data:
            data["provisions"]["establish-authority"]["verify"] = {
                "gate": "smallest-change"
            }
        self.assertIn("heuristic.used-as-authority", codes(self.skill))

    def test_capturing_an_outcome_that_carries_no_record_is_reported(self):
        """There is nothing to capture: the callee returns the outcome alone."""
        with edit_workflow(self.root, "alpha", "run") as data:
            data["steps"]["check-work"]["on"]["confirmed"] = {
                "next": "report",
                "as": "verified",
            }
        self.assertIn("value.invalid-capture", codes(self.skill))

    def test_one_command_both_required_and_prohibited_at_a_step_is_reported(self):
        """The only obligation conflict a source makes structurally visible.

        Two provisions may select one step at one phase — requiring a boundary
        and prohibiting what lies outside it is how a policy is written. What no
        reading of the node satisfies is the same command on both sides.
        """
        required = "Keep the report to the subject this workflow named."
        with edit_yaml(self.skill / "policies" / "run-authority.yaml") as data:
            data["provisions"]["contradict-the-subject"] = {
                "phase": "before",
                "match": {"subjects": ["report.write"]},
                "prohibit": required,
            }
        self.assertIn("workflow.conflicting-obligation", codes(self.skill))


class ProtocolStateTests(unittest.TestCase):
    """A hook runs from a state the frame can actually be in at that node."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def test_a_hook_running_from_a_state_unreachable_there_is_reported(self):
        """The hook that opens the trail runs where the frame is still initial.

        Pointing it at a state only a later hook can set makes the transition
        one no run can take, which is a source mistake rather than a state the
        agent has to handle.
        """
        with edit_yaml(self.skill / "protocols" / "run-trail.yaml") as data:
            opening = data["hooks"]["hold-finding"]
            self.assertEqual([data["initial"]], opening["from"])
            opening["from"] = [opening["to"]]
        self.assertIn("protocol.impossible-transition", codes(self.skill))


if __name__ == "__main__":
    unittest.main()
