"""DExpr: the value types, bindings, and side-effect-free expressions of Format 2.

Every machine condition in a Format 2 source is parsed here rather than carried
as prose. A branch that reads `decision.choose-mode == "execute"` is a condition
the compiler can check against the values that exist at that point in the
workflow; the same sentence written in English is a condition only an agent can
check, and only after it has guessed what the author meant.

Three things live in one module because they are one contract. A type says what
a value is, a binding says where a value comes from, and an expression reads
values and yields a truth. Splitting them would leave each half unable to say
what it means: `{from: result.inspection.summary}` is a binding whose type is a
record field's type, resolved through the same reference walk an expression uses.

Nothing here reaches a tool, a script, a clock, a random source, a network, or a
host API. An expression is a question about values the workflow already has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _continues_as_name(text: str, end: int) -> bool:
    """Whether digits matched so far are the start of a name rather than a number.

    `1:30` is not valid here, but `plan-2` and `2-step` are names: a
    lowercase-hyphenated identifier may begin with a digit. So a run of digits
    is a number only when nothing that belongs to a name follows it.
    """
    return end < len(text) and (text[end].isalnum() or text[end] == "-")


# Where a reference reads from. Each namespace is written by exactly one part of
# a workflow, which is what lets the compiler say whether a value exists yet:
# `input` by the caller, `result` by an action's `produces`, `decision` and
# `gate` by the step whose id they name, `call` by a call's receipt, and `state`
# by the protocol frame the reading hook belongs to.
NAMESPACES = ("input", "result", "decision", "gate", "call", "state")

FUNCTIONS = ("exists", "length", "contains")

SCALAR_TYPES = ("string", "integer", "number", "boolean")

# Every operator the tokenizer will accept. Nothing else validates a
# comparison: an operator absent here never becomes an `operator` token, so
# the expression fails to parse instead of reaching the type checker.
COMPARISONS = ("==", "!=", "<=", ">=", "<", ">")

MEMBERSHIP = ("in", "not in")

KEYWORD_LITERALS = {"true": True, "false": False, "null": None}

# The check a parse failure belongs to. It sits here, apart from the codes
# further down that this module reports itself, because this one is raised:
# it travels on the exception so that whoever catches one reports the same
# code without writing it again, as `DegardisError` does for a raised failure.
INVALID_SYNTAX = "expr.invalid-syntax"


class ExpressionError(ValueError):
    """One expression that cannot be parsed, and where in the text it failed."""

    def __init__(self, message: str, position: int = 0) -> None:
        super().__init__(message)
        self.position = position
        self.code = INVALID_SYNTAX


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueType:
    """What one declared value is, in the terms every check compares against.

    A type is a value rather than a class hierarchy so that two declarations
    written in different files compare equal when they say the same thing, which
    is what a binding check and a comparison check both need.
    """

    kind: str
    values: tuple[str, ...] = ()
    item: ValueType | None = None
    record: str = ""

    def render(self) -> str:
        if self.kind == "enum":
            return "one of " + ", ".join(self.values)
        if self.kind == "list":
            item = self.item.render() if self.item else "?"
            return f"list of {item}"
        if self.kind == "record":
            return f"record {self.record}"
        if self.kind == "optional":
            item = self.item.render() if self.item else "?"
            return f"optional {item}"
        return self.kind

    @property
    def optional(self) -> bool:
        return self.kind == "optional"

    @property
    def base(self) -> ValueType:
        """The type this one carries, with any optional wrapper removed."""
        if self.kind == "optional" and self.item is not None:
            return self.item.base
        return self


STRING = ValueType("string")
INTEGER = ValueType("integer")
NUMBER = ValueType("number")
BOOLEAN = ValueType("boolean")


def parse_type(data: Any) -> tuple[ValueType | None, str]:
    """Read one declared type, or say what is wrong with the declaration."""
    if isinstance(data, str):
        if data in SCALAR_TYPES:
            return ValueType(data), ""
        return None, (
            f"{data!r} is not a value type; write one of "
            f"{', '.join(SCALAR_TYPES)}, or a mapping naming enum, list, "
            "record, or optional"
        )
    if not isinstance(data, dict) or len(data) != 1:
        return None, (
            "a value type is one of "
            f"{', '.join(SCALAR_TYPES)}, or a mapping with exactly one of "
            "enum, list, record, optional"
        )
    key, value = next(iter(data.items()))
    if key == "enum":
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) for item in value)
            or any(not ID_PATTERN.fullmatch(item) for item in value)
        ):
            return None, (
                "enum takes a non-empty list of lowercase-hyphenated names"
            )
        if len(set(value)) != len(value):
            return None, "enum names a value twice"
        return ValueType("enum", values=tuple(value)), ""
    if key == "list":
        item, problem = parse_type(value)
        if item is None:
            return None, f"list item type: {problem}"
        if item.kind == "optional":
            return None, "a list item type cannot be optional"
        return ValueType("list", item=item), ""
    if key == "record":
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            return None, "record takes one lowercase-hyphenated record id"
        return ValueType("record", record=value), ""
    if key == "optional":
        item, problem = parse_type(value)
        if item is None:
            return None, f"optional value type: {problem}"
        if item.kind == "optional":
            return None, "an optional type cannot wrap another optional"
        return ValueType("optional", item=item), ""
    return None, (
        f"{key!r} is not a value type; write enum, list, record, or optional"
    )


def parse_value_declaration(data: Any) -> tuple[ValueType | None, str]:
    """Read a declared value: `{type: T}`, or `{record: R}` as its short form.

    A workflow input, a produced value, a record field, and a pattern input all
    declare the same thing, so all four are read here. `record:` is accepted
    directly because a produced value is usually a record and `type: {record: R}`
    says the same thing twice.
    """
    if not isinstance(data, dict):
        return None, "a declared value is a mapping naming its type"
    fields = set(data) - {"description"}
    if fields == {"type"}:
        return parse_type(data["type"])
    if fields == {"record"}:
        return parse_type({"record": data["record"]})
    return None, (
        "a declared value names exactly one of type or record, with an "
        "optional description"
    )


# --------------------------------------------------------------------------
# Bindings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """Where one supplied value comes from: another value, or a written literal.

    Tagged rather than inferred, because `author` is a perfectly good string and
    a perfectly good value name. `{from: ...}` and `{literal: ...}` say which was
    meant, so nothing has to guess and no source has to avoid a word.
    """

    kind: str
    reference: Reference | None = None
    literal: Any = None

    def render(self) -> str:
        if self.kind == "from" and self.reference is not None:
            return f"`{self.reference.render()}`"
        return f"`{_render_literal(self.literal)}`"


def parse_binding(data: Any) -> tuple[Binding | None, str]:
    if not isinstance(data, dict) or len(data) != 1:
        return None, "a binding is a mapping with exactly one of from or literal"
    key, value = next(iter(data.items()))
    if key == "from":
        if not isinstance(value, str):
            return None, "from takes one value reference, such as input.request"
        try:
            reference = parse_reference(value)
        except ExpressionError as exc:
            return None, f"from: {exc}"
        return Binding("from", reference=reference), ""
    if key == "literal":
        if isinstance(value, (dict, list)):
            return None, "literal takes a string, number, boolean, or null"
        return Binding("literal", literal=value), ""
    return None, f"{key!r} is not a binding; write from or literal"


def _render_literal(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


# --------------------------------------------------------------------------
# Expression syntax
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    value: Any

    def render(self) -> str:
        return _render_literal(self.value)


@dataclass(frozen=True)
class Reference:
    namespace: str
    path: tuple[Any, ...]

    def render(self) -> str:
        text = self.namespace
        for part in self.path:
            text += f"[{part}]" if isinstance(part, int) else f".{part}"
        return text

    @property
    def root(self) -> str:
        return str(self.path[0]) if self.path else ""


@dataclass(frozen=True)
class ListLiteral:
    items: tuple[Any, ...]

    def render(self) -> str:
        return "[" + ", ".join(render(item) for item in self.items) + "]"


@dataclass(frozen=True)
class Function:
    name: str
    arguments: tuple[Any, ...]

    def render(self) -> str:
        return f"{self.name}(" + ", ".join(render(a) for a in self.arguments) + ")"


@dataclass(frozen=True)
class Negation:
    operand: Any

    def render(self) -> str:
        return f"not {render(self.operand)}"


@dataclass(frozen=True)
class Conjunction:
    operands: tuple[Any, ...]

    def render(self) -> str:
        return " and ".join(render(item) for item in self.operands)


@dataclass(frozen=True)
class Disjunction:
    operands: tuple[Any, ...]

    def render(self) -> str:
        return " or ".join(render(item) for item in self.operands)


@dataclass(frozen=True)
class Comparison:
    left: Any
    operator: str
    right: Any

    def render(self) -> str:
        return f"{render(self.left)} {self.operator} {render(self.right)}"


@dataclass(frozen=True)
class Grouping:
    inner: Any

    def render(self) -> str:
        return f"({render(self.inner)})"


def render(node: Any) -> str:
    return node.render()


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    position: int
    value: Any = None


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character in " \t\n":
            index += 1
            continue
        if character in "()[],.":
            tokens.append(Token(character, character, index))
            index += 1
            continue
        # Two characters first, so `<=` is one operator rather than `<` and a
        # stray `=`. The length guard matters at the end of the text, where the
        # slice returns the single character `<` and would otherwise consume a
        # character that is not there.
        two = text[index : index + 2]
        if len(two) == 2 and two in COMPARISONS:
            tokens.append(Token("operator", two, index))
            index += 2
            continue
        if character in COMPARISONS:
            tokens.append(Token("operator", character, index))
            index += 1
            continue
        if character in "\"'":
            end = text.find(character, index + 1)
            if end < 0:
                raise ExpressionError("a quoted value is never closed", index)
            tokens.append(
                Token("string", text[index : end + 1], index, text[index + 1 : end])
            )
            index = end + 1
            continue
        number = _NUMBER_PATTERN.match(text, index)
        if number is not None and not _continues_as_name(text, number.end()):
            tokens.append(_number_token(number.group(0), index))
            index = number.end()
            continue
        identifier = ID_PATTERN.match(text, index)
        if identifier is not None and identifier.start() == index:
            tokens.append(Token("name", identifier.group(0), index))
            index = identifier.end()
            continue
        raise ExpressionError(
            f"{character!r} is not part of an expression", index
        )
    tokens.append(Token("end", "", length))
    return tokens


def _number_token(text: str, position: int) -> Token:
    value: Any = float(text) if "." in text else int(text)
    return Token("number", text, position, value)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _tokenize(text)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def take(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def accept_name(self, word: str) -> bool:
        if self.current.kind == "name" and self.current.text == word:
            self.index += 1
            return True
        return False

    def expect(self, kind: str, label: str) -> Token:
        if self.current.kind != kind:
            raise ExpressionError(
                f"expected {label}, found {self.current.text or 'the end'!r}",
                self.current.position,
            )
        return self.take()

    def parse(self) -> Any:
        node = self.parse_or()
        if self.current.kind != "end":
            raise ExpressionError(
                f"unexpected {self.current.text!r} after a complete expression",
                self.current.position,
            )
        return node

    def parse_or(self) -> Any:
        operands = [self.parse_and()]
        while self.accept_name("or"):
            operands.append(self.parse_and())
        return operands[0] if len(operands) == 1 else Disjunction(tuple(operands))

    def parse_and(self) -> Any:
        operands = [self.parse_unary()]
        while self.accept_name("and"):
            operands.append(self.parse_unary())
        return operands[0] if len(operands) == 1 else Conjunction(tuple(operands))

    def parse_unary(self) -> Any:
        if (
            self.current.kind == "name"
            and self.current.text == "not"
            and not (
                self.tokens[self.index + 1].kind == "name"
                and self.tokens[self.index + 1].text == "in"
            )
        ):
            self.index += 1
            return Negation(self.parse_unary())
        return self.parse_comparison()

    def parse_comparison(self) -> Any:
        left = self.parse_primary()
        if self.current.kind == "operator":
            operator = self.take().text
            return Comparison(left, operator, self.parse_primary())
        if self.current.kind == "name" and self.current.text == "in":
            self.index += 1
            return Comparison(left, "in", self.parse_primary())
        if (
            self.current.kind == "name"
            and self.current.text == "not"
            and self.tokens[self.index + 1].kind == "name"
            and self.tokens[self.index + 1].text == "in"
        ):
            self.index += 2
            return Comparison(left, "not in", self.parse_primary())
        return left

    def parse_primary(self) -> Any:
        token = self.current
        if token.kind == "(":
            self.index += 1
            inner = self.parse_or()
            self.expect(")", "a closing parenthesis")
            return Grouping(inner)
        if token.kind == "[":
            self.index += 1
            items: list[Any] = []
            if self.current.kind != "]":
                items.append(self.parse_or())
                while self.current.kind == ",":
                    self.index += 1
                    items.append(self.parse_or())
            self.expect("]", "a closing bracket")
            return ListLiteral(tuple(items))
        if token.kind in ("string", "number"):
            self.index += 1
            return Literal(token.value)
        if token.kind == "name":
            if token.text in KEYWORD_LITERALS and self.tokens[self.index + 1].kind != ".":
                self.index += 1
                return Literal(KEYWORD_LITERALS[token.text])
            if token.text in FUNCTIONS and self.tokens[self.index + 1].kind == "(":
                self.index += 2
                arguments: list[Any] = []
                if self.current.kind != ")":
                    arguments.append(self.parse_or())
                    while self.current.kind == ",":
                        self.index += 1
                        arguments.append(self.parse_or())
                self.expect(")", "a closing parenthesis")
                return Function(token.text, tuple(arguments))
            if token.text in NAMESPACES:
                return self.parse_reference()
            raise ExpressionError(
                f"{token.text!r} is not a value reference, a literal, or a "
                f"function; a reference begins with one of "
                f"{', '.join(NAMESPACES)}",
                token.position,
            )
        raise ExpressionError(
            f"expected a value, found {token.text or 'the end'!r}", token.position
        )

    def parse_reference(self) -> Reference:
        namespace = self.take().text
        path: list[Any] = []
        while True:
            if self.current.kind == ".":
                self.index += 1
                name = self.expect("name", "a name after the dot")
                if not ID_PATTERN.fullmatch(name.text):
                    raise ExpressionError(
                        f"{name.text!r} is not a lowercase-hyphenated name",
                        name.position,
                    )
                path.append(name.text)
                continue
            if self.current.kind == "[":
                self.index += 1
                number = self.expect("number", "a list position")
                if not isinstance(number.value, int):
                    raise ExpressionError(
                        "a list position must be a whole number", number.position
                    )
                self.expect("]", "a closing bracket")
                path.append(number.value)
                continue
            break
        if not path:
            raise ExpressionError(
                f"{namespace} names no value; write {namespace}.<name>",
                self.tokens[self.index - 1].position,
            )
        return Reference(namespace, tuple(path))


@dataclass(frozen=True)
class Expression:
    """One parsed condition, kept beside the text the source wrote for it.

    The text is retained rather than re-rendered, so what a generated node shows
    an agent is the condition its author wrote. The tree is what every check
    reads.
    """

    text: str
    node: Any

    def render(self) -> str:
        return self.text


def parse_expression(text: object) -> Expression:
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("an expression must be a non-empty string")
    return Expression(text.strip(), _Parser(text).parse())


def parse_reference(text: str) -> Reference:
    parser = _Parser(text)
    if parser.current.kind != "name" or parser.current.text not in NAMESPACES:
        raise ExpressionError(
            "a value reference begins with one of " + ", ".join(NAMESPACES),
            parser.current.position,
        )
    reference = parser.parse_reference()
    if parser.current.kind != "end":
        raise ExpressionError(
            f"unexpected {parser.current.text!r} after the reference",
            parser.current.position,
        )
    return reference


def references(node: Any) -> list[Reference]:
    """Every reference an expression reads, in the order it reads them."""
    found: list[Reference] = []
    _walk(node, found)
    return found


def _walk(node: Any, found: list[Reference]) -> None:
    if isinstance(node, Reference):
        found.append(node)
    elif isinstance(node, (Conjunction, Disjunction)):
        for operand in node.operands:
            _walk(operand, found)
    elif isinstance(node, Negation):
        _walk(node.operand, found)
    elif isinstance(node, Grouping):
        _walk(node.inner, found)
    elif isinstance(node, Comparison):
        _walk(node.left, found)
        _walk(node.right, found)
    elif isinstance(node, (ListLiteral,)):
        for item in node.items:
            _walk(item, found)
    elif isinstance(node, Function):
        for argument in node.arguments:
            _walk(argument, found)




# --------------------------------------------------------------------------
# Types over an expression
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Problem:
    """One thing wrong with an expression or a binding, and the check it fails.

    A code travels with the message rather than being derived from it later,
    because the checker is the only part that knows whether a reference named
    nothing, was read too early, or was read without its guard. A caller
    classifying by wording would break on the first reword.
    """

    code: str
    message: str


UNKNOWN_VALUE = "expr.unknown-value"
UNDEFINED_VALUE = "expr.undefined-value"
UNGUARDED_OPTIONAL = "expr.unguarded-optional"
TYPE_MISMATCH = "expr.type-mismatch"
MISTYPED_BINDING = "value.mistyped-binding"
INVALID_BINDING = "value.invalid-binding"


@dataclass
class TypeEnvironment:
    """What values exist where an expression is evaluated, and what each is.

    `values` is keyed by namespace and root name because that is the granularity
    a workflow declares: `result.inspection` is declared once by the step that
    produces it, and `result.inspection.summary` is a walk into the record that
    declaration named. `records` supplies those walks. `defined` narrows the
    same set to what definite assignment proves is available at this point, so
    an expression can be well typed and still read a value that may not exist
    yet.
    """

    values: dict[tuple[str, str], ValueType]
    records: dict[str, dict[str, ValueType]]
    defined: set[tuple[str, str]] | None = None

    def lookup(self, reference: Reference) -> tuple[ValueType | None, Problem | None]:
        found, problem, _ = self.resolve(reference)
        return found, problem

    def resolve(
        self, reference: Reference
    ) -> tuple[ValueType | None, Problem | None, tuple[str, ...]]:
        """The reference's type, any problem, and every optional step on the way.

        A reference walks through values as well as ending on one, and any step
        of that walk can be absent: `result.inspection.summary` reads a string,
        and reads it out of a record that may not be there. Each optional step is
        returned by the reference that names it, so the caller can require a
        guard for every one rather than only for the value at the end.
        """
        key = (reference.namespace, reference.root)
        declared = self.values.get(key)
        if declared is None:
            return (
                None,
                Problem(
                    UNKNOWN_VALUE, f"{reference.render()} names no value in scope"
                ),
                (),
            )
        if self.defined is not None and key not in self.defined:
            return (
                None,
                Problem(
                    UNDEFINED_VALUE,
                    f"{reference.render()} is read where not every path reaching "
                    "this point has produced it",
                ),
                (),
            )
        optional: list[str] = []
        current = declared
        walked = Reference(reference.namespace, reference.path[:1])
        if current.optional:
            optional.append(walked.render())
        for part in reference.path[1:]:
            stepped, problem = self._step(reference, current, part)
            if stepped is None:
                return None, problem, tuple(optional)
            current = stepped
            walked = Reference(reference.namespace, (*walked.path, part))
            if current.optional:
                optional.append(walked.render())
        return current, None, tuple(optional)

    def _step(
        self, reference: Reference, current: ValueType, part: Any
    ) -> tuple[ValueType | None, Problem | None]:
        subject = current.base
        if isinstance(part, int):
            if subject.kind != "list" or subject.item is None:
                return None, Problem(
                    TYPE_MISMATCH,
                    f"{reference.render()} takes a position of a "
                    f"{subject.render()}, which is not a list",
                )
            return subject.item, None
        if subject.kind != "record":
            return None, Problem(
                TYPE_MISMATCH,
                f"{reference.render()} reads the field {part!r} of a "
                f"{subject.render()}, which has no fields",
            )
        fields = self.records.get(subject.record)
        if fields is None:
            return None, Problem(
                UNKNOWN_VALUE, f"record {subject.record} is not declared"
            )
        field_type = fields.get(str(part))
        if field_type is None:
            return None, Problem(
                UNKNOWN_VALUE,
                f"record {subject.record} declares no field {str(part)!r}",
            )
        return field_type, None


def guards(node: Any) -> set[str]:
    """The references an expression proves present when it is true."""
    if isinstance(node, Function) and node.name == "exists":
        if len(node.arguments) == 1 and isinstance(node.arguments[0], Reference):
            return {node.arguments[0].render()}
        return set()
    if isinstance(node, Conjunction):
        found: set[str] = set()
        for operand in node.operands:
            found |= guards(operand)
        return found
    if isinstance(node, Grouping):
        return guards(node.inner)
    if isinstance(node, Negation):
        return _false_guards(node.operand)
    return set()


def _false_guards(node: Any) -> set[str]:
    """The references an expression proves present when it is false."""
    if isinstance(node, Negation):
        return guards(node.operand)
    if isinstance(node, Grouping):
        return _false_guards(node.inner)
    if isinstance(node, Disjunction):
        found: set[str] = set()
        for operand in node.operands:
            found |= _false_guards(operand)
        return found
    return set()


class _Checker:
    def __init__(self, environment: TypeEnvironment) -> None:
        self.environment = environment
        self.problems: list[Problem] = []

    def report(self, code: str, message: str) -> None:
        problem = Problem(code, message)
        if problem not in self.problems:
            self.problems.append(problem)

    def found(self, problem: Problem | None) -> None:
        if problem is not None and problem not in self.problems:
            self.problems.append(problem)

    def check(self, node: Any, established: set[str]) -> ValueType | None:
        if isinstance(node, Literal):
            return _literal_type(node.value)
        if isinstance(node, Reference):
            return self.check_reference(node, established)
        if isinstance(node, Grouping):
            return self.check(node.inner, established)
        if isinstance(node, ListLiteral):
            return self.check_list(node, established)
        if isinstance(node, Function):
            return self.check_function(node, established)
        if isinstance(node, Negation):
            return self.expect_boolean(node.operand, established, "not")
        if isinstance(node, Conjunction):
            known = set(established)
            for operand in node.operands:
                self.expect_boolean(operand, known, "and")
                known |= guards(operand)
            return BOOLEAN
        if isinstance(node, Disjunction):
            known = set(established)
            for operand in node.operands:
                self.expect_boolean(operand, known, "or")
                known |= _false_guards(operand)
            return BOOLEAN
        if isinstance(node, Comparison):
            return self.check_comparison(node, established)
        return None

    def check_reference(
        self, node: Reference, established: set[str]
    ) -> ValueType | None:
        found, problem, optional = self.environment.resolve(node)
        if found is None:
            self.found(problem)
            return None
        for prefix in optional:
            if prefix not in established:
                self.report(
                    UNGUARDED_OPTIONAL,
                    f"{prefix} may be absent, so reading {node.render()} needs "
                    f"exists({prefix}) in the same expression",
                )
        return found

    def check_list(self, node: ListLiteral, established: set[str]) -> ValueType | None:
        if not node.items:
            self.report(TYPE_MISMATCH, "an empty list can never match anything")
            return None
        types = [self.check(item, established) for item in node.items]
        known = [item for item in types if item is not None]
        if not known:
            return None
        first = known[0].base
        if any(item.base != first for item in known):
            self.report(TYPE_MISMATCH, "a list literal mixes value types")
            return None
        return ValueType("list", item=first)

    def check_function(self, node: Function, established: set[str]) -> ValueType | None:
        if node.name == "exists":
            if len(node.arguments) != 1 or not isinstance(node.arguments[0], Reference):
                self.report(TYPE_MISMATCH, "exists takes exactly one value reference")
                return BOOLEAN
            found, problem = self.environment.lookup(node.arguments[0])
            if found is None:
                self.found(problem)
            return BOOLEAN
        if node.name == "length":
            if len(node.arguments) != 1:
                self.report(TYPE_MISMATCH, "length takes exactly one value")
                return INTEGER
            subject = self.check(node.arguments[0], established)
            if subject is not None and subject.base.kind not in ("string", "list"):
                self.report(
                    TYPE_MISMATCH,
                    f"length reads a {subject.render()}, which has no length",
                )
            return INTEGER
        if len(node.arguments) != 2:
            self.report(TYPE_MISMATCH, "contains takes a value and the item to find")
            return BOOLEAN
        subject = self.check(node.arguments[0], established)
        item = self.check(node.arguments[1], established)
        if subject is None or item is None:
            return BOOLEAN
        container = subject.base
        if container.kind == "string":
            if item.base.kind != "string":
                self.report(TYPE_MISMATCH, "contains looks for text inside text")
        elif container.kind == "list":
            if container.item is not None and container.item != item.base:
                self.report(
                    TYPE_MISMATCH,
                    f"contains looks for a {item.render()} in a "
                    f"{container.render()}",
                )
        else:
            self.report(
                TYPE_MISMATCH,
                f"contains reads a {subject.render()}, which holds nothing",
            )
        return BOOLEAN

    def expect_boolean(
        self, node: Any, established: set[str], operator: str
    ) -> ValueType | None:
        found = self.check(node, established)
        if found is not None and found.base.kind != "boolean":
            self.report(
                TYPE_MISMATCH, f"{operator} joins truths, not a {found.render()}"
            )
        return BOOLEAN

    def check_comparison(
        self, node: Comparison, established: set[str]
    ) -> ValueType | None:
        left = self.check(node.left, established)
        right = self.check(node.right, established)
        if left is None or right is None:
            return BOOLEAN
        if node.operator in MEMBERSHIP:
            container = right.base
            if container.kind == "list" and container.item is not None:
                if not _comparable(left.base, container.item):
                    self.report(
                        TYPE_MISMATCH,
                        f"{node.operator} looks for a {left.render()} in a "
                        f"{right.render()}",
                    )
            elif container.kind == "string":
                if left.base.kind != "string":
                    self.report(
                        TYPE_MISMATCH, f"{node.operator} looks for text inside text"
                    )
            else:
                self.report(
                    TYPE_MISMATCH,
                    f"{node.operator} needs a list or text on the right, not a "
                    f"{right.render()}",
                )
            return BOOLEAN
        if node.operator in ("<", "<=", ">", ">="):
            for side in (left, right):
                if side.base.kind not in ("integer", "number"):
                    self.report(
                        TYPE_MISMATCH,
                        f"{node.operator} orders numbers, not a {side.render()}",
                    )
            return BOOLEAN
        if not _comparable(left.base, right.base):
            self.report(
                TYPE_MISMATCH,
                f"{node.operator} compares a {left.render()} with a "
                f"{right.render()}",
            )
        return BOOLEAN


def _comparable(left: ValueType, right: ValueType) -> bool:
    if left == right:
        return True
    numbers = {"integer", "number"}
    if left.kind in numbers and right.kind in numbers:
        return True
    if left.kind == "enum" and right.kind == "string":
        return True
    if right.kind == "enum" and left.kind == "string":
        return True
    if left.kind == "enum" and right.kind == "enum":
        return True
    return False


def _literal_type(value: Any) -> ValueType | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return BOOLEAN
    if isinstance(value, int):
        return INTEGER
    if isinstance(value, float):
        return NUMBER
    return STRING


def check_expression(expression: Expression, environment: TypeEnvironment) -> list[Problem]:
    """Type-check one expression where it is evaluated, collecting every problem."""
    checker = _Checker(environment)
    found = checker.check(expression.node, set())
    if found is not None and found.base.kind != "boolean":
        checker.report(
            TYPE_MISMATCH,
            f"a condition must be a truth, and this one is a {found.render()}",
        )
    return checker.problems


def check_binding(
    binding: Binding, expected: ValueType, environment: TypeEnvironment
) -> list[Problem]:
    """Check that one supplied value can stand where its destination expects it."""
    if binding.kind == "literal":
        found = _literal_type(binding.literal)
        if binding.literal is None:
            if expected.kind != "optional":
                return [
                    Problem(
                        MISTYPED_BINDING, f"null cannot supply a {expected.render()}"
                    )
                ]
            return []
        if found is None or not _comparable(found, expected.base):
            rendered = "null" if found is None else found.render()
            return [
                Problem(
                    MISTYPED_BINDING,
                    f"a {rendered} cannot supply a {expected.render()}",
                )
            ]
        if expected.base.kind == "enum" and binding.literal not in expected.base.values:
            return [
                Problem(
                    MISTYPED_BINDING,
                    f"{binding.literal!r} is not one of "
                    f"{', '.join(expected.base.values)}",
                )
            ]
        return []
    if binding.reference is None:
        return [Problem(INVALID_BINDING, "a binding reads no value")]
    found, problem, optional = environment.resolve(binding.reference)
    if found is None:
        return [problem] if problem is not None else []
    reference = binding.reference.render()
    if (optional or found.optional) and expected.kind != "optional":
        return [
            Problem(
                MISTYPED_BINDING,
                f"{reference} may be absent, and a {expected.render()} must be "
                "present",
            )
        ]
    if not _comparable(found.base, expected.base):
        return [
            Problem(
                MISTYPED_BINDING,
                f"{reference} is a {found.render()}, and a {expected.render()} "
                "is expected",
            )
        ]
    return []
