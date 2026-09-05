"""DExpr: the grammar, the types, the guards, and the bindings.

Expectations here come from the format's own grammar and type rules rather than
from the parser: each case states the expression, the environment it is
evaluated in, and the check code the format says applies.
"""

from __future__ import annotations

import unittest

from degardis.dexpr import (
    BOOLEAN,
    INTEGER,
    NAMESPACES,
    STRING,
    ExpressionError,
    TypeEnvironment,
    ValueType,
    check_binding,
    check_expression,
    parse_binding,
    parse_expression,
    parse_reference,
    parse_type,
    parse_value_declaration,
)


FINDING = ValueType("record", record="finding")
OPTIONAL_FINDING = ValueType("optional", item=FINDING)
MODE = ValueType("enum", values=("execute", "report-only"))


def environment(**overrides) -> TypeEnvironment:
    values = {
        ("input", "request"): STRING,
        ("input", "wide"): BOOLEAN,
        ("result", "finding"): FINDING,
        ("result", "maybe"): OPTIONAL_FINDING,
        ("decision", "choose-mode"): MODE,
        ("gate", "authorization"): ValueType("enum", values=("passed", "refused")),
        ("call", "check"): ValueType("enum", values=("confirmed",)),
        ("state", "held"): BOOLEAN,
    }
    values.update(overrides.pop("values", {}))
    records = {
        "finding": {
            "summary": STRING,
            "tags": ValueType("list", item=STRING),
            "count": INTEGER,
        }
    }
    return TypeEnvironment(values=values, records=records, **overrides)


def problems(text: str, **kwargs) -> set[str]:
    return {
        problem.code
        for problem in check_expression(parse_expression(text), environment(**kwargs))
    }


class GrammarTests(unittest.TestCase):
    def test_every_namespace_is_a_reference_root(self):
        for namespace in NAMESPACES:
            with self.subTest(namespace=namespace):
                reference = parse_reference(f"{namespace}.value")
                self.assertEqual(namespace, reference.namespace)
                self.assertEqual(("value",), reference.path)

    def test_a_reference_walks_fields_and_positions(self):
        reference = parse_reference("result.finding.tags[0]")
        self.assertEqual(("finding", "tags", 0), reference.path)

    def test_a_bare_namespace_names_no_value(self):
        with self.assertRaises(ExpressionError):
            parse_reference("result")

    def test_an_identifier_may_carry_hyphens_and_digits(self):
        self.assertEqual(set(), problems('decision.choose-mode == "execute"'))

    def test_operators_and_functions_parse(self):
        for text in (
            'input.request == "x"',
            'input.request != "x"',
            "result.finding.count < 2",
            "result.finding.count <= 2",
            "result.finding.count > 2",
            "result.finding.count >= 2",
            '"a" in result.finding.tags',
            '"a" not in result.finding.tags',
            "not input.wide",
            "input.wide and not input.wide",
            "input.wide or input.wide",
            "(input.wide)",
            "exists(result.maybe)",
            "length(result.finding.tags) == 1",
            'contains(result.finding.tags, "a")',
        ):
            with self.subTest(text=text):
                self.assertEqual(set(), problems(text))

    def test_prose_is_not_an_expression(self):
        with self.assertRaises(ExpressionError):
            parse_expression("the request authorizes a contract change")

    def test_an_unclosed_quote_is_reported_with_its_position(self):
        with self.assertRaises(ExpressionError) as raised:
            parse_expression('input.request == "x')
        self.assertGreater(raised.exception.position, 0)

    def test_the_text_is_kept_as_written(self):
        text = 'decision.choose-mode == "execute"'
        self.assertEqual(text, parse_expression(f"  {text}  ").render())


class TypeTests(unittest.TestCase):
    def test_a_condition_must_be_a_truth(self):
        self.assertEqual({"expr.type-mismatch"}, problems("input.request"))

    def test_unknown_values_records_and_fields_are_reported(self):
        self.assertEqual({"expr.unknown-value"}, problems('result.absent == "x"'))
        self.assertEqual({"expr.unknown-value"}, problems("result.finding.absent == 1"))

    def test_a_value_not_every_path_produced_is_reported(self):
        self.assertEqual(
            {"expr.undefined-value"},
            problems(
                'result.finding.summary == "x"',
                defined={("input", "request")},
            ),
        )

    def test_comparing_unlike_types_is_reported(self):
        self.assertEqual({"expr.type-mismatch"}, problems("input.request == 1"))
        self.assertEqual({"expr.type-mismatch"}, problems('input.wide < "a"'))

    def test_membership_needs_a_list_or_text_on_the_right(self):
        self.assertEqual({"expr.type-mismatch"}, problems("input.request in input.wide"))

    def test_an_enum_compares_against_a_string(self):
        self.assertEqual(set(), problems('gate.authorization == "passed"'))

    def test_length_and_contains_need_something_with_members(self):
        self.assertEqual({"expr.type-mismatch"}, problems("length(input.wide) > 0"))
        self.assertEqual(
            {"expr.type-mismatch"}, problems('contains(input.wide, "a")')
        )


class GuardTests(unittest.TestCase):
    """A possibly absent value has to be guarded in the same expression."""

    def test_an_unguarded_optional_is_reported(self):
        self.assertEqual(
            {"expr.unguarded-optional"}, problems('result.maybe.summary == "x"')
        )

    def test_a_guard_to_the_left_of_an_and_covers_the_read(self):
        self.assertEqual(
            set(), problems('exists(result.maybe) and result.maybe.summary == "x"')
        )

    def test_a_negated_guard_to_the_left_of_an_or_covers_the_read(self):
        self.assertEqual(
            set(),
            problems('not exists(result.maybe) or result.maybe.summary == "x"'),
        )

    def test_a_guard_on_the_wrong_side_does_not_cover_the_read(self):
        self.assertEqual(
            {"expr.unguarded-optional"},
            problems('result.maybe.summary == "x" and exists(result.maybe)'),
        )

    def test_the_optional_itself_may_be_tested_for_presence(self):
        self.assertEqual(set(), problems("exists(result.maybe)"))


class DeclaredTypeTests(unittest.TestCase):
    def test_the_scalar_types(self):
        for name in ("string", "integer", "number", "boolean"):
            with self.subTest(name=name):
                found, problem = parse_type(name)
                self.assertEqual(ValueType(name), found)
                self.assertEqual("", problem)

    def test_the_compound_types(self):
        cases = {
            ("enum",): {"enum": ["direct", "delegated"]},
            ("list",): {"list": "string"},
            ("record",): {"record": "finding"},
            ("optional",): {"optional": "string"},
        }
        for label, declaration in cases.items():
            with self.subTest(label=label):
                found, problem = parse_type(declaration)
                self.assertIsNotNone(found)
                self.assertEqual("", problem)
                self.assertEqual(label[0], found.kind)

    def test_an_unknown_type_is_refused(self):
        found, problem = parse_type("text")
        self.assertIsNone(found)
        self.assertNotEqual("", problem)

    def test_an_optional_cannot_wrap_an_optional(self):
        self.assertIsNone(parse_type({"optional": {"optional": "string"}})[0])

    def test_a_declared_value_names_one_of_type_or_record(self):
        self.assertIsNotNone(parse_value_declaration({"type": "string"})[0])
        self.assertIsNotNone(parse_value_declaration({"record": "finding"})[0])
        self.assertIsNone(
            parse_value_declaration({"type": "string", "record": "finding"})[0]
        )
        self.assertIsNone(parse_value_declaration({})[0])

    def test_a_description_sits_beside_a_declared_type(self):
        found, problem = parse_value_declaration(
            {"type": "string", "description": "What it is."}
        )
        self.assertEqual(STRING, found)
        self.assertEqual("", problem)


class BindingTests(unittest.TestCase):
    def test_a_binding_is_tagged(self):
        found, _ = parse_binding({"from": "input.request"})
        self.assertEqual("from", found.kind)
        found, _ = parse_binding({"literal": "author"})
        self.assertEqual("literal", found.kind)

    def test_an_untagged_value_is_refused(self):
        self.assertIsNone(parse_binding("input.request")[0])
        self.assertIsNone(parse_binding({"from": "input.request", "literal": 1})[0])

    def test_a_literal_must_fit_its_destination(self):
        binding, _ = parse_binding({"literal": "author"})
        self.assertEqual([], check_binding(binding, STRING, environment()))
        self.assertEqual(
            ["value.mistyped-binding"],
            [item.code for item in check_binding(binding, INTEGER, environment())],
        )

    def test_a_literal_must_be_one_of_an_enum(self):
        binding, _ = parse_binding({"literal": "elsewhere"})
        self.assertEqual(
            ["value.mistyped-binding"],
            [item.code for item in check_binding(binding, MODE, environment())],
        )

    def test_a_read_value_must_fit_its_destination(self):
        binding, _ = parse_binding({"from": "result.finding"})
        self.assertEqual([], check_binding(binding, FINDING, environment()))
        self.assertEqual(
            ["value.mistyped-binding"],
            [item.code for item in check_binding(binding, STRING, environment())],
        )

    def test_a_possibly_absent_value_needs_an_optional_destination(self):
        binding, _ = parse_binding({"from": "result.maybe"})
        self.assertEqual([], check_binding(binding, OPTIONAL_FINDING, environment()))
        self.assertEqual(
            ["value.mistyped-binding"],
            [item.code for item in check_binding(binding, FINDING, environment())],
        )

    def test_an_unknown_value_is_reported_as_unknown(self):
        binding, _ = parse_binding({"from": "result.absent"})
        self.assertEqual(
            ["expr.unknown-value"],
            [item.code for item in check_binding(binding, STRING, environment())],
        )


if __name__ == "__main__":
    unittest.main()
