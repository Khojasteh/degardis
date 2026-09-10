"""Authoring diagnostics distinguish declared reads and costs from prose guesses."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from degardis.dexpr import TypeEnvironment, check_expression, parse_expression, parse_type
from tests.support import codes, compiled, copy_skills, edit_yaml, inspect_one, write_text


class EnumMemberTests(unittest.TestCase):
    def test_enum_list_membership_checks_the_declared_members(self):
        declared, problem = parse_type({"list": {"enum": ["policy", "rule"]}})
        self.assertEqual("", problem)
        environment = TypeEnvironment(values={("result", "corpus"): declared}, records={})
        for member in ("policy", "rule", "profile"):
            for expression in (
                f"contains(result.corpus, '{member}')",
                f"'{member}' in result.corpus",
                f"'{member}' not in result.corpus",
                f"contains(result.corpus, ('{member}'))",
            ):
                with self.subTest(expression=expression):
                    found = {item.code for item in check_expression(parse_expression(expression), environment)}
                    self.assertEqual({"expr.unknown-member"} if member == "profile" else set(), found)

    def test_open_lists_and_wrong_types_keep_their_own_contract(self):
        declared, _ = parse_type({"list": "string"})
        environment = TypeEnvironment(values={("result", "corpus"): declared}, records={})
        self.assertEqual([], check_expression(parse_expression("contains(result.corpus, 'profile')"), environment))
        self.assertEqual(
            {"expr.type-mismatch"},
            {item.code for item in check_expression(parse_expression("contains(result.corpus, 1)"), environment)},
        )


class AuthoringCheckTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = copy_skills(Path(directory.name))
        self.skill = self.root / "beta"
        self.workflow = self.skill / "workflows/run.yaml"

    def findings(self, code):
        return [item for item in inspect_one(self.skill)["diagnostics"] if item.code == code]

    def test_record_outcome_without_capture_warns_but_empty_outcome_does_not(self):
        write_text(self.skill / "workflows/child.yaml", """title: Read the subject
description: Read the supplied subject and report it.
outcomes:
  done: {record: note}
entry: finish
steps:
  finish:
    return:
      outcome: done
      with: {text: {literal: observed}}
""")
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["next"] = "call-child"
            data["steps"]["call-child"] = {"use": "child", "on": {"done": "finish"}}
        self.assertEqual(["warning"], [item.severity for item in self.findings("workflow.unbound-outcome")])
        with edit_yaml(self.workflow) as data:
            data["steps"]["call-child"]["on"]["done"] = {"next": "finish", "as": "response"}
        self.assertEqual([], self.findings("workflow.unbound-outcome"))
        self.assertEqual(1, len(self.findings("value.unread")))
        with edit_yaml(self.workflow) as data:
            data["steps"]["finish"]["return"]["with"]["text"] = {"from": "result.response.text"}
            data["steps"]["act"].pop("produces")
        self.assertEqual([], self.findings("value.unread"))
        with edit_yaml(self.skill / "workflows/child.yaml") as data:
            data["outcomes"]["done"] = {}
            data["steps"]["finish"]["return"].pop("with")
        with edit_yaml(self.workflow) as data:
            data["steps"]["call-child"]["on"]["done"] = "finish"
            data["steps"]["finish"]["return"]["with"]["text"] = {"literal": "finished"}
        self.assertEqual([], self.findings("workflow.unbound-outcome"))

    def test_gate_and_decide_reads_are_checked_and_rendered(self):
        for form, alternatives in (("gate", "states"), ("decide", "choices")):
            with self.subTest(form=form):
                with edit_yaml(self.workflow) as data:
                    data["steps"]["act"]["produces"]["evidence"] = {"type": "string"}
                    data["steps"]["act"]["next"] = "judge"
                    data["steps"]["judge"] = {
                        form: "Judge the evidence.",
                        alternatives: {
                            "ready": {"command": "Accept the evidence.", "next": "finish"},
                            "refused": {"command": "Report the refusal.", "next": "finish"},
                        },
                    }
                self.assertEqual(1, len(self.findings("value.unread")))
                with edit_yaml(self.workflow) as data:
                    data["steps"]["judge"]["uses"] = ["result.evidence"]
                _, result, diagnostics = compiled(self.skill)
                self.assertEqual([], diagnostics.errors)
                self.assertNotIn("value.unread", {item.code for item in diagnostics.records})
                node = next(node for node in result.lowered.all_nodes() if node.step == "judge")
                self.assertIn("result.evidence", node.available)
                self.assertIn("`result.evidence`", "\n".join(result.rendered.execution_modules.values()))
                with edit_yaml(self.workflow) as data:
                    data["steps"]["judge"]["uses"] = ["result.absent"]
                self.assertEqual(1, len(self.findings("expr.unknown-value")))

    def test_branch_and_bound_verification_count_as_reads(self):
        with edit_yaml(self.workflow) as data:
            data["steps"]["finish"]["return"]["with"]["text"] = {"literal": "finished"}
        self.assertEqual(1, len(self.findings("value.unread")))
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["next"] = "route"
            data["steps"]["route"] = {"branch": [{"when": "length(result.note) > 0", "next": "finish"}, {"otherwise": "finish"}]}
        self.assertEqual([], self.findings("value.unread"))
        with edit_yaml(self.workflow) as data:
            data["steps"].pop("route")
            data["steps"]["act"]["next"] = "finish"
            data["rules"] = ["check-note"]
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["rules"] = ["rules/*.yaml"]
        write_text(self.skill / "rules/check-note.yaml", """title: Check the observation
summary: Check the produced text.
phase: before-return
match: {outcomes: [done]}
require: Confirm the produced text is present.
verify: {expression: 'length(result.note) > 0'}
""")
        self.assertEqual([], self.findings("value.unread"))

    def test_identifier_warning_strips_code_and_respects_token_boundaries(self):
        for text, count in (
            ("Read note before continuing.", 1),
            ("Read `note` before continuing.", 0),
            ("Read ``a `note` span`` before continuing.", 0),
            ("Read notebook and release-note before continuing.", 0),
        ):
            with self.subTest(text=text):
                with edit_yaml(self.workflow) as data:
                    data["steps"]["act"]["action"] = text
                self.assertEqual(count, len(self.findings("source.ordinary-identifier")))
        write_text(self.skill / "workflows/unreached.yaml", """description: Read note before continuing.
outcomes: {done: {}}
entry: finish
steps: {finish: {return: {outcome: done}}}
""")
        self.assertEqual([], self.findings("source.ordinary-identifier"))

    def test_protocol_update_consumes_a_result_without_a_step_read(self):
        with edit_yaml(self.workflow) as data:
            data["steps"]["finish"]["return"]["with"]["text"] = {"literal": "finished"}
            data["protocols"] = ["keep-observation"]
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["protocols"] = ["protocols/*.yaml"]
        write_text(self.skill / "protocols/keep-observation.yaml", """purpose: Retain the produced text.
states: [empty, held]
initial: empty
accepting: [held]
data:
  text: {type: {optional: string}}
hooks:
  hold:
    phase: after
    match: {forms: [action]}
    from: [empty]
    command: Retain the produced text.
    set: {text: {from: result.note}}
    to: held
""")
        result = inspect_one(self.skill)
        self.assertEqual([], result["errors"])
        self.assertNotIn("value.unread", {item.code for item in result["diagnostics"]})

    def test_protocol_update_reads_a_result_before_a_later_definition(self):
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["next"] = "replace"
            data["steps"]["act"]["subjects"] = ["observation.make"]
            data["steps"]["replace"] = {
                "action": "Replace the produced text.",
                "produces": {"note": {"type": "string"}},
                "next": "finish",
            }
            data["protocols"] = ["keep-observation"]
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["protocols"] = ["protocols/*.yaml"]
        write_text(self.skill / "protocols/keep-observation.yaml", """purpose: Retain the produced text.
states: [empty, held]
initial: empty
accepting: [held]
data:
  text: {type: {optional: string}}
hooks:
  hold:
    phase: after
    match: {forms: [action], subjects: [observation.make]}
    from: [empty]
    command: Retain the produced text.
    set: {text: {from: result.note}}
    to: held
""")
        self.assertEqual([], self.findings("value.overwritten"))

    def test_unused_declared_inputs_and_protocol_data_are_reported(self):
        with edit_yaml(self.workflow) as data:
            data.setdefault("inputs", {})["unused"] = {"type": "string"}
        self.assertEqual(1, len(self.findings("value.unread")))

        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"]["patterns"] = ["patterns/*.yaml"]
            data["content"]["protocols"] = ["protocols/*.yaml"]
        write_text(self.skill / "patterns/unused.yaml", """title: Unused input
summary: Carry out one action.
inputs:
  subject: {type: string}
procedure:
  act: {command: Act on the request.}
""")
        write_text(self.skill / "protocols/unused.yaml", """purpose: Track one lifecycle.
states: [clear]
initial: clear
accepting: [clear]
data:
  note: {type: {optional: string}}
hooks:
  enter:
    phase: enter
    from: [clear]
    command: Start the lifecycle.
""")
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["next"] = "apply"
            data["steps"]["apply"] = {
                "pattern": "unused",
                "with": {"subject": {"literal": "request"}},
                "protocols": ["unused"],
                "next": "finish",
            }
        messages = [item.message for item in self.findings("value.unread")]
        self.assertTrue(any("pattern unused input.subject" in item for item in messages))
        self.assertTrue(any("protocol unused data.note" in item for item in messages))

    def test_resources_require_declarations_even_when_prose_names_them(self):
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"].update(assets=["assets/*.md"], scripts=["scripts/*.py"])
        write_text(self.skill / "assets/template.md", "Template\n")
        write_text(self.skill / "scripts/helper.py", "print('ready')\n")
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["action"] = "Read assets/template.md and scripts/helper.py."
        self.assertEqual(2, len(self.findings("resource.unconsumed")))
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["resource"] = {"fill": "assets/template.md"}
        self.assertEqual(1, len(self.findings("resource.unconsumed")))

    def test_binding_bytes_measure_artifact_blocks_and_inline_lines(self):
        self.skill = self.root / "alpha"
        for phase in ("before", "during"):
            with self.subTest(phase=phase):
                with edit_yaml(self.skill / "policies/workflow-scope.yaml") as data:
                    provision = data["provisions"]["stay-on-subject"]
                    provision["phase"] = phase
                    provision["require"] = "Keep the café summary concise."
                _, result, diagnostics = compiled(self.skill)
                self.assertEqual([], diagnostics.errors)
                row = next(row for row in inspect_one(self.skill)["lowering"] if row["id"] == "workflow-scope.stay-on-subject")
                text = "\n".join(result.rendered.execution_modules.values())
                if phase == "before":
                    block = next(block for block in re.split(r"(?m)(?=^### )", text) if block.startswith(f"### [`{row['nodes'][0]}`]"))
                    expected = len((block.strip("\n") + "\n").encode("utf-8"))
                else:
                    expected = sum(len((line + "\n").encode("utf-8")) for line in text.splitlines() if "Keep the café summary concise." in line)
                self.assertEqual(expected, row["bytes"])
                self.assertGreater(row["bytes"], 0)

    def test_broadening_a_selector_charges_each_placement_once(self):
        self.skill = self.root / "alpha"
        policy = self.skill / "policies/workflow-scope.yaml"
        with edit_yaml(policy) as data:
            data["provisions"]["stay-on-subject"]["phase"] = "during"
        first = next(row for row in inspect_one(self.skill)["lowering"] if row["id"] == "workflow-scope.stay-on-subject")
        with edit_yaml(policy) as data:
            data["provisions"]["stay-on-subject"]["match"] = {"forms": ["action"]}
        second = next(row for row in inspect_one(self.skill)["lowering"] if row["id"] == first["id"])
        self.assertEqual(1, len(first["nodes"]))
        self.assertEqual(2, len(second["nodes"]))
        self.assertEqual(first["bytes"] * 2, second["bytes"])


class ProducedValueDefaultTests(unittest.TestCase):
    """A produced value declaring a default is defined wherever it is read."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = copy_skills(Path(directory.name))
        self.skill = self.root / "beta"
        self.workflow = self.skill / "workflows/run.yaml"
        with edit_yaml(self.workflow) as data:
            data["steps"]["act"]["next"] = "route"
            data["steps"]["route"] = {
                "branch": [
                    {"when": "length(input.subject) > 0", "next": "enrich"},
                    {"otherwise": "compose"},
                ]
            }
            data["steps"]["enrich"] = {
                "action": "Gather the further observations the subject supports.",
                "produces": {"extra": {"type": {"list": "string"}}},
                "next": "compose",
            }
            data["steps"]["compose"] = {
                "action": "Compose the note from every observation gathered.",
                "uses": ["result.extra"],
                "next": "finish",
            }

    def declare(self, **fields):
        with edit_yaml(self.workflow) as data:
            data["steps"]["enrich"]["produces"]["extra"] = fields

    def findings(self, code, severity="error"):
        return [
            item
            for item in inspect_one(self.skill)["diagnostics"]
            if item.code == code and item.severity == severity
        ]

    def test_a_default_defines_the_value_on_a_path_that_produced_none(self):
        self.assertEqual(1, len(self.findings("expr.undefined-value")))
        self.declare(type={"list": "string"}, default=[])
        self.assertEqual(set(), codes(self.skill))

    def test_the_default_is_checked_against_the_type_it_stands_for(self):
        for declared, default in (
            ({"list": "string"}, "none"),
            ({"list": "string"}, [1]),
            ("string", 1),
            ("integer", "one"),
            ({"enum": ["brief", "full"]}, "partial"),
            ({"optional": "string"}, "none"),
            ({"record": "note"}, {"text": "none"}),
        ):
            with self.subTest(declared=declared, default=default):
                self.declare(type=declared, default=default)
                self.assertEqual(
                    1,
                    len(self.findings("value.invalid-default")),
                    msg=f"{default!r} was accepted for {declared!r}",
                )

    def test_an_empty_list_stands_for_any_list_including_one_of_records(self):
        self.declare(type={"list": {"record": "note"}}, default=[])
        self.assertEqual([], self.findings("value.invalid-default"))

    def test_a_default_is_declared_only_where_a_step_produces_the_value(self):
        for location in ("inputs", "record", "pattern"):
            with self.subTest(location=location):
                with edit_yaml(self.workflow) as data:
                    data["inputs"]["subject"] = {"type": "string", "default": "none"}
                if location == "record":
                    with edit_yaml(self.skill / "records/note.yaml") as data:
                        data["fields"]["text"] = {"type": "string", "default": "none"}
                self.assertIn("value.invalid-type", codes(self.skill))

    def test_two_producers_of_one_value_agree_on_its_default(self):
        with edit_yaml(self.workflow) as data:
            data["steps"]["enrich"]["produces"]["extra"] = {
                "type": {"list": "string"},
                "default": [],
            }
            data["steps"]["compose"]["produces"] = {
                "extra": {"type": {"list": "string"}, "default": ["none"]}
            }
        self.assertEqual(1, len(self.findings("workflow.conflicting-value")))

    def test_a_defaulted_value_still_needs_a_reader(self):
        self.declare(type={"list": "string"}, default=[])
        with edit_yaml(self.workflow) as data:
            data["steps"]["compose"].pop("uses")
        self.assertEqual(1, len(self.findings("value.unread", "warning")))

if __name__ == "__main__":
    unittest.main()
