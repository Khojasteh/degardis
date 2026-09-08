"""One file, one construct: the schema each selected source must satisfy.

The manifest key that selected a file decides which schema it is read against.
Nothing here infers a construct kind from a directory name, and no top-level
construct carries an `id` field: the lowercase-hyphenated file stem is the
identity, so moving a file keeps its id and renaming the file changes it.

The constructs are separate schemas rather than one generic list because they
have different execution meanings. A policy provision is binding wherever it
matches; a heuristic advises a choice and can never satisfy a binding check.
Reading both out of the same shape would leave the compiler unable to tell them
apart, which is exactly the distinction the generated bundle has to make.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dexpr import (
    Binding,
    Expression,
    ExpressionError,
    ValueType,
    check_default,
    parse_binding,
    parse_expression,
    parse_reference,
    parse_value_declaration,
)
from .model import Diagnostics, filename_title


ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A dotted opaque tag, or a prefix selector ending in `.*`. Neither is
# interpreted: a subject and an effect are labels a selector compares, and the
# compiler never reads meaning into their words.
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
TAG_PREFIX_PATTERN = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*\.\*$")

# The node kinds a selector may name. These are the kinds the lowered graph
# holds, not the step keywords a source writes, because a selector matches nodes.
SELECTOR_FORMS: tuple[str, ...] = (
    "action",
    "branch",
    "decision",
    "gate",
    "call",
    "pattern",
    "return",
)
SELECTOR_FIELDS = frozenset(
    {"forms", "subjects", "effects", "calls", "outcomes", "all"}
)

# Where a binding provision, rule, or hook is enforced relative to the node it
# constrains. `before-return` is separate from `before` because a return has no
# action to precede: what it precedes is leaving the workflow.
BINDING_PHASES: tuple[str, ...] = ("before", "during", "after", "before-return")
HOOK_PHASES: tuple[str, ...] = ("enter", "before", "after", "exit")

# The step forms. A step has exactly one, which is what makes its meaning
# readable without a `kind` field to consult.
STEP_FORMS: tuple[str, ...] = (
    "action",
    "branch",
    "decide",
    "gate",
    "use",
    "pattern",
    "return",
)
STEP_FORM_NODE_KINDS = {
    "action": "action",
    "branch": "branch",
    "decide": "decision",
    "gate": "gate",
    "use": "call",
    "pattern": "pattern",
    "return": "return",
}

# `heuristics` is common to the schema and not to the forms: only a decide or a
# gate may carry one, and a step that names heuristics anywhere else is reported
# as a misplaced heuristic rather than as an unrecognized field, because the
# author's mistake is about what a heuristic is for.
COMMON_STEP_FIELDS = frozenset(
    {
        "policies",
        "rules",
        "protocols",
        "guidance",
        "subjects",
        "effects",
        "heuristics",
    }
)

WORKFLOW_FIELDS = frozenset(
    {
        "title",
        "description",
        "policies",
        "rules",
        "protocols",
        "guidance",
        "inputs",
        "outcomes",
        "entry",
        "steps",
    }
)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    """Which nodes a policy provision, rule, or protocol hook applies to.

    Selection is over declared metadata only. Nothing here reads a title, a
    description, a command, an example, or a filename, so what a provision
    constrains cannot drift as prose is reworded, and an author can see from the
    source which nodes they have selected.
    """

    forms: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    every: bool = False

    def render(self) -> str:
        if self.every:
            return "every node in scope"
        parts = []
        for label, values in (
            ("form", self.forms),
            ("subject", self.subjects),
            ("effect", self.effects),
            ("call", self.calls),
            ("outcome", self.outcomes),
        ):
            if values:
                parts.append(f"{label} {' or '.join(values)}")
        return ", ".join(parts)

    def matches(self, facts: NodeFacts) -> bool:
        if self.every:
            return True
        if self.forms and facts.form not in self.forms:
            return False
        if self.subjects and not _tags_match(self.subjects, facts.subjects):
            return False
        if self.effects and not _tags_match(self.effects, facts.effects):
            return False
        if self.calls and facts.call not in self.calls:
            return False
        if self.outcomes and facts.outcome not in self.outcomes:
            return False
        return True


@dataclass(frozen=True)
class NodeFacts:
    """What a selector compares one node against."""

    form: str
    subjects: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    call: str = ""
    outcome: str = ""


def _tags_match(patterns: tuple[str, ...], tags: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if any(tag == prefix or tag.startswith(f"{prefix}.") for tag in tags):
                return True
        elif pattern in tags:
            return True
    return False


@dataclass(frozen=True)
class Verification:
    """How a binding check is settled: by an expression, a gate, or a person.

    A gate names a closed judgment the workflow already makes, so the check is
    discharged by the state that judgment reached. A confirmation names what the
    agent must establish, which the compiler renders and cannot evaluate.
    """

    kind: str
    expression: Expression | None = None
    gate: str = ""
    confirm: str = ""


@dataclass(frozen=True)
class GuidanceUse:
    """One non-binding guidance application, and how much of it renders inline."""

    id: str
    inline: bool = False


@dataclass(frozen=True)
class Provision:
    id: str
    phase: str
    selector: Selector
    command: str
    prohibits: bool
    when: Expression | None = None
    unless: Expression | None = None
    verify: Verification | None = None
    line: int | None = None


@dataclass(frozen=True)
class Policy:
    id: str
    path: Path
    title: str
    summary: str
    rationale: str
    provisions: tuple[Provision, ...]


@dataclass(frozen=True)
class Rule:
    id: str
    path: Path
    title: str
    summary: str
    rationale: str
    provision: Provision


@dataclass(frozen=True)
class StateField:
    """One typed value a protocol frame holds, and what it holds when it opens.

    The field is `default` rather than the `initial` an earlier format gave it,
    because a protocol already declares an `initial` and that one names the
    lifecycle state the frame opens in. One word for two things left a reader of
    a protocol file to tell them apart by depth, and left the format with two
    words for the one idea of the value something holds before anything wrote
    it. `Reader.declared_default` reads it, and states what a written default
    may be.
    """

    name: str
    type: ValueType
    default: Any = None

    @property
    def defaulted(self) -> bool:
        """Whether the frame opens holding this value, rather than without it."""
        return self.default is not None


@dataclass(frozen=True)
class Hook:
    id: str
    phase: str
    selector: Selector | None
    from_states: tuple[str, ...]
    command: str = ""
    when: Expression | None = None
    verify: Verification | None = None
    updates: tuple[tuple[str, Binding], ...] = ()
    clears: tuple[str, ...] = ()
    to: str = ""
    line: int | None = None


@dataclass(frozen=True)
class Protocol:
    id: str
    path: Path
    title: str
    purpose: str
    rationale: str
    states: tuple[str, ...]
    initial: str
    accepting: tuple[str, ...]
    data: tuple[StateField, ...]
    hooks: tuple[Hook, ...]

    def field(self, name: str) -> StateField | None:
        return next((item for item in self.data if item.name == name), None)


@dataclass(frozen=True)
class ProcedureItem:
    id: str
    command: str
    uses: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pattern:
    id: str
    path: Path
    title: str
    summary: str
    inputs: tuple[tuple[str, ValueType], ...]
    procedure: tuple[ProcedureItem, ...]
    references: tuple[str, ...] = ()

    @property
    def has_auxiliary_material(self) -> bool:
        return bool(self.references)


@dataclass(frozen=True)
class Advice:
    id: str
    prefer: str
    when: Expression | None = None
    because: str = ""
    caution: str = ""


@dataclass(frozen=True)
class Heuristic:
    id: str
    path: Path
    title: str
    question: str
    advice: tuple[Advice, ...]
    references: tuple[str, ...] = ()

    @property
    def has_auxiliary_material(self) -> bool:
        return bool(self.references)


@dataclass(frozen=True)
class Guidance:
    id: str
    path: Path
    title: str
    summary: str
    rationale: str
    points: tuple[str, ...] = ()
    references: tuple[str, ...] = ()

    @property
    def has_auxiliary_material(self) -> bool:
        return bool(self.points or self.references)


@dataclass(frozen=True)
class Profile:
    """Auxiliary guidance a reader chooses for itself from the generated index.

    Profiles are deliberately outside the execution graph.  The optional
    description is what lets a reader tell one candidate from another before
    opening it; missing or ignored profiles never change validity,
    requirements, or failure.
    """

    id: str
    path: Path
    title: str
    category: str = ""
    description: str = ""
    points: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecordField:
    name: str
    type: ValueType
    description: str = ""


@dataclass(frozen=True)
class Record:
    id: str
    path: Path
    title: str
    fields: tuple[RecordField, ...]

    def types(self) -> dict[str, ValueType]:
        return {item.name: item.type for item in self.fields}


@dataclass(frozen=True)
class BranchCase:
    when: Expression | None
    next: str


@dataclass(frozen=True)
class Option:
    """One closed alternative a decision or gate may reach."""

    id: str
    command: str
    next: str


@dataclass(frozen=True)
class Outcome:
    id: str
    record: str = ""


@dataclass(frozen=True)
class ResourceUse:
    operation: str
    path: str


@dataclass(frozen=True)
class ProducedValue:
    """One value an action produces, and what it holds where the action did not run.

    `default` sits on the declaration rather than on the workflow because the
    sentence describing the value and the value it falls back to are one
    statement: separated, the two drift, and the empty case ends up described in
    a hand-written step instead. Its lifetime is still the workflow's, which is
    where the compiler states it. It is the same field a protocol state field
    declares, and `Reader.declared_default` reads both.
    """

    name: str
    type: ValueType
    default: Any = None

    @property
    def defaulted(self) -> bool:
        """Whether the workflow holds this value from its first node onward."""
        return self.default is not None


@dataclass(frozen=True)
class CallOutcome:
    id: str
    next: str
    capture: str = ""


@dataclass(frozen=True)
class Step:
    id: str
    form: str
    command: str = ""
    uses: tuple[str, ...] = ()
    produces: tuple[ProducedValue, ...] = ()
    next: str = ""
    cases: tuple[BranchCase, ...] = ()
    options: tuple[Option, ...] = ()
    heuristics: tuple[str, ...] = ()
    call: str = ""
    supplied: tuple[tuple[str, Binding], ...] = ()
    on: tuple[CallOutcome, ...] = ()
    resource: ResourceUse | None = None
    pattern: str = ""
    outcome: str = ""
    policies: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ()
    guidance: tuple[GuidanceUse, ...] = ()
    subjects: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    line: int | None = None

    @property
    def node_kind(self) -> str:
        return STEP_FORM_NODE_KINDS[self.form]

    @property
    def successors(self) -> tuple[str, ...]:
        if self.form == "branch":
            return tuple(case.next for case in self.cases)
        if self.form in ("decide", "gate"):
            return tuple(option.next for option in self.options)
        if self.form == "use":
            return tuple(item.next for item in self.on)
        if self.form == "return":
            return ()
        return (self.next,) if self.next else ()


@dataclass(frozen=True)
class Workflow:
    id: str
    path: Path
    title: str
    description: str
    entry: str
    steps: tuple[Step, ...]
    inputs: tuple[tuple[str, ValueType], ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    policies: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ()
    guidance: tuple[GuidanceUse, ...] = ()

    def step(self, identifier: str) -> Step | None:
        return next((item for item in self.steps if item.id == identifier), None)

    def outcome(self, identifier: str) -> Outcome | None:
        return next((item for item in self.outcomes if item.id == identifier), None)


@dataclass
class SourceSet:
    """Every selected construct, keyed by id except source-relative profiles.

    Workflows never name profiles, so a profile's filename cannot be a runtime
    identifier. Keeping its source-relative key lets two profile files share a
    stem while retaining both auxiliary pages.
    """

    policies: dict[str, Policy] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    patterns: dict[str, Pattern] = field(default_factory=dict)
    heuristics: dict[str, Heuristic] = field(default_factory=dict)
    guidance: dict[str, Guidance] = field(default_factory=dict)
    protocols: dict[str, Protocol] = field(default_factory=dict)
    records: dict[str, Record] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)

    def kind(self, key: str) -> dict[str, Any]:
        return getattr(self, key)

    def record_types(self) -> dict[str, dict[str, ValueType]]:
        return {name: record.types() for name, record in self.records.items()}


# --------------------------------------------------------------------------
# Reading one file
# --------------------------------------------------------------------------


class Reader:
    """One source file being read against one schema, collecting every problem.

    A reader exists per file so that a message can name the file and the local
    key it was found under without every check restating both, and so that a
    file with several problems reports all of them rather than the first.
    """

    def __init__(
        self,
        path: Path,
        data: dict[str, Any],
        diagnostics: Diagnostics,
        code: str,
        *,
        unknown: str = "",
    ) -> None:
        self.path = path
        self.data = data
        self.diagnostics = diagnostics
        self.code = code
        self.unknown = unknown
        self.usable = True

    @contextmanager
    def under(self, code: str):
        """Report every finding inside this block against a narrower check.

        A provision, a procedure item, a hook, and a step each have their own
        check code, and each is read through the same shared helpers. Scoping
        the code here keeps those helpers general while a finding still names
        the check an author would look up: a provision missing its selector is
        `policy.invalid-provision`, not the file-level shape check.
        """
        previous = self.code
        self.code = code
        try:
            yield
        finally:
            self.code = previous

    def fail(self, message: str, code: str = "", *, fatal: bool = True) -> None:
        self.diagnostics.error(f"{self.path}: {message}", code or self.code, self.path)
        if fatal:
            self.usable = False

    def warn(self, message: str, code: str = "") -> None:
        self.diagnostics.warning(
            f"{self.path}: {message}", code or self.code, self.path
        )

    def unknown_fields(self, allowed: frozenset[str], label: str) -> None:
        unknown = sorted(set(self.data) - allowed)
        if unknown:
            self.fail(
                f"unrecognized {label} fields: {', '.join(unknown)}",
                self.unknown,
                fatal=False,
            )

    def text(
        self,
        key: str,
        *,
        required: bool = False,
        missing: str = "",
        invalid: str = "",
    ) -> str:
        """One top-level text field, reporting its absence as its own check.

        A required field that is simply not there is the commonest mistake an
        author makes, and the one they can act on without reading anything, so
        `missing` names a check that names the key: an author who knows the key
        can build the code rather than look it up. A field nested in a
        provision, a hook, a step, or a procedure item passes nothing and keeps
        its enclosing item's check, because there the item is what an author
        repairs.
        """
        return self._text(self.data, key, required, "", missing, invalid)

    def field_text(
        self,
        data: dict[str, Any],
        key: str,
        required: bool = False,
        location: str = "",
        invalid: str = "",
    ) -> str:
        return self._text(data, key, required, location, invalid=invalid)

    def _text(
        self,
        data: dict[str, Any],
        key: str,
        required: bool,
        location: str,
        missing: str = "",
        invalid: str = "",
    ) -> str:
        if key not in data:
            if required:
                self.fail(f"{location}{key} is required", missing)
            return ""
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            self.fail(f"{location}{key} must be a non-empty string", invalid)
            return ""
        return value.strip()

    def text_list(
        self,
        data: dict[str, Any],
        key: str,
        location: str = "",
        invalid: str = "",
    ) -> tuple[str, ...]:
        if key not in data:
            return ()
        value = data[key]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            self.fail(
                f"{location}{key} must be a non-empty list of non-empty strings",
                invalid,
            )
            return ()
        return tuple(item.strip() for item in value)

    def id_list(
        self,
        data: dict[str, Any],
        key: str,
        location: str = "",
        invalid: str = "",
    ) -> tuple[str, ...]:
        values = self.text_list(data, key, location, invalid)
        for value in values:
            if not ID_PATTERN.fullmatch(value):
                self.fail(
                    f"{location}{key} names {value!r}, which is not a "
                    "lowercase-hyphenated file stem",
                    invalid,
                )
                return ()
        repeated = sorted({item for item in values if values.count(item) > 1})
        if repeated:
            self.fail(
                f"{location}{key} names {', '.join(repeated)} more than once",
                invalid,
            )
            return ()
        return values

    def required_id_list(
        self,
        data: dict[str, Any],
        key: str,
        message: str,
        *,
        missing: str,
        invalid: str,
    ) -> tuple[str, ...]:
        """One required top-level list of ids, reporting absence separately.

        A list the schema requires can be absent or present-and-malformed, and
        the two are different repairs: `missing` names the check the absence
        reports, while a malformed value keeps the file's shape check.
        """
        if key not in data:
            self.fail(message, missing)
            return ()
        return self.id_list(data, key, invalid=invalid)

    def tag_list(
        self, data: dict[str, Any], key: str, location: str = "", *, prefixes: bool = False
    ) -> tuple[str, ...]:
        values = self.text_list(data, key, location)
        for value in values:
            if TAG_PATTERN.fullmatch(value):
                continue
            if prefixes and TAG_PREFIX_PATTERN.fullmatch(value):
                continue
            allowed = (
                "a dotted lowercase tag, or a prefix ending in .*"
                if prefixes
                else "a dotted lowercase tag"
            )
            self.fail(f"{location}{key} names {value!r}, which is not {allowed}")
            return ()
        return values

    def mapping(
        self,
        key: str,
        *,
        required: bool = False,
        location: str = "",
        missing: str = "",
        invalid: str = "",
    ) -> dict[str, Any]:
        if key not in self.data:
            if required:
                self.fail(f"{location}{key} is required", missing)
            return {}
        return self.submapping(self.data, key, location, invalid)

    def submapping(
        self,
        data: dict[str, Any],
        key: str,
        location: str = "",
        invalid: str = "",
    ) -> dict[str, Any]:
        if key not in data:
            return {}
        value = data[key]
        if not isinstance(value, dict) or not value:
            self.fail(f"{location}{key} must be a non-empty mapping", invalid)
            return {}
        for name in value:
            if not ID_PATTERN.fullmatch(name):
                self.fail(
                    f"{location}{key} names {name!r}, which is not a "
                    "lowercase-hyphenated identifier",
                    invalid,
                )
                return {}
        return value

    def item_mapping(
        self, data: dict[str, Any], name: str, location: str
    ) -> dict[str, Any]:
        value = data.get(name)
        if not isinstance(value, dict) or not value:
            self.fail(f"{location} must be a non-empty mapping of fields")
            return {}
        return value

    def condition(
        self,
        data: dict[str, Any],
        key: str,
        location: str = "",
        invalid: str = "",
    ) -> Expression | None:
        value = data.get(key)
        if value is None:
            return None
        try:
            return parse_expression(value)
        except ExpressionError as exc:
            self.fail(f"{location}{key}: {exc}", invalid or exc.code)
            return None

    def declared_type(
        self, data: dict[str, Any], name: str, location: str
    ) -> ValueType | None:
        """One declared value's type, and the description written beside it.

        All five declaration sites reach their type through here, so the
        description is read here too: read at each site instead, it was read at
        the one that stores it and nowhere else.
        """
        declaration = data.get(name)
        if isinstance(declaration, dict):
            self.field_text(
                declaration,
                "description",
                location=f"{location}{name}.",
                invalid="value.invalid-description",
            )
        found, problem = parse_value_declaration(declaration)
        if found is None:
            self.fail(f"{location}{name}: {problem}", "value.invalid-type")
        return found

    def declared_default(
        self, data: dict[str, Any], declared: ValueType, location: str
    ) -> tuple[Any, bool]:
        """One declared value's default, and whether the declaration stands.

        Two sites declare a value that may hold something before anything wrote
        it — a produced value on a path that produced none, and a protocol state
        field when its frame opens — and both refuse one the same way, so both
        read it here rather than each spelling the refusal again.

        The key being absent and a written null are different answers. Null is a
        value no non-optional type accepts, and an optional type has no use for
        one because it is already absent, so it is reported rather than read as
        the absence of a default.
        """
        if "default" not in data:
            return None, True
        default = data["default"]
        problem = (
            "default states the value this holds before anything wrote it, so "
            "it names one"
            if default is None
            else check_default(default, declared)
        )
        if problem:
            self.fail(f"{location}.default: {problem}", "value.invalid-default")
            return None, False
        return default, True

    def bindings(
        self, data: dict[str, Any], key: str, location: str
    ) -> tuple[tuple[str, Binding], ...]:
        value = data.get(key)
        if value is None:
            return ()
        if not isinstance(value, dict) or not value:
            self.fail(f"{location}{key} must be a non-empty mapping of bindings")
            return ()
        supplied: list[tuple[str, Binding]] = []
        for name, item in value.items():
            if not ID_PATTERN.fullmatch(name):
                self.fail(
                    f"{location}{key} supplies {name!r}, which is not a "
                    "lowercase-hyphenated name"
                )
                continue
            binding, problem = parse_binding(item)
            if binding is None:
                self.fail(f"{location}{key}.{name}: {problem}", "value.invalid-binding")
                continue
            supplied.append((name, binding))
        return tuple(supplied)

    def selector(
        self,
        data: dict[str, Any],
        location: str,
        *,
        required: bool = True,
        missing: str = "",
        invalid: str = "",
    ) -> Selector | None:
        value = data.get("match")
        if value is None:
            if required:
                self.fail(f"{location}match is required", missing)
            return None
        if not isinstance(value, dict) or not value:
            self.fail(
                f"{location}match must be a mapping selecting nodes, or "
                "{all: true} to select every node in scope",
                invalid,
            )
            return None
        unknown = sorted(set(value) - SELECTOR_FIELDS)
        if unknown:
            self.fail(
                f"{location}match: unrecognized selector fields: "
                f"{', '.join(unknown)}",
                invalid,
            )
            return None
        if "all" in value:
            if value["all"] is not True or len(value) > 1:
                self.fail(
                    f"{location}match: all is written as {{all: true}} and "
                    "stands alone",
                    invalid,
                )
                return None
            return Selector(every=True)
        forms = self.text_list(value, "forms", f"{location}match.")
        for form in forms:
            if form not in SELECTOR_FORMS:
                self.fail(
                    f"{location}match.forms names {form!r}; the node forms are "
                    f"{', '.join(SELECTOR_FORMS)}"
                )
                return None
        selector = Selector(
            forms=forms,
            subjects=self.tag_list(value, "subjects", f"{location}match.", prefixes=True),
            effects=self.tag_list(value, "effects", f"{location}match.", prefixes=True),
            calls=self.id_list(value, "calls", f"{location}match."),
            outcomes=self.id_list(value, "outcomes", f"{location}match."),
        )
        if not any(
            (
                selector.forms,
                selector.subjects,
                selector.effects,
                selector.calls,
                selector.outcomes,
            )
        ):
            self.fail(
                f"{location}match selects nothing; name at least one of "
                f"{', '.join(sorted(SELECTOR_FIELDS - {'all'}))}, or write "
                "{all: true}"
            )
            return None
        return selector

    def verification(
        self, data: dict[str, Any], location: str, invalid: str = ""
    ) -> Verification | None:
        value = data.get("verify")
        if value is None:
            return None
        if not isinstance(value, dict) or len(value) != 1:
            self.fail(
                f"{location}verify names exactly one of expression, gate, or "
                "confirm",
                invalid,
            )
            return None
        key, inner = next(iter(value.items()))
        if key == "expression":
            expression = self.condition(
                value, "expression", f"{location}verify.", invalid
            )
            if expression is None:
                return None
            return Verification("expression", expression=expression)
        if key == "gate":
            if not isinstance(inner, str) or not ID_PATTERN.fullmatch(inner):
                self.fail(
                    f"{location}verify.gate names one gate step in scope", invalid
                )
                return None
            return Verification("gate", gate=inner)
        if key == "confirm":
            text = self._text(
                value, "confirm", True, f"{location}verify.", invalid=invalid
            )
            if not text:
                return None
            return Verification("confirm", confirm=text)
        if key in ("heuristic", "prefer"):
            self.fail(
                f"{location}verify names advice; a heuristic can improve a "
                "choice and can never satisfy a binding check, so verify takes "
                "an expression, a gate, or an agent confirmation",
                "heuristic.used-as-authority",
            )
            return None
        self.fail(
            f"{location}verify: {key!r} is not a verification; write expression, "
            "gate, or confirm",
            invalid,
        )
        return None

    def guidance_uses(
        self, data: dict[str, Any], location: str = "", invalid: str = ""
    ) -> tuple[GuidanceUse, ...]:
        if "guidance" not in data:
            return ()
        value = data["guidance"]
        if not isinstance(value, list) or not value:
            self.fail(f"{location}guidance must be a non-empty list", invalid)
            return ()
        uses: list[GuidanceUse] = []
        for item in value:
            if isinstance(item, str):
                if not ID_PATTERN.fullmatch(item):
                    self.fail(
                        f"{location}guidance names {item!r}, which is not a "
                        "lowercase-hyphenated file stem",
                        invalid,
                    )
                    return ()
                uses.append(GuidanceUse(item))
                continue
            if not isinstance(item, dict) or sorted(item) not in (
                ["guidance"],
                ["detail", "guidance"],
            ):
                self.fail(
                    f"{location}guidance takes a file stem, or a mapping with "
                    "guidance and an optional detail mode",
                    invalid,
                )
                return ()
            name = item["guidance"]
            if not isinstance(name, str) or not ID_PATTERN.fullmatch(name):
                self.fail(
                    f"{location}guidance names {name!r}, which is not a "
                    "lowercase-hyphenated file stem",
                    invalid,
                )
                return ()
            detail = item.get("detail", "synopsis")
            if detail not in ("synopsis", "inline"):
                self.fail(
                    f"{location}guidance.detail is synopsis or inline, not "
                    f"{detail!r}",
                    invalid,
                )
                return ()
            uses.append(GuidanceUse(name, inline=detail == "inline"))
        names = [use.id for use in uses]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            self.fail(
                f"{location}guidance names {', '.join(repeated)} more than once",
                invalid,
            )
            return ()
        return tuple(uses)


def _stem_id(path: Path, diagnostics: Diagnostics) -> str:
    """The construct's id, or the check that the filename cannot be one.

    Every construct kind reports the same code here, because the mistake is the
    same one wherever it happens: the file stem is the identity, so a stem that
    is not a lowercase-hyphenated name leaves the construct unnameable.
    """
    if ID_PATTERN.fullmatch(path.stem):
        return path.stem
    diagnostics.error(
        f"{path}: filename must be lowercase letters, digits, and single "
        "hyphens, because the file stem is the construct's id",
        "source.invalid-name",
        path,
    )
    return ""


# --------------------------------------------------------------------------
# Construct schemas
# --------------------------------------------------------------------------


POLICY_FIELDS = frozenset({"title", "summary", "rationale", "provisions"})
PROVISION_FIELDS = frozenset(
    {"phase", "match", "when", "unless", "require", "prohibit", "verify"}
)


def read_policy(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Policy | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "policy.invalid-summary",
        unknown="policy.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(POLICY_FIELDS, "policy")
    summary = reader.text(
        "summary", required=True, missing="policy.missing-summary", invalid="policy.invalid-summary"
    )
    declared = reader.mapping(
        "provisions", required=True, missing="policy.missing-provisions", invalid="policy.invalid-provisions"
    )
    provisions: list[Provision] = []
    for name in declared:
        provision = _read_provision(
            reader, declared, name, f"provisions.{name}", "policy.invalid-provision"
        )
        if provision is not None:
            provisions.append(provision)
    if not identifier or not reader.usable or not provisions:
        return None
    return Policy(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="policy.invalid-title") or filename_title(identifier),
        summary=summary,
        rationale=reader.text("rationale", invalid="policy.invalid-rationale"),
        provisions=tuple(provisions),
    )


def _read_provision(
    reader: Reader,
    container: dict[str, Any],
    name: str,
    location: str,
    code: str,
) -> Provision | None:
    body = reader.item_mapping(container, name, location)
    if not body:
        return None
    unknown = sorted(set(body) - PROVISION_FIELDS)
    if unknown:
        reader.fail(
            f"{location}: unrecognized fields: {', '.join(unknown)}; a "
            f"provision declares {', '.join(sorted(PROVISION_FIELDS))}",
            code,
        )
        return None
    with reader.under(code):
        return _read_provision_body(reader, body, name, location, code)


def _read_provision_body(
    reader: Reader,
    body: dict[str, Any],
    name: str,
    location: str,
    code: str,
    *,
    missing_phase: str = "",
    missing_match: str = "",
    missing_command: str = "",
    invalid_phase: str = "",
    invalid_match: str = "",
    invalid_command: str = "",
    invalid_when: str = "",
    invalid_unless: str = "",
    invalid_verify: str = "",
) -> Provision | None:
    """The binding half a policy provision and a rule declare identically.

    A rule is one provision written at file scope: it has the same phase,
    selector, activation, command, and verification, so both are read here and
    lowered by the same pass. What differs is only where the fields sit, which
    is why the enclosing reader owns the unknown-field check.

    The three `missing_` codes are supplied only by the rule, whose phase,
    selector, and command are top-level fields and so report their absence by
    key. In a policy the same fields sit inside a provision, and the provision
    is the unit an author repairs, so their absence keeps
    `policy.invalid-provision`.
    """
    prefix = f"{location}." if location else ""
    if "phase" not in body:
        reader.fail(
            f"{prefix}phase is required: it is one of "
            f"{', '.join(BINDING_PHASES)}",
            missing_phase or code,
        )
        return None
    phase = body.get("phase")
    if phase not in BINDING_PHASES:
        reader.fail(
            f"{prefix}phase is one of {', '.join(BINDING_PHASES)}, not {phase!r}",
            invalid_phase or code,
        )
        return None
    selector = reader.selector(
        body, prefix, missing=missing_match or code, invalid=invalid_match or code
    )
    if selector is None:
        return None
    has_require = "require" in body
    has_prohibit = "prohibit" in body
    if not has_require and not has_prohibit:
        subject = f"{location}: declares" if location else "declares"
        reader.fail(
            f"{subject} neither require nor prohibit; one binding command is "
            "what makes a provision act",
            missing_command or code,
        )
        return None
    if has_require and has_prohibit:
        subject = f"{location}: declares" if location else "declares"
        reader.fail(
            f"{subject} both require and prohibit, and a provision carries "
            "exactly one binding command",
            invalid_command or code,
        )
        return None
    key = "require" if has_require else "prohibit"
    command = reader.field_text(
        body, key, True, prefix, invalid_command or code
    )
    if not command:
        return None
    return Provision(
        id=name,
        phase=phase,
        selector=selector,
        command=command,
        prohibits=has_prohibit,
        when=reader.condition(body, "when", prefix, invalid_when),
        unless=reader.condition(body, "unless", prefix, invalid_unless),
        verify=reader.verification(body, prefix, invalid_verify),
    )


RULE_FIELDS = frozenset(
    {
        "title",
        "summary",
        "rationale",
        "phase",
        "match",
        "when",
        "unless",
        "require",
        "prohibit",
        "verify",
    }
)


def read_rule(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Rule | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "rule.invalid-summary",
        unknown="rule.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(RULE_FIELDS, "rule")
    summary = reader.text(
        "summary", required=True, missing="rule.missing-summary", invalid="rule.invalid-summary"
    )
    with reader.under("rule.invalid-command"):
        provision = _read_provision_body(
            reader,
            data,
            identifier or path.stem,
            "",
            "rule.invalid-command",
            missing_phase="rule.missing-phase",
            missing_match="rule.missing-match",
            missing_command="rule.missing-command",
            invalid_phase="rule.invalid-phase",
            invalid_match="rule.invalid-match",
            invalid_command="rule.invalid-command",
            invalid_when="rule.invalid-when",
            invalid_unless="rule.invalid-unless",
            invalid_verify="rule.invalid-verify",
        )
    if not identifier or not reader.usable or provision is None:
        return None
    return Rule(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="rule.invalid-title") or filename_title(identifier),
        summary=summary,
        rationale=reader.text("rationale", invalid="rule.invalid-rationale"),
        provision=Provision(
            id=identifier,
            phase=provision.phase,
            selector=provision.selector,
            command=provision.command,
            prohibits=provision.prohibits,
            when=provision.when,
            unless=provision.unless,
            verify=provision.verify,
        ),
    )


PROTOCOL_FIELDS = frozenset(
    {
        "title",
        "purpose",
        "rationale",
        "states",
        "initial",
        "accepting",
        "data",
        "hooks",
    }
)
HOOK_FIELDS = frozenset(
    {
        "phase",
        "match",
        "from",
        "when",
        "command",
        "verify",
        "set",
        "clear",
        "to",
    }
)


def read_protocol(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Protocol | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "protocol.invalid-purpose",
        unknown="protocol.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(PROTOCOL_FIELDS, "protocol")
    purpose = reader.text(
        "purpose", required=True, missing="protocol.missing-purpose", invalid="protocol.invalid-purpose"
    )
    # A field that is absent and one that is present but malformed are different
    # mistakes with different repairs, so they report different checks: the
    # absence names the key, and the malformed value names the shape.
    states = reader.required_id_list(
        data,
        "states",
        "states is required: it names every state a frame can hold",
        missing="protocol.missing-states",
        invalid="protocol.invalid-states",
    )
    initial = reader.text(
        "initial", required=True, missing="protocol.missing-initial", invalid="protocol.invalid-initial"
    )
    accepting = reader.required_id_list(
        data,
        "accepting",
        "accepting is required: it names the states a frame may close in",
        missing="protocol.missing-accepting",
        invalid="protocol.invalid-accepting",
    )
    if initial and initial not in states:
        reader.fail(
            f"{initial!r} is not one of the declared states ({', '.join(states)})",
            "protocol.invalid-initial",
        )
    for name in accepting:
        if name not in states:
            reader.fail(
                f"{name!r} is not one of the declared states "
                f"({', '.join(states)})",
                "protocol.invalid-accepting",
            )
    fields = _read_state_fields(reader)
    hooks = _read_hooks(reader, states)
    if not hooks and "hooks" not in data:
        reader.fail(
            "hooks is required, because a protocol with no hook constrains "
            "nothing",
            "protocol.missing-hooks",
        )
    if not identifier or not reader.usable:
        return None
    return Protocol(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="protocol.invalid-title") or filename_title(identifier),
        purpose=purpose,
        rationale=reader.text("rationale", invalid="protocol.invalid-rationale"),
        states=states,
        initial=initial,
        accepting=accepting,
        data=fields,
        hooks=hooks,
    )


def _read_state_fields(reader: Reader) -> tuple[StateField, ...]:
    declared = reader.mapping("data", invalid="protocol.invalid-data")
    fields: list[StateField] = []
    # Every failure inside `data` is a repair to `data`, so each one names that
    # key rather than inheriting whichever field the reader looked at last.
    reader.code = "protocol.invalid-data"
    for name in declared:
        body = reader.item_mapping(declared, name, f"data.{name}")
        if not body:
            continue
        unknown = sorted(set(body) - {"type", "record", "default", "description"})
        if unknown:
            reader.fail(
                f"data.{name}: unrecognized fields: {', '.join(unknown)}; a state "
                "field declares type or record, an optional default, and an "
                "optional description"
            )
            continue
        found = reader.declared_type(
            {name: {k: v for k, v in body.items() if k != "default"}}, name, "data."
        )
        if found is None:
            continue
        default, usable = reader.declared_default(body, found, f"data.{name}")
        if not usable:
            continue
        fields.append(StateField(name=name, type=found, default=default))
    return tuple(fields)


def _read_hooks(reader: Reader, states: tuple[str, ...]) -> tuple[Hook, ...]:
    declared = reader.mapping("hooks", invalid="protocol.invalid-hooks")
    hooks: list[Hook] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"hooks.{name}")
        if not body:
            continue
        location = f"hooks.{name}"
        prefix = f"{location}."
        reader.code = "protocol.invalid-hook"
        unknown = sorted(set(body) - HOOK_FIELDS)
        if unknown:
            reader.fail(
                f"{location}: unrecognized fields: {', '.join(unknown)}; a hook "
                f"declares {', '.join(sorted(HOOK_FIELDS))}",
                "protocol.invalid-hook",
            )
            continue
        phase = body.get("phase")
        if phase not in HOOK_PHASES:
            reader.fail(
                f"{prefix}phase is one of {', '.join(HOOK_PHASES)}, not {phase!r}",
                "protocol.invalid-hook",
            )
            continue
        boundary = phase in ("enter", "exit")
        if boundary and "match" in body:
            reader.fail(
                f"{location}: an {phase} hook runs at the frame boundary, so it "
                "selects no node; remove match",
                "protocol.invalid-hook",
            )
            continue
        selector = None if boundary else reader.selector(body, prefix)
        if not boundary and selector is None:
            continue
        from_states = reader.id_list(body, "from", prefix)
        if not from_states:
            reader.fail(
                f"{prefix}from is a non-empty list of the states this hook runs "
                "from",
                "protocol.invalid-hook",
            )
            continue
        unknown_states = [item for item in from_states if item not in states]
        if unknown_states:
            reader.fail(
                f"{prefix}from names {', '.join(unknown_states)}, which is not a "
                "declared state",
                "protocol.invalid-state",
            )
            continue
        target = body.get("to", "")
        if "to" in body and (
            not isinstance(target, str) or not target.strip() or target not in states
        ):
            reader.fail(
                f"{prefix}to names {target!r}, which is not a declared state",
                "protocol.invalid-state",
            )
            continue
        verify = reader.verification(body, prefix)
        command = reader.field_text(body, "command", False, prefix)
        if not command and verify is None:
            reader.fail(
                f"{location}: declares neither command nor verify, so the "
                "generated node would state nothing to do",
                "protocol.invalid-hook",
            )
            continue
        updates: tuple[tuple[str, Binding], ...] = reader.bindings(body, "set", prefix)
        clears = reader.id_list(body, "clear", prefix)
        hooks.append(
            Hook(
                id=name,
                phase=phase,
                selector=selector,
                from_states=from_states,
                command=command,
                when=reader.condition(body, "when", prefix),
                verify=verify,
                updates=updates,
                clears=clears,
                to=str(target),
            )
        )
    reader.code = "protocol.invalid-hooks"
    return tuple(hooks)


PATTERN_FIELDS = frozenset(
    {"title", "summary", "inputs", "procedure", "references"}
)
PROCEDURE_ITEM_FIELDS = frozenset({"command", "uses", "subjects", "effects"})


def read_pattern(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Pattern | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "pattern.invalid-summary",
        unknown="pattern.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(PATTERN_FIELDS, "pattern")
    summary = reader.text(
        "summary", required=True, missing="pattern.missing-summary", invalid="pattern.invalid-summary"
    )
    inputs = _read_declared_values(reader, "inputs", "pattern.invalid-inputs")
    declared = reader.mapping(
        "procedure", required=True, missing="pattern.missing-procedure", invalid="pattern.invalid-procedure"
    )
    items: list[ProcedureItem] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"procedure.{name}")
        if not body:
            continue
        location = f"procedure.{name}"
        with reader.under("pattern.invalid-procedure"):
            unknown = sorted(set(body) - PROCEDURE_ITEM_FIELDS)
            if unknown:
                reader.fail(
                    f"{location}: unrecognized fields: {', '.join(unknown)}; a "
                    "procedure item declares "
                    f"{', '.join(sorted(PROCEDURE_ITEM_FIELDS))}. A procedure "
                    "item does not branch, call, return, or produce a value: use a workflow where reusable behavior "
                    "needs those"
                )
                continue
            command = reader.field_text(body, "command", True, f"{location}.")
            if not command:
                continue
            items.append(
                ProcedureItem(
                    id=name,
                    command=command,
                    uses=reader.text_list(body, "uses", f"{location}."),
                    subjects=reader.tag_list(body, "subjects", f"{location}."),
                    effects=reader.tag_list(body, "effects", f"{location}."),
                )
            )
    declared_inputs = {name for name, _ in inputs}
    for item in items:
        for text in item.uses:
            try:
                reference = parse_reference(text)
            except ExpressionError as exc:
                reader.fail(
                    f"procedure.{item.id}.uses: {exc}", "pattern.invalid-use"
                )
                continue
            root = reference.path[0] if reference.path else ""
            if reference.namespace != "input" or root not in declared_inputs:
                reader.fail(
                    f"procedure.{item.id}.uses names {text}, which is not a "
                    "declared pattern input",
                    "pattern.invalid-use",
                )
    if not identifier or not reader.usable or not items:
        return None
    return Pattern(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="pattern.invalid-title") or filename_title(identifier),
        summary=summary,
        inputs=inputs,
        procedure=tuple(items),
        references=reader.text_list(data, "references", invalid="pattern.invalid-references"),
    )


HEURISTIC_FIELDS = frozenset({"title", "question", "advice", "references"})
ADVICE_FIELDS = frozenset({"prefer", "when", "because", "caution"})


def read_heuristic(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Heuristic | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "heuristic.invalid-question",
        unknown="heuristic.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(HEURISTIC_FIELDS, "heuristic")
    question = reader.text(
        "question", required=True, missing="heuristic.missing-question", invalid="heuristic.invalid-question"
    )
    declared = reader.mapping(
        "advice", required=True, missing="heuristic.missing-advice", invalid="heuristic.invalid-advice"
    )
    reader.code = "heuristic.invalid-advice"
    advice: list[Advice] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"advice.{name}")
        if not body:
            continue
        location = f"advice.{name}"
        unknown = sorted(set(body) - ADVICE_FIELDS)
        if unknown:
            reader.fail(
                f"{location}: unrecognized fields: {', '.join(unknown)}; advice "
                f"declares {', '.join(sorted(ADVICE_FIELDS))}"
            )
            continue
        prefer = reader.field_text(body, "prefer", True, f"{location}.")
        if not prefer:
            continue
        advice.append(
            Advice(
                id=name,
                prefer=prefer,
                when=reader.condition(body, "when", f"{location}."),
                because=reader.field_text(body, "because", False, f"{location}."),
                caution=reader.field_text(body, "caution", False, f"{location}."),
            )
        )
    if not identifier or not reader.usable or not advice:
        return None
    return Heuristic(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="heuristic.invalid-title") or filename_title(identifier),
        question=question,
        advice=tuple(advice),
        references=reader.text_list(data, "references", invalid="heuristic.invalid-references"),
    )


GUIDANCE_FIELDS = frozenset(
    {"title", "summary", "rationale", "points", "references"}
)


def read_guidance(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Guidance | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "guidance.invalid-summary",
        unknown="guidance.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(GUIDANCE_FIELDS, "guidance")
    summary = reader.text(
        "summary", required=True, missing="guidance.missing-summary", invalid="guidance.invalid-summary"
    )
    if not identifier or not reader.usable:
        return None
    return Guidance(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="guidance.invalid-title") or filename_title(identifier),
        summary=summary,
        rationale=reader.text("rationale", invalid="guidance.invalid-rationale"),
        points=reader.text_list(data, "points", invalid="guidance.invalid-points"),
        references=reader.text_list(data, "references", invalid="guidance.invalid-references"),
    )


PROFILE_FIELDS = frozenset(
    {"title", "description", "points", "references", "category"}
)
# What a profile may never contribute. Profiles are auxiliary retrieval targets;
# workflow correctness and mandatory safety cannot depend on their presence.
PROFILE_FORBIDDEN: tuple[str, ...] = ("policies", "rules", "protocols", "workflows")


def read_profile(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Profile | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "profile.invalid-title",
        unknown="profile.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    binding = sorted(set(data) & set(PROFILE_FORBIDDEN))
    if binding:
        reader.fail(
            f"a profile cannot contribute {', '.join(binding)}: profile guidance "
            "is auxiliary, and mandatory behavior cannot depend on it",
            "profile.binding-contribution",
        )
    reader.unknown_fields(PROFILE_FIELDS, "profile")
    if "title" not in data:
        reader.warn(
            "title is missing; the filename-derived title is used",
            "profile.missing-title",
        )
    description = reader.text("description", invalid="profile.invalid-description")
    category = reader.text("category", invalid="profile.invalid-category")
    if "points" not in data:
        reader.fail(
            "points is required: it is the prose this profile contributes",
            "profile.missing-points",
        )
    points = reader.text_list(data, "points", invalid="profile.invalid-points")
    references = reader.text_list(
        data, "references", invalid="profile.invalid-references"
    )
    if not identifier or not reader.usable:
        return None
    return Profile(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="profile.invalid-title") or filename_title(identifier),
        description=description,
        points=points,
        references=references,
        category=category,
    )


RECORD_FIELDS = frozenset({"title", "fields"})


def read_record(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Record | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "record.invalid-fields",
        unknown="record.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(RECORD_FIELDS, "record")
    declared = reader.mapping(
        "fields", required=True, missing="record.missing-fields", invalid="record.invalid-fields"
    )
    fields: list[RecordField] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"fields.{name}")
        if not body:
            continue
        unknown = sorted(set(body) - {"type", "record", "description"})
        if unknown:
            reader.fail(
                f"fields.{name}: unrecognized fields: {', '.join(unknown)}; a "
                "record field declares type or record, and an optional description"
            )
            continue
        found = reader.declared_type(declared, name, "fields.")
        if found is None:
            continue
        fields.append(
            RecordField(
                name=name,
                type=found,
                description=reader.field_text(
                    body, "description", False, f"fields.{name}.", "value.invalid-description"
                ),
            )
        )
    if not identifier or not reader.usable or not fields:
        return None
    return Record(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="record.invalid-title") or filename_title(identifier),
        fields=tuple(fields),
    )


def _read_declared_values(
    reader: Reader, key: str, invalid: str = ""
) -> tuple[tuple[str, ValueType], ...]:
    declared = reader.mapping(key, invalid=invalid)
    values: list[tuple[str, ValueType]] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"{key}.{name}")
        if not body:
            continue
        found = reader.declared_type(declared, name, f"{key}.")
        if found is not None:
            values.append((name, found))
    return tuple(values)


# --------------------------------------------------------------------------
# Workflows
# --------------------------------------------------------------------------


def read_workflow(
    path: Path, data: dict[str, Any], diagnostics: Diagnostics
) -> Workflow | None:
    reader = Reader(
        path,
        data,
        diagnostics,
        "workflow.invalid-description",
        unknown="workflow.unknown-field",
    )
    identifier = _stem_id(path, diagnostics)
    reader.unknown_fields(WORKFLOW_FIELDS, "workflow")
    description = reader.text(
        "description", required=True, missing="workflow.missing-description", invalid="workflow.invalid-description"
    )
    entry = reader.text("entry", required=True, missing="workflow.missing-entry", invalid="workflow.invalid-entry")
    if entry and not ID_PATTERN.fullmatch(entry):
        reader.fail("entry names one step id, in lowercase letters, digits, and hyphens", "workflow.invalid-entry")
    inputs = _read_declared_values(reader, "inputs", "workflow.invalid-inputs")
    outcomes = _read_outcomes(reader)
    steps = _read_steps(reader)
    if not identifier or not reader.usable:
        return None
    return Workflow(
        id=identifier,
        path=path,
        title=reader.text("title", invalid="workflow.invalid-title") or filename_title(identifier),
        description=description,
        entry=entry,
        steps=steps,
        inputs=inputs,
        outcomes=outcomes,
        policies=reader.id_list(data, "policies", invalid="workflow.invalid-policies"),
        rules=reader.id_list(data, "rules", invalid="workflow.invalid-rules"),
        protocols=reader.id_list(data, "protocols", invalid="workflow.invalid-protocols"),
        guidance=reader.guidance_uses(data, invalid="workflow.invalid-guidance"),
    )


def _read_outcomes(reader: Reader) -> tuple[Outcome, ...]:
    declared = reader.mapping(
        "outcomes", required=True, missing="workflow.missing-outcomes", invalid="workflow.invalid-outcomes"
    )
    outcomes: list[Outcome] = []
    for name in declared:
        body = declared.get(name)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            reader.fail(
                f"outcomes.{name} is a mapping naming an optional record, or {{}}"
            )
            continue
        unknown = sorted(set(body) - {"record"})
        if unknown:
            reader.fail(
                f"outcomes.{name}: unrecognized fields: {', '.join(unknown)}; an "
                "outcome declares an optional record"
            )
            continue
        record = body.get("record", "")
        if "record" in body and (
            not isinstance(record, str)
            or not record.strip()
            or not ID_PATTERN.fullmatch(record)
        ):
            reader.fail(
                f"outcomes.{name}.record names one record file stem",
                "workflow.invalid-outcomes",
            )
            continue
        outcomes.append(Outcome(id=name, record=str(record)))
    return tuple(outcomes)


def _step_form(reader: Reader, name: str, body: dict[str, Any]) -> str:
    present = [form for form in STEP_FORMS if form in body]
    if len(present) == 1:
        return present[0]
    if not present:
        reader.fail(
            f"steps.{name}: declares no step form; a step names exactly one of "
            f"{', '.join(STEP_FORMS)}",
            "workflow.invalid-step",
        )
        return ""
    reader.fail(
        f"steps.{name}: declares {', '.join(present)}; a step names exactly one "
        "step form",
        "workflow.invalid-step",
    )
    return ""


_FORM_FIELDS: dict[str, frozenset[str]] = {
    "action": frozenset({"action", "uses", "produces", "resource", "next"}),
    "branch": frozenset({"branch"}),
    "decide": frozenset({"decide", "uses", "choices"}),
    "gate": frozenset({"gate", "uses", "states"}),
    "use": frozenset({"use", "with", "on"}),
    "pattern": frozenset({"pattern", "with", "next"}),
    "return": frozenset({"return"}),
}


def _read_steps(reader: Reader) -> tuple[Step, ...]:
    declared = reader.mapping(
        "steps", required=True, missing="workflow.missing-steps", invalid="workflow.invalid-steps"
    )
    steps: list[Step] = []
    for name in declared:
        body = reader.item_mapping(declared, name, f"steps.{name}")
        if not body:
            continue
        form = _step_form(reader, name, body)
        if not form:
            continue
        location = f"steps.{name}"
        prefix = f"{location}."
        allowed = _FORM_FIELDS[form] | COMMON_STEP_FIELDS
        unknown = sorted(set(body) - allowed)
        if unknown:
            reader.fail(
                f"{location}: a {form} step does not declare "
                f"{', '.join(unknown)}; it declares "
                f"{', '.join(sorted(allowed))}",
                "workflow.invalid-step",
            )
            continue
        if form == "pattern" and body.get("effects"):
            reader.fail(
                f"{location}: a pattern application does not declare effects; "
                "put each effect on the procedure item that performs it",
                "pattern.invalid-effects",
            )
            continue
        if "heuristics" in body and form not in ("decide", "gate"):
            reader.fail(
                f"{location}: a {form} step names heuristics; a heuristic aids a "
                "choice among valid alternatives, so it belongs on a decide or a "
                "gate and nowhere else",
                "heuristic.invalid-placement",
            )
            continue
        reader.code = "workflow.invalid-step"
        common = {
            "policies": reader.id_list(body, "policies", prefix),
            "rules": reader.id_list(body, "rules", prefix),
            "protocols": reader.id_list(body, "protocols", prefix),
            "guidance": reader.guidance_uses(body, prefix),
            "subjects": reader.tag_list(body, "subjects", prefix),
            "effects": reader.tag_list(body, "effects", prefix),
        }
        step = _read_step_form(reader, name, body, form, location, common)
        reader.code = "workflow.invalid-steps"
        if step is not None:
            steps.append(step)
    return tuple(steps)


def _read_resource_use(
    reader: Reader, body: dict[str, Any], prefix: str
) -> ResourceUse | None:
    if "resource" not in body:
        return None
    value = body.get("resource")
    if not isinstance(value, dict) or len(value) != 1:
        reader.fail(
            f"{prefix}resource declares exactly one of run, read, copy, or fill",
            "resource.invalid-operation",
        )
        return None
    operation, path = next(iter(value.items()))
    if operation not in {"run", "read", "copy", "fill"} or not isinstance(path, str):
        reader.fail(
            f"{prefix}resource declares exactly one of run, read, copy, or fill with a relative path",
            "resource.invalid-operation",
        )
        return None
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/") or not normalized.strip():
        reader.fail(
            f"{prefix}resource path must stay inside the skill bundle",
            "resource.invalid-path",
        )
        return None
    required_prefix = {"run": "scripts/", "copy": "assets/", "fill": "assets/"}.get(operation)
    if required_prefix and not normalized.startswith(required_prefix):
        reader.fail(
            f"{prefix}resource.{operation} must name a path under {required_prefix}",
            "resource.invalid-path",
        )
        return None
    if operation == "read" and not normalized.startswith(("references/", "assets/")):
        reader.fail(
            f"{prefix}resource.read must name a path under references/ or assets/",
            "resource.invalid-path",
        )
        return None
    return ResourceUse(operation, normalized)


def _read_step_form(
    reader: Reader,
    name: str,
    body: dict[str, Any],
    form: str,
    location: str,
    common: dict[str, Any],
) -> Step | None:
    prefix = f"{location}."
    if form == "action":
        command = reader.field_text(body, "action", True, prefix)
        successor = reader.field_text(body, "next", True, prefix)
        if not command or not successor:
            return None
        return Step(
            id=name,
            form=form,
            command=command,
            uses=reader.text_list(body, "uses", prefix),
            produces=_read_step_values(reader, body, "produces", prefix),
            resource=_read_resource_use(reader, body, prefix),
            next=successor,
            **common,
        )
    if form == "branch":
        cases = _read_branch(reader, body, location)
        if not cases:
            return None
        return Step(id=name, form=form, cases=cases, **common)
    if form in ("decide", "gate"):
        command = reader.field_text(body, form, True, prefix)
        key = "choices" if form == "decide" else "states"
        options = _read_options(reader, body, key, location)
        if not command or not options:
            return None
        return Step(
            id=name,
            form=form,
            command=command,
            options=options,
            uses=reader.text_list(body, "uses", prefix),
            heuristics=reader.id_list(body, "heuristics", prefix),
            **common,
        )
    if form == "use":
        call = reader.field_text(body, "use", True, prefix)
        mapped = _read_outcome_map(reader, body, location)
        if not call or not mapped:
            return None
        if not ID_PATTERN.fullmatch(call):
            reader.fail(f"{prefix}use names one workflow file stem", "workflow.invalid-step")
            return None
        return Step(
            id=name,
            form=form,
            call=call,
            supplied=reader.bindings(body, "with", prefix),
            on=mapped,
            **common,
        )
    if form == "pattern":
        pattern = reader.field_text(body, "pattern", True, prefix)
        successor = reader.field_text(body, "next", True, prefix)
        if not pattern or not successor:
            return None
        if not ID_PATTERN.fullmatch(pattern):
            reader.fail(
                f"{prefix}pattern names one pattern file stem", "workflow.invalid-step"
            )
            return None
        return Step(
            id=name,
            form=form,
            pattern=pattern,
            supplied=reader.bindings(body, "with", prefix),
            next=successor,
            **common,
        )
    returned = body.get("return")
    if not isinstance(returned, dict):
        reader.fail(
            f"{prefix}return is a mapping naming the outcome and its values",
            "workflow.invalid-step",
        )
        return None
    unknown = sorted(set(returned) - {"outcome", "with"})
    if unknown:
        reader.fail(
            f"{prefix}return: unrecognized fields: {', '.join(unknown)}; a "
            "return declares an outcome and an optional with",
            "workflow.invalid-step",
        )
        return None
    outcome = reader.field_text(returned, "outcome", True, f"{prefix}return.")
    if not outcome:
        return None
    return Step(
        id=name,
        form=form,
        outcome=outcome,
        supplied=reader.bindings(returned, "with", f"{prefix}return."),
        **common,
    )


def _read_step_values(
    reader: Reader, body: dict[str, Any], key: str, prefix: str
) -> tuple[ProducedValue, ...]:
    """Read what one action produces, with the default each value falls back to.

    `default` is taken out of the declaration before the shared reader sees it,
    the way protocol state data takes out its own: the other three declaration
    sites name nothing that could go unwritten, so a default there is an
    unrecognized field and the shared reader is what says so.
    """
    declared = reader.submapping(body, key, prefix)
    values: list[ProducedValue] = []
    for name in declared:
        item = declared.get(name)
        location = f"{prefix}{key}.{name}"
        if not isinstance(item, dict):
            reader.fail(f"{location} is a mapping naming its type")
            continue
        unknown = sorted(set(item) - {"type", "record", "default", "description"})
        if unknown:
            reader.fail(
                f"{location}: unrecognized fields: {', '.join(unknown)}; a "
                "produced value declares type or record, an optional default, "
                "and an optional description",
            )
            continue
        found = reader.declared_type(
            {name: {k: v for k, v in item.items() if k != "default"}},
            name,
            f"{prefix}{key}.",
        )
        if found is None:
            continue
        default, usable = reader.declared_default(item, found, location)
        if not usable:
            continue
        values.append(ProducedValue(name=name, type=found, default=default))
    return tuple(values)


def _read_branch(
    reader: Reader, body: dict[str, Any], location: str
) -> tuple[BranchCase, ...]:
    value = body.get("branch")
    if not isinstance(value, list) or not value:
        reader.fail(
            f"{location}.branch is a non-empty ordered list of cases",
            "workflow.invalid-step",
        )
        return ()
    cases: list[BranchCase] = []
    for index, item in enumerate(value):
        where = f"{location}.branch[{index}]"
        if not isinstance(item, dict):
            reader.fail(
                f"{where} is a mapping with when and next, or otherwise",
                "workflow.invalid-step",
            )
            return ()
        keys = sorted(item)
        if keys == ["otherwise"]:
            if index != len(value) - 1:
                reader.fail(
                    f"{where}: otherwise closes a branch, so nothing follows it",
                    "workflow.invalid-step",
                )
                return ()
            target = item["otherwise"]
            if not isinstance(target, str) or not ID_PATTERN.fullmatch(target):
                reader.fail(f"{where}.otherwise names one step id", "workflow.invalid-step")
                return ()
            cases.append(BranchCase(when=None, next=target))
            continue
        if keys != ["next", "when"]:
            reader.fail(
                f"{where} declares when and next, or otherwise alone",
                "workflow.invalid-step",
            )
            return ()
        condition = reader.condition(item, "when", f"{where}.")
        target = item["next"]
        if condition is None or not isinstance(target, str) or not ID_PATTERN.fullmatch(target):
            if condition is not None:
                reader.fail(f"{where}.next names one step id", "workflow.invalid-step")
            return ()
        cases.append(BranchCase(when=condition, next=target))
    if cases[-1].when is not None:
        reader.fail(
            f"{location}.branch: the final case is otherwise, so every path "
            "reaching this branch continues somewhere",
            "workflow.invalid-step",
        )
        return ()
    return tuple(cases)


def _read_options(
    reader: Reader, body: dict[str, Any], key: str, location: str
) -> tuple[Option, ...]:
    declared = reader.submapping(body, key, f"{location}.")
    if not declared:
        return ()
    options: list[Option] = []
    for name in declared:
        item = declared.get(name)
        where = f"{location}.{key}.{name}"
        if not isinstance(item, dict):
            reader.fail(
                f"{where} is a mapping with a command and a next step",
                "workflow.invalid-step",
            )
            return ()
        unknown = sorted(set(item) - {"command", "next"})
        if unknown:
            reader.fail(
                f"{where}: unrecognized fields: {', '.join(unknown)}; each names "
                "a command and a next step",
                "workflow.invalid-step",
            )
            return ()
        command = reader.field_text(item, "command", True, f"{where}.")
        target = item.get("next")
        if not command:
            return ()
        if not isinstance(target, str) or not ID_PATTERN.fullmatch(target):
            reader.fail(f"{where}.next names one step id", "workflow.invalid-step")
            return ()
        options.append(Option(id=name, command=command, next=target))
    if len(options) < 2:
        reader.fail(
            f"{location}.{key} names at least two alternatives, because a closed "
            "judgment with one answer decides nothing",
            "workflow.invalid-step",
        )
        return ()
    return tuple(options)


def _read_outcome_map(
    reader: Reader, body: dict[str, Any], location: str
) -> tuple[CallOutcome, ...]:
    declared = reader.submapping(body, "on", f"{location}.")
    if not declared:
        reader.fail(
            f"{location}.on maps every outcome the called workflow declares to a "
            "next step",
            "workflow.invalid-step",
        )
        return ()
    mapped: list[CallOutcome] = []
    for name, target in declared.items():
        capture = ""
        if isinstance(target, str):
            successor = target
        elif isinstance(target, dict):
            unknown = sorted(set(target) - {"next", "as"})
            successor = target.get("next")
            capture = target.get("as", "")
            if (
                unknown
                or not isinstance(successor, str)
                or ("as" in target and (
                    not isinstance(capture, str) or not capture.strip()
                ))
            ):
                reader.fail(
                    f"{location}.on.{name} declares next and optional as",
                    "workflow.invalid-step",
                )
                return ()
        else:
            reader.fail(
                f"{location}.on.{name} names one step id or a next/as mapping",
                "workflow.invalid-step",
            )
            return ()
        if not ID_PATTERN.fullmatch(successor):
            reader.fail(
                f"{location}.on.{name}.next names one step id", "workflow.invalid-step"
            )
            return ()
        if capture and not ID_PATTERN.fullmatch(capture):
            reader.fail(
                f"{location}.on.{name}.as names one result id", "workflow.invalid-step"
            )
            return ()
        mapped.append(CallOutcome(name, successor, capture))
    return tuple(mapped)


# The reader each parsed content key uses, so the manifest key that selected a
# file is what decides the schema it must satisfy.
CONSTRUCT_READERS = {
    "policies": read_policy,
    "rules": read_rule,
    "patterns": read_pattern,
    "heuristics": read_heuristic,
    "guidance": read_guidance,
    "protocols": read_protocol,
    "records": read_record,
    "workflows": read_workflow,
    "profiles": read_profile,
}

# What one construct kind is called in a message, and the field it lives in.
CONSTRUCT_LABELS = {
    "policies": "policy",
    "rules": "rule",
    "patterns": "pattern",
    "heuristics": "heuristic",
    "guidance": "guidance unit",
    "protocols": "protocol",
    "records": "record",
    "workflows": "workflow",
    "profiles": "profile",
}
