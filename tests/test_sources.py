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
        policy, found = read(
            "policies", self.GOOD + "rationale: External effects need explicit ownership.\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual("thing", policy.id)
        self.assertEqual("External effects need explicit ownership.", policy.rationale)
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

    def test_an_empty_provisions_mapping_names_the_field(self):
        """A key that is present and unreadable is a different repair from an
        absent one, so it reports the shape rather than the missing key."""
        _, found = read("policies", "summary: A boundary.\nprovisions: {}\n")
        self.assertIn("policy.invalid-provisions", found)

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

    def test_a_nested_condition_keeps_the_expression_syntax_code(self):
        _, found = read(
            "policies",
            self.GOOD.replace(
                "    require: Establish the authority for the external effect.",
                "    when: not prose here\n"
                "    require: Establish the authority for the external effect.",
            ),
        )
        self.assertIn("expr.invalid-syntax", found)

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
        rule, found = read(
            "rules", self.GOOD + "rationale: Unapproved changes surprise callers.\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual("Unapproved changes surprise callers.", rule.rationale)
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
        self.assertIn("rule.invalid-when", found)

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
        self.assertIn("rule.invalid-phase", found)

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
  seen:
    type: {list: string}
    default: []
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
        protocol, found = read(
            "protocols", self.GOOD + "rationale: Deferred decisions need a visible owner.\n"
        )
        self.assertEqual(set(), found)
        self.assertEqual("Deferred decisions need a visible owner.", protocol.rationale)
        self.assertEqual(("clear", "open"), protocol.states)
        self.assertEqual("clear", protocol.initial)
        self.assertEqual(("clear",), protocol.accepting)
        self.assertEqual("decision", protocol.data[0].name)
        self.assertEqual("open", protocol.hooks[0].to)
        # An optional field begins absent, so it declares no default; the list
        # field declares the value the frame opens holding.
        self.assertFalse(protocol.data[0].defaulted)
        self.assertEqual([], protocol.data[1].default)
        self.assertTrue(protocol.data[1].defaulted)

    def test_a_state_field_default_must_suit_its_declared_type(self):
        _, found = read(
            "protocols", self.GOOD.replace("default: []", "default: none")
        )
        self.assertIn("value.invalid-default", found)

    def test_a_state_outside_the_declared_set_is_reported(self):
        _, found = read("protocols", self.GOOD.replace("initial: clear", "initial: idle"))
        self.assertIn("protocol.invalid-initial", found)

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
        self.assertIn("protocol.invalid-hooks", found)


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
        self.assertIn("pattern.invalid-procedure", found)

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
        self.assertIn("heuristic.invalid-advice", found)

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
        self.assertIn("heuristic.invalid-advice", found)


class GuidanceTests(unittest.TestCase):
    def test_guidance_is_read_with_its_summary(self):
        unit, found = read(
            "guidance",
            "summary: Lead with the result.\n"
            "rationale: The reader needs the outcome before the method.\n"
            "points:\n- Say what you inferred.\n",
        )
        self.assertEqual(set(), found)
        self.assertEqual("The reader needs the outcome before the method.", unit.rationale)
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
        self.assertIn("guidance.invalid-points", found)


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
        self.assertIn("profile.invalid-points", found)

    def test_removed_profile_fields_are_ordinary_unknown_fields(self):
        for field, value in (
            ("applies", "{terms: [concise]}"),
            ("activation", "explicit"),
            ("guides", "[guides/concise.md]"),
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


class ProfileReferenceTests(unittest.TestCase):
    """A profile names supporting Markdown the way every other construct does.

    A reference is a page the bundle ships and the profile links, not a file the
    profile's own page absorbs, so the checks that hold it are the ones already
    holding a pattern's, a heuristic's, and a guidance unit's references: the
    target has to be something `content` selected, and a shipped reference has
    to have a route in. Both need a skill on disk rather than a mapping, because
    each is settled against what a build would write.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.skill = self.root / "alpha"

    def set_references(self, *references: str) -> None:
        with edit_yaml(self.skill / "profiles" / "thorough.yaml") as data:
            data["references"] = list(references)

    def test_a_reference_the_bundle_does_not_ship_is_reported(self):
        self.set_references("references/profiles/absent.md")
        self.assertIn("output.broken-reference", codes(self.skill))

    def test_a_reference_outside_the_shipped_set_is_reported(self):
        """A path that leaves the skill directory ships nothing, so it is broken.

        Containment is enforced where the bundle's contents are decided: a
        content pattern cannot select outside the skill, so an escaping target
        is a target no build writes.
        """
        write_text(self.root / "outside.md", "# Outside\n\nText.\n")
        self.set_references("../../outside.md")
        self.assertIn("output.broken-reference", codes(self.skill))

    def test_the_reference_a_profile_links_is_reached_through_that_profile(self):
        """A profile page is a route in, so what it links is not unreached.

        The generated profile index is linked from `SKILL.md` and every profile
        page from that index, so a reference only a profile names still has a
        route an agent arrives by. Warning here would push the author to link
        the same page from a workflow, which is what a profile may never do.
        """
        self.assertNotIn("output.unlinked-reference", codes(self.skill, "warning"))
        self.set_references()
        self.assertIn("output.unlinked-reference", codes(self.skill, "warning"))

    def test_a_reference_that_states_no_heading_is_reported(self):
        """A link is named by the document it opens, so a nameless one is reported.

        The link falls back to the path, which is what the check exists to
        tell the author about: an agent reading it learns where the file sits
        and has to open it to learn whether it wanted the file at all.
        """
        notes = self.skill / "references" / "profiles" / "thorough-notes.md"
        self.assertNotIn("render.untitled-reference", codes(self.skill, "warning"))
        write_text(notes, "Worked examples of the profile follow.\n")
        self.assertIn("render.untitled-reference", codes(self.skill, "warning"))


class RemovedDocumentationFieldTests(unittest.TestCase):
    def test_removed_author_only_fields_are_not_part_of_the_schema(self):
        cases = (
            ("policies", PolicyTests.GOOD + "examples:\n- Author example.\n", "policy.unknown-field"),
            ("protocols", ProtocolTests.GOOD + "examples:\n- Author example.\n", "protocol.unknown-field"),
            ("patterns", PatternTests.GOOD + "tradeoffs:\n- Author note.\n", "pattern.unknown-field"),
            ("heuristics", HeuristicTests.GOOD.replace("    because: Smaller reversible changes reduce unintended impact.\n", "    because: Smaller reversible changes reduce unintended impact.\n    examples:\n    - Author example.\n"), "heuristic.invalid-advice"),
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
        self.assertIn("record.invalid-fields", found)

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
        for source, code in (
            (self.GOOD.replace("outcomes:\n  done: {}", "outcomes: {}"), "workflow.invalid-outcomes"),
            (self.GOOD.replace("entry: act", "entry: Act Now"), "workflow.invalid-entry"),
        ):
            with self.subTest(source=source.splitlines()[2]):
                _, found = read("workflows", source)
                self.assertIn(code, found)

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


class DeclaredValueDescriptionTests(unittest.TestCase):
    """The description beside a declared value's type, in all five places.

    A workflow input, a produced value, a pattern input, a record field, and a
    protocol state field declare a value the same way, and each accepts an
    optional description. Only the record field stored one, so only the record
    field checked it, and the other four accepted a description that was empty,
    blank, or not text at all. These cases hold every one of the five to the
    same check, so a declaration is refused wherever the empty description was
    written.
    """

    MARKER = "DESCRIPTION"

    SOURCES = (
        (
            "workflows",
            WorkflowShapeTests.GOOD.replace(
                "outcomes:",
                "inputs:\n  request:\n    type: string\n"
                f"    description: {MARKER}\noutcomes:",
            ),
        ),
        (
            "workflows",
            WorkflowShapeTests.GOOD.replace(
                "    action: Do the one thing.\n",
                "    action: Do the one thing.\n    produces:\n      finding:\n"
                f"        type: string\n        description: {MARKER}\n",
            ),
        ),
        (
            "patterns",
            PatternTests.GOOD.replace(
                "  target:\n    type: string\n",
                f"  target:\n    type: string\n    description: {MARKER}\n",
            ),
        ),
        (
            "protocols",
            ProtocolTests.GOOD.replace(
                "    type: {optional: string}\n",
                f"    type: {{optional: string}}\n    description: {MARKER}\n",
            ),
        ),
        (
            "records",
            f"fields:\n  summary:\n    type: string\n    description: {MARKER}\n",
        ),
    )

    def test_a_declared_value_is_read_with_the_description_written_beside_it(self):
        for kind, source in self.SOURCES:
            with self.subTest(kind=kind):
                _, found = read(
                    kind, source.replace(self.MARKER, "What the reader needs.")
                )
                self.assertEqual(set(), found)

    def test_a_description_that_is_not_a_non_empty_string_is_reported(self):
        for description in ('""', '"   "', "true", "[]"):
            for kind, source in self.SOURCES:
                with self.subTest(kind=kind, description=description):
                    _, found = read(kind, source.replace(self.MARKER, description))
                    self.assertIn("value.invalid-description", found)

    def test_a_record_field_keeps_the_description_it_declares(self):
        """The record field is the one declaration that stores its description.

        Its own reader no longer checks the field, so this holds the stored
        value to what the source wrote rather than to what a second reader
        happened to return.
        """
        record, found = read(
            "records",
            "fields:\n  summary:\n    type: string\n    description: Concise result.\n",
        )
        self.assertEqual(set(), found)
        self.assertEqual("Concise result.", record.fields[0].description)

    def test_one_refused_description_is_one_finding(self):
        """Two readers reached this field, and a reader is owed it once.

        The check that reads every declared value's type reports it, so the
        record field's own reader must not report it again under the record's
        file-level shape check.
        """
        diagnostics = Diagnostics()
        sources.CONSTRUCT_READERS["records"](
            Path("records/thing.yaml"),
            yaml.safe_load('fields:\n  summary:\n    type: string\n    description: ""\n'),
            diagnostics,
        )
        self.assertEqual(
            ["value.invalid-description"],
            [record.code for record in diagnostics.records],
        )


class InvalidTopLevelFieldCodeTests(unittest.TestCase):
    """Every malformed top-level field identifies that field in its code."""

    CASES = (
        ("policies", PolicyTests.GOOD, "title", "", "policy.invalid-title"),
        ("policies", PolicyTests.GOOD, "summary", "", "policy.invalid-summary"),
        ("policies", PolicyTests.GOOD, "rationale", "", "policy.invalid-rationale"),
        ("policies", PolicyTests.GOOD, "provisions", {}, "policy.invalid-provisions"),
        ("rules", RuleTests.GOOD, "title", "", "rule.invalid-title"),
        ("rules", RuleTests.GOOD, "summary", "", "rule.invalid-summary"),
        ("rules", RuleTests.GOOD, "rationale", "", "rule.invalid-rationale"),
        ("rules", RuleTests.GOOD, "phase", "later", "rule.invalid-phase"),
        ("rules", RuleTests.GOOD, "match", {}, "rule.invalid-match"),
        ("rules", RuleTests.GOOD, "require", "", "rule.invalid-command"),
        ("rules", RuleTests.GOOD, "when", "not prose here", "rule.invalid-when"),
        ("rules", RuleTests.GOOD, "unless", "not prose here", "rule.invalid-unless"),
        ("rules", RuleTests.GOOD, "verify", {}, "rule.invalid-verify"),
        ("protocols", ProtocolTests.GOOD, "title", "", "protocol.invalid-title"),
        ("protocols", ProtocolTests.GOOD, "purpose", "", "protocol.invalid-purpose"),
        ("protocols", ProtocolTests.GOOD, "rationale", "", "protocol.invalid-rationale"),
        ("protocols", ProtocolTests.GOOD, "states", [""], "protocol.invalid-states"),
        ("protocols", ProtocolTests.GOOD, "initial", "", "protocol.invalid-initial"),
        ("protocols", ProtocolTests.GOOD, "accepting", [""], "protocol.invalid-accepting"),
        ("protocols", ProtocolTests.GOOD, "data", {}, "protocol.invalid-data"),
        ("protocols", ProtocolTests.GOOD, "hooks", {}, "protocol.invalid-hooks"),
        ("patterns", PatternTests.GOOD, "title", "", "pattern.invalid-title"),
        ("patterns", PatternTests.GOOD, "summary", "", "pattern.invalid-summary"),
        ("patterns", PatternTests.GOOD, "inputs", {}, "pattern.invalid-inputs"),
        ("patterns", PatternTests.GOOD, "procedure", {}, "pattern.invalid-procedure"),
        ("patterns", PatternTests.GOOD, "references", [""], "pattern.invalid-references"),
        ("heuristics", HeuristicTests.GOOD, "title", "", "heuristic.invalid-title"),
        ("heuristics", HeuristicTests.GOOD, "question", "", "heuristic.invalid-question"),
        ("heuristics", HeuristicTests.GOOD, "advice", {}, "heuristic.invalid-advice"),
        ("heuristics", HeuristicTests.GOOD, "references", [""], "heuristic.invalid-references"),
        ("guidance", "summary: State it.\n", "title", "", "guidance.invalid-title"),
        ("guidance", "summary: State it.\n", "summary", "", "guidance.invalid-summary"),
        ("guidance", "summary: State it.\n", "rationale", "", "guidance.invalid-rationale"),
        ("guidance", "summary: State it.\n", "points", [""], "guidance.invalid-points"),
        ("guidance", "summary: State it.\n", "references", [""], "guidance.invalid-references"),
        ("profiles", ProfileTests.GOOD, "title", "", "profile.invalid-title"),
        ("profiles", ProfileTests.GOOD, "points", [""], "profile.invalid-points"),
        ("profiles", ProfileTests.GOOD, "references", [""], "profile.invalid-references"),
        ("records", "title: Result\nfields:\n  value: {type: string}\n", "title", "", "record.invalid-title"),
        ("records", "title: Result\nfields:\n  value: {type: string}\n", "fields", {}, "record.invalid-fields"),
        ("workflows", WorkflowShapeTests.GOOD, "title", "", "workflow.invalid-title"),
        ("workflows", WorkflowShapeTests.GOOD, "description", "", "workflow.invalid-description"),
        ("workflows", WorkflowShapeTests.GOOD, "entry", "", "workflow.invalid-entry"),
        ("workflows", WorkflowShapeTests.GOOD, "inputs", {}, "workflow.invalid-inputs"),
        ("workflows", WorkflowShapeTests.GOOD, "outcomes", {}, "workflow.invalid-outcomes"),
        ("workflows", WorkflowShapeTests.GOOD, "policies", [""], "workflow.invalid-policies"),
        ("workflows", WorkflowShapeTests.GOOD, "rules", [""], "workflow.invalid-rules"),
        ("workflows", WorkflowShapeTests.GOOD, "protocols", [""], "workflow.invalid-protocols"),
        ("workflows", WorkflowShapeTests.GOOD, "guidance", [""], "workflow.invalid-guidance"),
        ("workflows", WorkflowShapeTests.GOOD, "steps", {}, "workflow.invalid-steps"),
    )

    def test_each_invalid_field_has_its_own_code(self):
        for kind, source, field, value, code in self.CASES:
            with self.subTest(kind=kind, field=field):
                data = yaml.safe_load(source)
                data[field] = value
                _, found = read(kind, yaml.safe_dump(data, sort_keys=False))
                self.assertIn(code, found)


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
