"""Read the source constructs: tasks, domain knowledge, and facets.

Four constructs of authored source reach the compiler, and each is one Markdown
file whose file stem is its identity. The manifest says which construct namespace
a file belongs to; knowledge files additionally state a `kind` that controls how
they are grouped when rendered. Nothing here reads an `id` field, and every
reader refuses one: the filename already carries the name, and a second spelling
of it in frontmatter is a name that can disagree with itself.

A **task** is a recognizable class of work the requester wants performed. It is
the only construct a request is routed to, and it is where the compiler assembles
a page an agent can act on without following anything.

A **knowledge unit** is domain expertise, authored once and compiled into every
task that needs it. It declares what it requires; that relationship exists
because the compiler consumes it to expand a task's closure, and for no other
reason. A relationship nothing consumes would be a claim in the source that the
bundle cannot show.

A **facet** is skill-wide guidance for one aspect of the situation — the
audience, the kind of material, the rules in force — that the agent selects from
the situation in front of it rather than from any task. That selection is a
genuine runtime choice, so it is preserved; every authoring choice around it is
compiled away.

A **principle** is guidance a skill or task may need. The level that uses one
names it; what each says is the author's, read from this skill's own
`principles/` directory and nowhere else. The compiler owns no principle text of
its own, so two builds of one source say the same thing whichever version of the
compiler ran.

Each reader collects every problem it finds rather than stopping at the first,
and each writes its check code out at the call site that reports it, so the
coverage check can read this module and find every code it can emit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .markdown import MarkdownSource
from .model import Diagnostics


# Knowledge kinds are presentation categories, not namespaces. Every unit lives
# in the same `knowledge` namespace and is referenced by bare id. The tuple order
# is the canonical order of the subsections rendered on every task page.
KNOWLEDGE_KINDS: tuple[str, ...] = (
    "concept",
    "fact",
    "constraint",
    "guidance",
)
CONSTRAINT_KIND = "constraint"

CONSTRUCT_LABELS: dict[str, str] = {
    "tasks": "task",
    "principles": "principle",
    "knowledge": "knowledge",
    "facets": "facet",
    "guides": "guide",
}

# A construct id, which is a file stem. The same spelling as a skill name, so an
# author learns one rule rather than one per position.
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


TASK_FIELDS = frozenset({"title", "recognize", "goal", "knowledge", "principles", "guides"})
KNOWLEDGE_FIELDS = frozenset({"kind", "title", "requires"})
PRINCIPLE_FIELDS = frozenset({"title", "activation"})
FACET_FIELDS = frozenset({"title", "category", "description", "guides"})
GUIDE_FIELDS = frozenset({"title", "activation"})

# The field a Markdown source may never declare, because its filename already
# states it.
DERIVED_FIELD = "id"


@dataclass(frozen=True)
class Guide:
    """One optional knowledge page, identified by its file stem."""

    id: str
    path: Path
    title: str
    activation: str = ""
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Task:
    """One recognizable class of work, as its author declared it."""

    id: str
    path: Path
    title: str
    goal: str
    recognize: tuple[str, ...] = ()
    knowledge: tuple[str, ...] = ()
    principles: tuple[str, ...] = ()
    guides: tuple[str, ...] = ()
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Knowledge:
    """One unit of domain expertise, and what it cannot be understood without."""

    id: str
    kind: str
    path: Path
    title: str
    requires: tuple[str, ...] = ()
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        return self.id


@dataclass(frozen=True)
class Principle:
    """One piece of guidance this skill holds across its tasks.

    A principle is authored in the skill that uses it, like everything else a
    skill says. The compiler decides where each one is stated and adjusts its
    heading depth to fit the page; it never supplies, substitutes, or reworks the
    words. So the same source states the same guidance whichever version of the
    compiler built it.
    """

    id: str
    path: Path
    title: str
    activation: str = ""
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Facet:
    """One situational overlay the running agent decides the applicability of.

    Guides are named here the way a task names them, because it is the same
    relationship: material this guidance needs but does not carry, loaded as its
    own page. What differs is only who decided the load was warranted — the
    situation the agent recognized, rather than the work it was asked for.
    """

    id: str
    path: Path
    title: str
    category: str = ""
    description: str = ""
    guides: tuple[str, ...] = ()
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass
class SourceSet:
    """Every construct one skill selects, keyed the way a reference names it."""

    tasks: dict[str, Task] = field(default_factory=dict)
    principles: dict[str, Principle] = field(default_factory=dict)
    knowledge: dict[str, Knowledge] = field(default_factory=dict)
    facets: dict[str, Facet] = field(default_factory=dict)
    guides: dict[str, Guide] = field(default_factory=dict)

    def kind(self, key: str) -> dict[str, Any]:
        """The store one content key fills, so a loader need not switch on the key.

        An unrecognized key raises rather than resolving to a default store: a
        key with no store is a content key this class was never told about, and
        answering it with the wrong dictionary would file those constructs under
        a namespace no reference names.
        """
        stores: dict[str, dict[str, Any]] = {
            "tasks": self.tasks,
            "principles": self.principles,
            "knowledge": self.knowledge,
            "facets": self.facets,
            "guides": self.guides,
        }
        return stores[key]

    def of_kind(self, kind: str) -> list[Knowledge]:
        """Every knowledge unit of one kind, in id order."""
        return [
            unit
            for _, unit in sorted(self.knowledge.items())
            if unit.kind == kind
        ]


class _Reader:
    """One source file being read, and the findings that reading it produced.

    Every field check needs the same three things — the value, where to report a
    problem, and the code to report it under — so they are held once here and
    each call site states only what is specific to it: the field name and the two
    codes. The codes stay written out at the call site rather than assembled from
    the field name, because a code assembled at runtime is a code the coverage
    check can no longer find in this module's source.
    """

    def __init__(
        self,
        source: MarkdownSource,
        label: str,
        allowed: frozenset[str],
        diagnostics: Diagnostics,
    ) -> None:
        self.source = source
        self.label = label
        self.fields = source.fields
        self.diagnostics = diagnostics
        self.ok = True
        self._allowed = allowed

    def error(self, message: str, code: str) -> None:
        self.ok = False
        self.diagnostics.error(f"{self.source.path}: {message}", code, self.source.path)

    def where(self, name: str) -> str:
        return f"{self.label} {self.source.id}: {name}"

    def unknown_fields(
        self, code: str, *, extensions: bool = False, warning: bool = False
    ) -> None:
        unknown = sorted(
            name
            for name in set(self.fields) - self._allowed - {DERIVED_FIELD}
            if not extensions or not name.startswith("x-")
        )
        if unknown:
            message = f"unrecognized {self.label} fields: {', '.join(unknown)}"
            if warning:
                self.diagnostics.warning(
                    f"{self.source.path}: {message}", code, self.source.path
                )
            else:
                self.error(message, code)

    def declared_id(self, code: str) -> None:
        """Refuse an id in frontmatter, naming the id the filename already gives.

        The message states the derived value rather than only refusing the
        field, because an author who wrote one was telling the compiler what to
        call this file, and the answer is that it is already called that.
        """
        if DERIVED_FIELD in self.fields:
            self.error(
                f"this {self.label} declares an {DERIVED_FIELD} field; an id is "
                f"derived from the file name, so this {self.label}'s id is "
                f"{self.source.id!r}. Remove the field",
                code,
            )

    def metadata(self) -> dict[str, Any]:
        """Keep custom fields without making them part of the source schema.

        Constructs may travel between tools that add their own `x-` frontmatter.
        The compiler must still parse that YAML safely, but a field it does not
        consume cannot change the artifact, so it is retained only for callers
        that need the source model.
        """
        return {name: value for name, value in self.fields.items() if name.startswith("x-")}

    def string(self, name: str, missing: str, invalid: str) -> str:
        if name not in self.fields:
            self.error(f"{self.where(name)} is required", missing)
            return ""
        value = self.fields[name]
        if not isinstance(value, str) or not value.strip():
            self.error(f"{self.where(name)} must be a non-empty string", invalid)
            return ""
        return value.strip()

    def choice(
        self,
        name: str,
        values: tuple[str, ...],
        missing: str,
        invalid: str,
    ) -> str:
        """One required string chosen from a closed vocabulary."""
        if name not in self.fields:
            self.error(f"{self.where(name)} is required", missing)
            return ""
        value = self.fields[name]
        if not isinstance(value, str) or value.strip() not in values:
            self.error(
                f"{self.where(name)} must be one of {', '.join(values)}", invalid
            )
            return ""
        return value.strip()

    def optional_string(self, name: str, invalid: str) -> str:
        if name not in self.fields:
            return ""
        value = self.fields[name]
        if not isinstance(value, str) or not value.strip():
            self.error(f"{self.where(name)} must be a non-empty string", invalid)
            return ""
        return value.strip()

    def sentences(self, name: str, missing: str, invalid: str) -> tuple[str, ...]:
        if name not in self.fields:
            self.error(f"{self.where(name)} is required", missing)
            return ()
        return self._sentences(name, invalid)

    def optional_sentences(self, name: str, invalid: str) -> tuple[str, ...]:
        if name not in self.fields:
            return ()
        return self._sentences(name, invalid)

    def _sentences(self, name: str, invalid: str) -> tuple[str, ...]:
        value = self.fields[name]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            self.error(
                f"{self.where(name)} must be a non-empty list of sentences", invalid
            )
            return ()
        return tuple(item.strip() for item in value)

    def names(self, name: str, invalid: str) -> tuple[str, ...]:
        """A list of bare ids, which is what a field naming one namespace holds.

        `principles` names principles and nothing else, so the field itself
        establishes the namespace and a qualified reference there would repeat
        what the key already said.
        """
        if name not in self.fields:
            return ()
        value = self.fields[name]
        if (
            not isinstance(value, list)
            or not value
            or any(
                not isinstance(item, str) or not NAME_PATTERN.fullmatch(item.strip())
                for item in value
            )
        ):
            self.error(
                f"{self.where(name)} must be a non-empty list of ids, in "
                "lowercase letters, digits, and single hyphens",
                invalid,
            )
            return ()
        found = tuple(item.strip() for item in value)
        repeated = sorted({item for item in found if found.count(item) > 1})
        if repeated:
            self.error(
                f"{self.where(name)} names {', '.join(repeated)} more than once",
                invalid,
            )
            return ()
        return found

def _check_name(source: MarkdownSource, label: str, diagnostics: Diagnostics) -> bool:
    """Hold a filename to the spelling every id in this format uses.

    The stem is the id, so a stem that is not a usable id is a construct that
    cannot be referenced, linked to, or written to a predictable page path.
    """
    if NAME_PATTERN.fullmatch(source.id):
        return True
    diagnostics.error(
        f"{source.path}: a {label} file stem is its id, and "
        f"{source.id!r} is not one; use lowercase letters, digits, and single "
        "hyphens",
        "source.invalid-name",
        source.path,
    )
    return False


def read_task(source: MarkdownSource, diagnostics: Diagnostics) -> Task | None:
    """Read one task: what it is, how it is recognized, and what it needs."""
    if not _check_name(source, "task", diagnostics):
        return None
    reader = _Reader(source, "task", TASK_FIELDS, diagnostics)
    reader.unknown_fields("task.unknown-field", extensions=True, warning=True)
    reader.declared_id("task.unexpected-id")
    title = reader.string("title", "task.missing-title", "task.invalid-title")
    recognize = reader.sentences(
        "recognize", "task.missing-recognize", "task.invalid-recognize"
    )
    goal = reader.string("goal", "task.missing-goal", "task.invalid-goal")
    knowledge = reader.names("knowledge", "task.invalid-knowledge")
    principles = reader.names("principles", "task.invalid-principles")
    guides = _read_guides(reader, "task.invalid-guides")
    if not reader.ok:
        return None
    return Task(
        id=source.id,
        path=source.path,
        title=title,
        goal=goal,
        recognize=recognize,
        knowledge=knowledge,
        principles=principles,
        guides=guides,
        body=source.body,
        metadata=reader.metadata(),
    )


def _read_guides(reader: _Reader, invalid: str) -> tuple[str, ...]:
    """Read guide identities; each guide owns the condition for opening it.

    Two constructs name guides, and each reports under its own check, so the
    code belongs to the caller: an author repairing a facet is told that a facet
    field is unreadable rather than a task one.
    """
    return reader.names("guides", invalid)


def read_knowledge(
    source: MarkdownSource, diagnostics: Diagnostics
) -> Knowledge | None:
    """Read one unit of knowledge and the presentation kind it declares."""
    if not _check_name(source, "knowledge", diagnostics):
        return None
    reader = _Reader(source, "knowledge", KNOWLEDGE_FIELDS, diagnostics)
    reader.unknown_fields("knowledge.unknown-field", extensions=True, warning=True)
    reader.declared_id("knowledge.unexpected-id")
    kind = reader.choice(
        "kind", KNOWLEDGE_KINDS, "knowledge.missing-kind", "knowledge.invalid-kind"
    )
    title = reader.string(
        "title", "knowledge.missing-title", "knowledge.invalid-title"
    )
    requires = reader.names("requires", "knowledge.invalid-requires")
    if not source.body.strip():
        reader.error(
            "this knowledge unit states no body, so it would compile into a task "
            "page as a heading with nothing under it; write the knowledge below "
            "the frontmatter, or delete the file",
            "knowledge.empty",
        )
    if not reader.ok:
        return None
    return Knowledge(
        id=source.id,
        kind=kind,
        path=source.path,
        title=title,
        requires=requires,
        body=source.body,
        metadata=reader.metadata(),
    )


def read_principle(
    source: MarkdownSource, diagnostics: Diagnostics
) -> Principle | None:
    """Read one principle: how it is named, and the guidance it states."""
    if not _check_name(source, "principle", diagnostics):
        return None
    reader = _Reader(source, "principle", PRINCIPLE_FIELDS, diagnostics)
    reader.unknown_fields("principle.unknown-field", extensions=True, warning=True)
    reader.declared_id("principle.unexpected-id")
    title = reader.string(
        "title", "principle.missing-title", "principle.invalid-title"
    )
    activation = reader.optional_string("activation", "principle.invalid-activation")
    if not source.body.strip():
        reader.error(
            "this principle states no guidance below its frontmatter, so every "
            "page that carries it would carry a heading with nothing under it",
            "principle.empty",
        )
    if not reader.ok:
        return None
    return Principle(
        id=source.id,
        path=source.path,
        title=title,
        activation=activation,
        body=source.body,
        metadata=reader.metadata(),
    )


def read_facet(source: MarkdownSource, diagnostics: Diagnostics) -> Facet | None:
    """Read one facet: how a reader recognizes it, what it says, and what it opens."""
    if not _check_name(source, "facet", diagnostics):
        return None
    reader = _Reader(source, "facet", FACET_FIELDS, diagnostics)
    reader.unknown_fields("facet.unknown-field", extensions=True, warning=True)
    reader.declared_id("facet.unexpected-id")
    title = reader.string("title", "facet.missing-title", "facet.invalid-title")
    category = reader.optional_string("category", "facet.invalid-category")
    description = reader.optional_string("description", "facet.invalid-description")
    guides = _read_guides(reader, "facet.invalid-guides")
    if not source.body.strip():
        reader.error(
            "this facet states no body, so a reader who decided it applies "
            "would load a page with nothing on it",
            "facet.empty",
        )
    if not reader.ok:
        return None
    return Facet(
        id=source.id,
        path=source.path,
        title=title,
        category=category,
        description=description,
        guides=guides,
        body=source.body,
        metadata=reader.metadata(),
    )


def read_guide(source: MarkdownSource, diagnostics: Diagnostics) -> Guide | None:
    """Read one guide and the optional condition that opens it everywhere."""
    if not _check_name(source, "guide", diagnostics):
        return None
    reader = _Reader(source, "guide", GUIDE_FIELDS, diagnostics)
    reader.unknown_fields("guide.unknown-field", extensions=True, warning=True)
    reader.declared_id("guide.unexpected-id")
    title = reader.string("title", "guide.missing-title", "guide.invalid-title")
    activation = reader.optional_string("activation", "guide.invalid-activation")
    if not source.body.strip():
        reader.error(
            "this guide states no knowledge below its frontmatter, so a reader "
            "who needs it would open a page with nothing on it",
            "guide.empty",
        )
    if not reader.ok:
        return None
    return Guide(
        id=source.id,
        path=source.path,
        title=title,
        activation=activation,
        body=source.body,
        metadata=reader.metadata(),
    )


def read_construct(
    source: MarkdownSource, key: str, diagnostics: Diagnostics
) -> Any | None:
    """Read one selected file under the schema its content key names."""
    if key == "tasks":
        return read_task(source, diagnostics)
    if key == "principles":
        return read_principle(source, diagnostics)
    if key == "facets":
        return read_facet(source, diagnostics)
    if key == "guides":
        return read_guide(source, diagnostics)
    return read_knowledge(source, diagnostics)


def construct_key(construct: Any, key: str) -> str:
    """The store key one construct is filed under, which is its bare id."""
    return construct.id
