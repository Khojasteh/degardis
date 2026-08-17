"""The schema each construct kind must satisfy, read against its own reader.

The manifest key that selected a file decides its schema, so each case hands one
reader the mapping a file would hold and states the check code the format says
applies.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from degardis import sources
from degardis.model import Diagnostics
from tests.support import codes, copy_skills, edit_yaml, write_text


def read(kind: str, text: str, stem: str = "thing") -> tuple[Any, set[str]]:
    reader = sources.CONSTRUCT_READERS[kind]
    diagnostics = Diagnostics()
    construct = reader(
        Path(f"{kind}/{stem}.yaml"), yaml.safe_load(text), diagnostics
    )
    return construct, {record.code for record in diagnostics.records}


class PolicyTests(unittest.TestCase):
    GOOD = """
summary: Keep external effects within established authority.
provisions:
  establish-authority:
    phase: before
    match:
      effects: [external.*]
    require: Establish the authority for the external effect.
"""

    def test_a_policy_with_provisions_is_read(self):
        policy, found = read("policies", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual("thing", policy.id)
        self.assertEqual(1, len(policy.provisions))
        self.assertEqual("before", policy.provisions[0].phase)

    def test_the_title_falls_back_to_the_file_stem(self):
        policy, _ = read("policies", self.GOOD, stem="external-authority")
        self.assertEqual("External Authority", policy.title)

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        for source, code in (
            (
                "provisions:\n  act:\n    phase: before\n    match:\n"
                "      all: true\n    require: Act.\n",
                "policy.missing-summary",
            ),
            ("summary: A boundary.\n", "policy.missing-provisions"),
        ):
            with self.subTest(code=code):
                _, found = read("policies", source)
                self.assertIn(code, found)

    def test_an_empty_provisions_mapping_is_a_shape_error(self):
        """A key that is present and unreadable is a different repair from an
        absent one, so it reports the shape rather than the missing key."""
        _, found = read("policies", "summary: A boundary.\nprovisions: {}\n")
        self.assertIn("policy.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("policies", self.GOOD + "prefer: The smaller effect.\n")
        self.assertIn("policy.unknown-field", found)

    def test_every_binding_phase_is_accepted(self):
        for phase in sources.BINDING_PHASES:
            with self.subTest(phase=phase):
                _, found = read(
                    "policies", self.GOOD.replace("phase: before", f"phase: {phase}")
                )
                self.assertEqual(set(), found)

    def test_an_unknown_phase_is_reported(self):
        _, found = read(
            "policies", self.GOOD.replace("phase: before", "phase: sometime")
        )
        self.assertIn("policy.invalid-provision", found)

    def test_a_provision_needs_a_selector(self):
        _, found = read(
            "policies",
            """
summary: A boundary.
provisions:
  one:
    phase: before
    require: Do the thing.
""",
        )
        self.assertIn("policy.invalid-provision", found)

    def test_a_provision_names_exactly_one_obligation(self):
        both = self.GOOD + "    prohibit: Do not do the thing.\n"
        _, found = read("policies", both)
        self.assertIn("policy.invalid-provision", found)
        neither = self.GOOD.replace(
            "    require: Establish the authority for the external effect.\n", ""
        )
        _, found = read("policies", neither)
        self.assertIn("policy.invalid-provision", found)

    def test_a_selector_selecting_nothing_is_reported(self):
        _, found = read(
            "policies",
            """
summary: A boundary.
provisions:
  one:
    phase: before
    match: {}
    require: Do the thing.
""",
        )
        self.assertIn("policy.invalid-provision", found)

    def test_all_true_selects_every_node(self):
        policy, found = read(
            "policies",
            """
summary: A boundary.
provisions:
  one:
    phase: before
    match: {all: true}
    require: Do the thing everywhere.
""",
        )
        self.assertEqual(set(), found)
        self.assertTrue(policy.provisions[0].selector.every)

    def test_a_verification_names_one_kind(self):
        for verify in (
            "    verify:\n      gate: authorization\n",
            "    verify:\n      confirm: The thing was done.\n",
            "    verify:\n      expression: input.wide == true\n",
        ):
            with self.subTest(verify=verify.strip()):
                _, found = read("policies", self.GOOD + verify)
                self.assertEqual(set(), found)
        _, found = read(
            "policies",
            self.GOOD + "    verify:\n      gate: a\n      confirm: b\n",
        )
        self.assertIn("policy.invalid-provision", found)

    def test_a_verification_naming_advice_is_reported(self):
        _, found = read(
            "policies", self.GOOD + "    verify:\n      prefer: The smaller one.\n"
        )
        self.assertIn("heuristic.used-as-authority", found)


class RuleTests(unittest.TestCase):
    GOOD = """
summary: A public contract stays stable unless the request authorizes a change.
phase: before
match:
  subjects: [change.public-contract]
require: Preserve the existing public contract.
"""

    def test_a_rule_is_one_provision_at_file_scope(self):
        rule, found = read("rules", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual("before", rule.provision.phase)
        self.assertFalse(rule.provision.prohibits)

    def test_a_prohibiting_rule_is_read_as_one(self):
        rule, found = read(
            "rules",
            self.GOOD.replace(
                "require: Preserve the existing public contract.",
                "prohibit: Change the public contract without authority.",
            ),
        )
        self.assertEqual(set(), found)
        self.assertTrue(rule.provision.prohibits)

    def test_activation_conditions_are_parsed(self):
        rule, found = read(
            "rules",
            self.GOOD
            + "when: input.wide == false\nunless: input.wide == true\n",
        )
        self.assertEqual(set(), found)
        self.assertIsNotNone(rule.provision.when)
        self.assertIsNotNone(rule.provision.unless)

    def test_a_condition_that_is_prose_is_reported(self):
        _, found = read(
            "rules", self.GOOD + "when: the request authorizes the change\n"
        )
        self.assertIn("expr.invalid-syntax", found)

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        for removed, code in (
            (
                "summary: A public contract stays stable unless the request "
                "authorizes a change.\n",
                "rule.missing-summary",
            ),
            ("phase: before\n", "rule.missing-phase"),
            (
                "match:\n  subjects: [change.public-contract]\n",
                "rule.missing-match",
            ),
            (
                "require: Preserve the existing public contract.\n",
                "rule.missing-command",
            ),
        ):
            with self.subTest(removed=removed.split(":")[0]):
                _, found = read("rules", self.GOOD.replace(removed, ""))
                self.assertIn(code, found)

    def test_a_phase_outside_the_vocabulary_is_a_shape_error(self):
        _, found = read("rules", self.GOOD.replace("phase: before", "phase: later"))
        self.assertIn("rule.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("rules", self.GOOD + "prefer: The smaller change.\n")
        self.assertIn("rule.unknown-field", found)


class ProtocolTests(unittest.TestCase):
    GOOD = """
purpose: Keep a decision available until its consumer uses it.
states: [clear, open]
initial: clear
accepting: [clear]
data:
  decision:
    type: {optional: string}
    initial: {literal: null}
hooks:
  retain:
    phase: after
    match:
      subjects: [decision.open]
    from: [clear]
    command: Retain the decision basis.
    set:
      decision: {from: result.basis}
    to: open
"""

    def test_a_protocol_is_read_with_its_state_machine(self):
        protocol, found = read("protocols", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual(("clear", "open"), protocol.states)
        self.assertEqual("clear", protocol.initial)
        self.assertEqual(("clear",), protocol.accepting)
        self.assertEqual("decision", protocol.data[0].name)
        self.assertEqual("open", protocol.hooks[0].to)

    def test_a_state_outside_the_declared_set_is_reported(self):
        _, found = read("protocols", self.GOOD.replace("initial: clear", "initial: idle"))
        self.assertIn("protocol.invalid-state", found)

    def test_a_hook_moving_to_an_undeclared_state_is_reported(self):
        _, found = read("protocols", self.GOOD.replace("to: open", "to: spent"))
        self.assertIn("protocol.invalid-state", found)

    def test_a_hook_from_an_undeclared_state_is_reported(self):
        _, found = read("protocols", self.GOOD.replace("from: [clear]", "from: [idle]"))
        self.assertIn("protocol.invalid-state", found)

    def test_every_hook_phase_is_accepted(self):
        for phase in sources.HOOK_PHASES:
            with self.subTest(phase=phase):
                text = self.GOOD.replace("phase: after", f"phase: {phase}")
                if phase in ("enter", "exit"):
                    text = text.replace(
                        "    match:\n      subjects: [decision.open]\n", ""
                    )
                _, found = read("protocols", text)
                self.assertEqual(set(), found)

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        for removed, code in (
            (
                "purpose: Keep a decision available until its consumer uses it.\n",
                "protocol.missing-purpose",
            ),
            ("states: [clear, open]\n", "protocol.missing-states"),
            ("initial: clear\n", "protocol.missing-initial"),
            ("accepting: [clear]\n", "protocol.missing-accepting"),
        ):
            with self.subTest(removed=removed.split(":")[0]):
                _, found = read("protocols", self.GOOD.replace(removed, ""))
                self.assertIn(code, found)

    def test_a_protocol_with_no_hooks_names_the_key_it_is_missing(self):
        _, found = read(
            "protocols",
            "purpose: Keep a decision available.\nstates: [clear]\n"
            "initial: clear\naccepting: [clear]\n",
        )
        self.assertIn("protocol.missing-hooks", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("protocols", self.GOOD + "ledger:\n- Remember what is open.\n")
        self.assertIn("protocol.unknown-field", found)

    def test_a_frame_boundary_hook_selects_no_node(self):
        _, found = read("protocols", self.GOOD.replace("phase: after", "phase: enter"))
        self.assertIn("protocol.invalid-hook", found)

    def test_a_hook_with_neither_command_nor_verification_is_reported(self):
        _, found = read(
            "protocols",
            self.GOOD.replace("    command: Retain the decision basis.\n", ""),
        )
        self.assertIn("protocol.invalid-hook", found)

    def test_a_hook_with_only_a_verification_is_accepted(self):
        _, found = read(
            "protocols",
            self.GOOD.replace(
                "    command: Retain the decision basis.\n",
                "    verify:\n      confirm: The basis still governs this action.\n",
            ),
        )
        self.assertEqual(set(), found)

    def test_a_protocol_with_no_hooks_is_reported(self):
        _, found = read(
            "protocols",
            """
purpose: Keep nothing.
states: [clear]
initial: clear
accepting: [clear]
hooks: {}
""",
        )
        self.assertIn("protocol.invalid-shape", found)


class PatternTests(unittest.TestCase):
    GOOD = """
summary: Inspect the owner, choose a plan, then act.
inputs:
  target:
    type: string
procedure:
  inspect-owner:
    command: Inspect the source that owns the target behavior.
    uses: [input.target]
  perform-change:
    command: Perform only the chosen bounded change.
"""

    def test_a_pattern_is_read_with_its_ordered_procedure(self):
        pattern, found = read("patterns", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual(
            ["inspect-owner", "perform-change"],
            [item.id for item in pattern.procedure],
        )

    def test_a_procedure_read_outside_the_pattern_inputs_is_reported(self):
        """A pattern reads its own declared inputs and nothing else.

        The caller translates those reads through its `with` bindings, so a read
        naming a caller value directly would bind to whatever the caller happened
        to have rather than to what the pattern declares.
        """
        for reference in ("result.finding", "not an expression"):
            with self.subTest(reference=reference):
                _, found = read(
                    "patterns",
                    self.GOOD.replace(
                        "    uses: [input.target]", f"    uses: ['{reference}']"
                    ),
                )
                self.assertIn("pattern.invalid-use", found)

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        for source, code in (
            (
                "procedure:\n  act:\n    command: Act on the target.\n",
                "pattern.missing-summary",
            ),
            ("summary: A method.\n", "pattern.missing-procedure"),
        ):
            with self.subTest(code=code):
                _, found = read("patterns", source)
                self.assertIn(code, found)

    def test_an_empty_procedure_mapping_is_a_shape_error(self):
        _, found = read("patterns", "summary: A method.\nprocedure: {}\n")
        self.assertIn("pattern.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("patterns", self.GOOD + "outcomes:\n  done: {}\n")
        self.assertIn("pattern.unknown-field", found)

    def test_a_procedure_item_needs_a_command(self):
        _, found = read(
            "patterns",
            self.GOOD.replace(
                "    command: Perform only the chosen bounded change.",
                "    details:\n    - Something.",
            ),
        )
        self.assertIn("pattern.invalid-procedure", found)

    def test_a_procedure_item_does_not_branch_call_or_produce(self):
        for field in ("next: other", "use: other", "produces: {x: {type: string}}"):
            with self.subTest(field=field):
                _, found = read("patterns", self.GOOD + f"    {field}\n")
                self.assertIn("pattern.invalid-procedure", found)

    def test_a_procedure_item_may_declare_local_effects(self):
        pattern, found = read("patterns", self.GOOD + "    effects: [external.write]\n")
        self.assertEqual(set(), found)
        self.assertEqual(("external.write",), pattern.procedure[-1].effects)


class HeuristicTests(unittest.TestCase):
    GOOD = """
question: Which valid option should be preferred?
advice:
  reversible:
    prefer: Prefer the smallest reversible option.
    because: Smaller reversible changes reduce unintended impact.
"""

    def test_a_heuristic_is_read_with_its_advice(self):
        heuristic, found = read("heuristics", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual("reversible", heuristic.advice[0].id)

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        for source, code in (
            (
                "advice:\n  small:\n    prefer: Prefer the smaller option.\n",
                "heuristic.missing-question",
            ),
            ("question: Which one?\n", "heuristic.missing-advice"),
        ):
            with self.subTest(code=code):
                _, found = read("heuristics", source)
                self.assertIn(code, found)

    def test_an_empty_advice_mapping_is_a_shape_error(self):
        _, found = read("heuristics", "question: Which one?\nadvice: {}\n")
        self.assertIn("heuristic.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        """A heuristic cannot require or verify, so it has no field for either."""
        _, found = read(
            "heuristics", self.GOOD + "require: Take the smaller option.\n"
        )
        self.assertIn("heuristic.unknown-field", found)

    def test_advice_needs_a_preference(self):
        _, found = read(
            "heuristics",
            self.GOOD.replace(
                "    prefer: Prefer the smallest reversible option.",
                "    require: Take the smallest reversible option.",
            ),
        )
        self.assertIn("heuristic.invalid-shape", found)


class GuidanceTests(unittest.TestCase):
    def test_guidance_is_read_with_its_summary(self):
        unit, found = read(
            "guidance",
            "summary: Lead with the result.\npoints:\n- Say what you inferred.\n",
        )
        self.assertEqual(set(), found)
        self.assertEqual(1, len(unit.points))

    def test_a_missing_summary_names_the_key_it_is_missing(self):
        _, found = read("guidance", "points:\n- Say what you inferred.\n")
        self.assertIn("guidance.missing-summary", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read(
            "guidance", "summary: Lead with the result.\nphase: before\n"
        )
        self.assertIn("guidance.unknown-field", found)

    def test_a_value_that_cannot_be_read_is_a_shape_error(self):
        _, found = read("guidance", "summary: Lead with the result.\npoints: []\n")
        self.assertIn("guidance.invalid-shape", found)


class ProfileTests(unittest.TestCase):
    def test_category_is_optional_and_trims_surrounding_whitespace(self):
        for suffix, expected in (("", ""), ('category: "  Writing  "\n', "Writing")):
            with self.subTest(category=expected):
                profile, found = read("profiles", self.GOOD + suffix)
                self.assertEqual(set(), found)
                self.assertEqual(expected, profile.category)

    def test_invalid_category_has_a_specific_diagnostic(self):
        for value in ("''", "'   '", "null", "42", "false", "[]", "{}"):
            with self.subTest(value=value):
                profile, found = read("profiles", self.GOOD + f"category: {value}\n")
                self.assertIsNone(profile)
                self.assertEqual({"profile.invalid-category"}, found)

    GOOD = """
title: Concise result
description: Apply where the reader needs the shortest answer.
points:
- Keep only the detail that changes the reader's decision.
- Lead with the result.
"""

    def test_a_profile_is_read_with_its_description_and_points(self):
        profile, found = read("profiles", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual("Concise result", profile.title)
        self.assertEqual(
            "Apply where the reader needs the shortest answer.", profile.description
        )
        self.assertEqual(
            (
                "Keep only the detail that changes the reader's decision.",
                "Lead with the result.",
            ),
            profile.points,
        )

    def test_a_profile_with_no_title_warns_that_one_was_derived(self):
        profile, found = read(
            "profiles",
            "points:\n- Keep it clear.\n",
            stem="detailed-review",
        )
        self.assertIn("profile.missing-title", found)
        self.assertEqual("Detailed Review", profile.title)

    def test_a_profile_with_no_description_is_read_without_one(self):
        """The description is what the index says about a profile, and an author
        who has nothing to add there leaves the row its title alone."""
        profile, found = read(
            "profiles", "title: Concise\npoints:\n- Keep it short.\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual("", profile.description)

    def test_invalid_description_has_a_specific_diagnostic(self):
        for value in ("''", "'   '", "null", "42", "false", "[]", "{}"):
            with self.subTest(value=value):
                profile, found = read(
                    "profiles",
                    f"title: Concise\ndescription: {value}\npoints:\n- Keep it short.\n",
                )
                self.assertIsNone(profile)
                self.assertEqual({"profile.invalid-description"}, found)

    def test_a_profile_with_no_points_is_reported(self):
        _, found = read("profiles", "title: Concise\n")
        self.assertIn("profile.missing-points", found)

    def test_an_empty_points_list_is_a_shape_error(self):
        _, found = read("profiles", "title: Concise\npoints: []\n")
        self.assertIn("profile.invalid-shape", found)

    def test_removed_profile_fields_are_ordinary_unknown_fields(self):
        for field, value in (
            ("applies", "{terms: [concise]}"),
            ("activation", "explicit"),
        ):
            with self.subTest(field=field):
                _, found = read("profiles", self.GOOD + f"{field}: {value}\n")
                self.assertIn("profile.unknown-field", found)
                self.assertFalse(any("provenance" in code for code in found))

    def test_a_profile_cannot_declare_guidance(self):
        _, found = read("profiles", self.GOOD + "guidance:\n- clear-reporting\n")
        self.assertIn("profile.unknown-field", found)

    def test_a_profile_cannot_contribute_a_binding_construct(self):
        for key in sources.PROFILE_FORBIDDEN:
            with self.subTest(key=key):
                _, found = read("profiles", self.GOOD + f"{key}:\n- something\n")
                self.assertIn("profile.binding-contribution", found)


class ProfileGuideTests(unittest.TestCase):
    """A guide is read from disk, so its checks need a skill rather than a mapping.

    Each check answers a different repair: the path is wrong, the file is not
    there, it is not Markdown, or it brings a heading the generated page already
    supplies.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def set_guides(self, *guides: str) -> None:
        with edit_yaml(self.skill / "profiles" / "thorough.yaml") as data:
            data["guides"] = list(guides)

    def test_a_guide_that_is_not_there_is_reported(self):
        self.set_guides("guides/absent.md")
        self.assertIn("profile.guide-missing", codes(self.skill))

    def test_a_guide_that_is_not_markdown_is_reported(self):
        write_text(self.skill / "profiles" / "guides" / "notes.txt", "Plain text.\n")
        self.set_guides("guides/notes.txt")
        self.assertIn("profile.guide-not-markdown", codes(self.skill))

    def test_a_guide_outside_the_skill_is_reported(self):
        write_text(self.root / "outside.md", "## Outside\n\nText.\n")
        self.set_guides("../../outside.md")
        self.assertIn("profile.guide-outside-skill", codes(self.skill))

    def test_a_guide_bringing_its_own_level_one_heading_is_reported(self):
        write_text(
            self.skill / "profiles" / "guides" / "thorough.md",
            "# Thorough\n\nInspect every source the request reaches.\n",
        )
        self.assertIn("profile.guide-heading", codes(self.skill))


class RemovedDocumentationFieldTests(unittest.TestCase):
    def test_removed_author_only_fields_are_not_part_of_the_schema(self):
        cases = (
            ("policies", PolicyTests.GOOD + "rationale: Author note.\n", "policy.unknown-field"),
            ("policies", PolicyTests.GOOD + "examples:\n- Author example.\n", "policy.unknown-field"),
            ("rules", RuleTests.GOOD + "rationale: Author note.\n", "rule.unknown-field"),
            ("protocols", ProtocolTests.GOOD + "examples:\n- Author example.\n", "protocol.unknown-field"),
            ("patterns", PatternTests.GOOD + "tradeoffs:\n- Author note.\n", "pattern.unknown-field"),
            ("heuristics", HeuristicTests.GOOD.replace("    because: Smaller reversible changes reduce unintended impact.\n", "    because: Smaller reversible changes reduce unintended impact.\n    examples:\n    - Author example.\n"), "heuristic.invalid-shape"),
            ("guidance", "summary: Lead with the result.\nrationale: Author note.\n", "guidance.unknown-field"),
        )
        for kind, text, code in cases:
            with self.subTest(kind=kind, code=code):
                _, found = read(kind, text)
                self.assertIn(code, found)


class RecordTests(unittest.TestCase):
    def test_a_record_is_read_with_its_typed_fields(self):
        record, found = read(
            "records",
            """
title: Inspection result
fields:
  summary:
    type: string
    description: Concise result.
  findings:
    type: {list: string}
""",
        )
        self.assertEqual(set(), found)
        self.assertEqual({"summary", "findings"}, set(record.types()))

    def test_a_missing_fields_mapping_names_the_key_it_is_missing(self):
        _, found = read("records", "title: Empty\n")
        self.assertIn("record.missing-fields", found)

    def test_an_empty_fields_mapping_is_a_shape_error(self):
        _, found = read("records", "title: Empty\nfields: {}\n")
        self.assertIn("record.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("records", "title: Empty\nsummary:\n  type: string\n")
        self.assertIn("record.unknown-field", found)

    def test_a_field_with_an_unknown_type_is_reported(self):
        _, found = read("records", "fields:\n  summary:\n    type: text\n")
        self.assertIn("value.invalid-type", found)


class WorkflowShapeTests(unittest.TestCase):
    GOOD = """
description: Do the one thing and return.
outcomes:
  done: {}
entry: act
steps:
  act:
    action: Do the one thing.
    next: finish
  finish:
    return:
      outcome: done
"""

    def test_a_workflow_is_read_with_its_steps(self):
        workflow, found = read("workflows", self.GOOD)
        self.assertEqual(set(), found)
        self.assertEqual("act", workflow.entry)
        self.assertEqual(["act", "finish"], [step.id for step in workflow.steps])

    def test_a_missing_required_field_names_the_key_it_is_missing(self):
        """The commonest authoring mistake, and one a code can answer alone.

        A workflow requires description, entry, outcomes, and steps, so leaving
        one out reports a check naming that key rather than the file's shape.
        """
        for removed, code in (
            (
                "description: Do the one thing and return.\n",
                "workflow.missing-description",
            ),
            ("entry: act\n", "workflow.missing-entry"),
            ("outcomes:\n  done: {}\n", "workflow.missing-outcomes"),
        ):
            with self.subTest(removed=removed.split(":")[0]):
                _, found = read("workflows", self.GOOD.replace(removed, ""))
                self.assertIn(code, found)

    def test_a_workflow_with_no_steps_names_the_key_it_is_missing(self):
        _, found = read(
            "workflows",
            "description: Do nothing.\noutcomes:\n  done: {}\nentry: act\n",
        )
        self.assertIn("workflow.missing-steps", found)

    def test_a_value_that_cannot_be_read_is_a_shape_error(self):
        for source in (
            self.GOOD.replace("outcomes:\n  done: {}", "outcomes: {}"),
            self.GOOD.replace("entry: act", "entry: Act Now"),
        ):
            with self.subTest(source=source.splitlines()[2]):
                _, found = read("workflows", source)
                self.assertIn("workflow.invalid-shape", found)

    def test_a_field_the_schema_does_not_have_is_reported(self):
        _, found = read("workflows", self.GOOD + "profiles:\n- concise\n")
        self.assertIn("workflow.unknown-field", found)

    def test_an_action_resource_declares_exactly_one_named_operation(self):
        for resource in (
            "    resource:\n      walk: scripts/greet.py",
            "    resource:\n      run: scripts/greet.py\n      read: assets/note.md",
            "    resource:\n      run: [scripts/greet.py]",
            "    resource: scripts/greet.py",
        ):
            with self.subTest(resource=resource.split("\n")[-1].strip()):
                _, found = read(
                    "workflows",
                    self.GOOD.replace(
                        "    action: Do the one thing.",
                        f"    action: Do the one thing.\n{resource}",
                    ),
                )
                self.assertIn("resource.invalid-operation", found)

    def test_a_resource_path_outside_its_operation_s_directory_is_reported(self):
        """Each operation names the one directory the bundle keeps that kind in.

        `run` executes, so it names a script; `copy` and `fill` name an asset;
        `read` names a reference or an asset. A path that leaves the bundle is
        refused whatever the operation.
        """
        for resource in (
            "      run: assets/greet.py",
            "      copy: scripts/greet.py",
            "      fill: references/note.md",
            "      read: scripts/greet.py",
            "      run: ../outside/greet.py",
            "      run: /absolute/greet.py",
        ):
            with self.subTest(resource=resource.strip()):
                _, found = read(
                    "workflows",
                    self.GOOD.replace(
                        "    action: Do the one thing.",
                        f"    action: Do the one thing.\n    resource:\n{resource}",
                    ),
                )
                self.assertIn("resource.invalid-path", found)

    def test_a_pattern_step_does_not_declare_the_effects_its_items_take(self):
        _, found = read(
            "workflows",
            self.GOOD.replace(
                "    action: Do the one thing.",
                "    pattern: inspect-plan-act\n    effects: [external.write]",
            ),
        )
        self.assertIn("pattern.invalid-effects", found)

    def test_a_step_names_exactly_one_form(self):
        _, found = read(
            "workflows",
            self.GOOD.replace(
                "    action: Do the one thing.",
                "    action: Do the one thing.\n    decide: Choose something.",
            ),
        )
        self.assertIn("workflow.invalid-step", found)
        _, found = read(
            "workflows",
            self.GOOD.replace("    action: Do the one thing.\n", ""),
        )
        self.assertIn("workflow.invalid-step", found)

    def test_a_field_the_form_does_not_have_is_reported(self):
        _, found = read(
            "workflows", self.GOOD.replace("    next: finish", "    next: finish\n    with:\n      x: {literal: 1}")
        )
        self.assertIn("workflow.invalid-step", found)

    def test_heuristics_belong_on_a_decision_or_a_gate(self):
        _, found = read(
            "workflows",
            self.GOOD.replace(
                "    next: finish", "    next: finish\n    heuristics: [smallest-change]"
            ),
        )
        self.assertIn("heuristic.invalid-placement", found)

    def test_a_decision_needs_at_least_two_choices(self):
        _, found = read(
            "workflows",
            """
description: Choose and return.
outcomes:
  done: {}
entry: pick
steps:
  pick:
    decide: Choose the route.
    choices:
      only:
        command: Take the only route.
        next: finish
  finish:
    return:
      outcome: done
""",
        )
        self.assertIn("workflow.invalid-step", found)

    def test_a_branch_closes_with_otherwise(self):
        _, found = read(
            "workflows",
            """
description: Branch and return.
outcomes:
  done: {}
entry: route
steps:
  route:
    branch:
    - when: input.wide == true
      next: finish
  finish:
    return:
      outcome: done
""",
        )
        self.assertIn("workflow.invalid-step", found)

    def test_otherwise_closes_the_branch(self):
        _, found = read(
            "workflows",
            """
description: Branch and return.
outcomes:
  done: {}
entry: route
steps:
  route:
    branch:
    - otherwise: finish
    - when: input.wide == true
      next: finish
  finish:
    return:
      outcome: done
""",
        )
        self.assertIn("workflow.invalid-step", found)


class RequiredFieldCodeTests(unittest.TestCase):
    """Every required top-level field reports a check that names the key.

    An absent required field is the commonest authoring mistake and the one a
    code alone can answer, so it may not fall back to the construct's
    file-level shape check. This reads the reader source rather than any list,
    because the requirement is expressed at the call site that reads the field:
    a new required field with no `missing` code fails here rather than shipping
    a finding that names the file instead of the key.
    """

    READS = ("text", "mapping", "required_id_list")

    def _tree(self):
        source = Path(sources.__file__).read_text(encoding="utf-8")
        return ast.parse(source)

    def test_every_required_top_level_read_names_its_own_check(self):
        for call in self._required_reads():
            key = self._key(call)
            with self.subTest(field=key, line=call.lineno):
                keyword = next(
                    (item for item in call.keywords if item.arg == "missing"), None
                )
                self.assertIsNotNone(
                    keyword,
                    f"a required read of {key!r} passes no missing= check code",
                )
                self.assertIsInstance(keyword.value, ast.Constant)
                self.assertRegex(keyword.value.value, r"^[a-z]+\.missing-[a-z_-]+$")

    def test_every_missing_code_names_the_key_it_reports(self):
        """The code spells the key, so an author can build it from the field."""
        for call in self._required_reads():
            keyword = next(
                (item for item in call.keywords if item.arg == "missing"), None
            )
            if keyword is None:
                continue
            key = self._key(call)
            with self.subTest(field=key):
                self.assertTrue(
                    keyword.value.value.endswith(f".missing-{key}"),
                    f"{keyword.value.value} does not name the key {key!r}",
                )

    @staticmethod
    def _key(call):
        """The field name a read names, whichever position it sits in."""
        for argument in call.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return argument.value
        return "?"

    def _required_reads(self):
        found = []
        for node in ast.walk(self._tree()):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in self.READS:
                continue
            required = any(
                item.arg == "required"
                and isinstance(item.value, ast.Constant)
                and item.value.value is True
                for item in node.keywords
            )
            if required or node.func.attr == "required_id_list":
                found.append(node)
        self.assertTrue(found, "no required top-level reads found to check")
        return found


if __name__ == "__main__":
    unittest.main()
