"""Read one YAML source under the narrow profile Format 2 accepts.

Format 2 accepts mappings, lists, strings, integers, finite numbers, booleans,
and null, and nothing else. Everything YAML can otherwise do to a source file —
share a value through an anchor and an alias, merge one mapping into another,
name a type with a tag, read a bare date as a timestamp, read `.inf` as a
number, override an earlier key with a repeated one — changes what the compiler
reads from what the author wrote, and none of it is visible in the generated
bundle. So the loader rejects each of them at the line that wrote it rather than
compiling a source whose meaning YAML supplied.

Two failures live here. A file that does not parse, or that parses into
something the profile refuses, is raised as a SourceError carrying the line and
a plain-language reading of what happened. A file that parses cleanly but holds
an unquoted scalar whose text YAML silently reinterprets is reported as warnings
the caller collects.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .model import Diagnostic, SourceError


# The unquoted spellings that read as an ordinary word and load as a boolean.
# `true`, `false`, and `null` are left out: the format accepts all three as
# values, and those are their canonical spellings, so warning about them would
# tell an author to quote the value they meant.
YAML_AMBIGUOUS_SCALARS = {
    "yes",
    "no",
    "on",
    "off",
}

YAML_NUMERIC_SCALAR = re.compile(r"^-?\d+\.\d+$")
YAML_SEXAGESIMAL_SCALAR = re.compile(r"^-?\d+(?::[0-5]?\d)+$")

# The only tags a Format 2 source may resolve to. Every other tag names a type
# the profile does not carry, whether the author wrote it or YAML's own implicit
# resolver supplied it, and the message names what was found rather than the URI.
_TAG_PREFIX = "tag:yaml.org,2002:"
ALLOWED_TAGS = frozenset(
    f"{_TAG_PREFIX}{name}"
    for name in ("str", "int", "float", "bool", "null", "seq", "map")
)
_TAG_READINGS = {
    f"{_TAG_PREFIX}timestamp": (
        "a bare date or time is read as a timestamp rather than as text; quote "
        "the value"
    ),
    f"{_TAG_PREFIX}merge": (
        "a << key merges another mapping into this one, so the fields here are "
        "not the fields the file shows; write each field out"
    ),
    f"{_TAG_PREFIX}binary": (
        "a !!binary value is decoded rather than read as text; quote the value"
    ),
    f"{_TAG_PREFIX}set": "a !!set is not a mapping, a list, or a scalar",
    f"{_TAG_PREFIX}omap": "an !!omap is not a mapping, a list, or a scalar",
    f"{_TAG_PREFIX}pairs": "a !!pairs value is not a mapping, a list, or a scalar",
}


class _Rejected(Exception):
    """One construct the profile refuses, at the line that wrote it."""

    def __init__(self, explanation: str, mark: Any = None) -> None:
        super().__init__(explanation)
        self.explanation = explanation
        self.line = None if mark is None else mark.line + 1


class StrictLoader(yaml.SafeLoader):
    """A safe loader narrowed to the values Format 2 accepts.

    Each override refuses one way YAML can make the loaded value differ from the
    text on the page. They are overrides rather than a post-load walk of the
    result because by then the evidence is gone: an alias and the value it copies
    are indistinguishable once both are plain Python, and a repeated key has
    already overwritten the field it replaced.
    """

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        event = self.peek_event()
        if isinstance(event, yaml.events.AliasEvent):
            raise _Rejected(
                f"*{event.anchor} refers to a value declared elsewhere; write "
                "the value out here",
                event.start_mark,
            )
        if getattr(event, "anchor", None) is not None:
            raise _Rejected(
                f"&{event.anchor} declares an anchor for another line to reuse; "
                "write each value where it belongs",
                event.start_mark,
            )
        return super().compose_node(parent, index)

    def construct_object(self, node, deep=False):  # type: ignore[no-untyped-def]
        if node.tag not in ALLOWED_TAGS:
            reading = _TAG_READINGS.get(node.tag)
            if reading is None:
                reading = (
                    f"the tag {node.tag} names a type this format does not "
                    "carry; remove it, or quote the value"
                )
            raise _Rejected(reading, node.start_mark)
        value = super().construct_object(node, deep=deep)
        if isinstance(value, float) and not math.isfinite(value):
            raise _Rejected(
                f"{node.value!r} is not a finite number; write a finite value, "
                "or quote it to keep it as text",
                node.start_mark,
            )
        return value

    def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self._field_name(key_node)
            if key in mapping:
                raise _Rejected(
                    f"the field {key!r} appears twice, and the later value "
                    "silently replaces the earlier one",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping

    def _field_name(self, node) -> str:  # type: ignore[no-untyped-def]
        """One mapping key, taken as the text on the page rather than as a value.

        A field name is always text, and YAML would otherwise resolve some
        perfectly ordinary names to something else: `on:` becomes the boolean
        true, and a step whose form is `on` would be a step with no `on` field.
        The tag is still checked, so a merge key or a tagged key is refused
        rather than quietly read as its own spelling.
        """
        if not isinstance(node, yaml.ScalarNode):
            raise _Rejected(
                "a field name must be text, not a list or a mapping",
                node.start_mark,
            )
        if node.tag not in ALLOWED_TAGS:
            reading = _TAG_READINGS.get(node.tag)
            raise _Rejected(
                reading
                or f"the tag {node.tag} names a type a field name cannot have",
                node.start_mark,
            )
        return node.value


@dataclass(frozen=True)
class _YamlErrorShape:
    """One recognizable parser failure, and the plain-language reading of it."""

    problem: re.Pattern[str]
    explanation: str
    context: str = ""
    # Report where the construct opened rather than where scanning stopped, for
    # a failure PyYAML detects far from the line that has to be edited.
    at_context: bool = False


# The parser failures this format's authors actually hit, in the voice of the
# compiler's own checks: what YAML did with the text, and what to write instead.
# PyYAML reports each as a context ("while scanning a quoted scalar") and a
# problem ("found unexpected end of stream"); anything not matched here keeps
# PyYAML's own wording rather than being guessed at.
_YAML_ERROR_SHAPES: tuple[_YamlErrorShape, ...] = (
    _YamlErrorShape(
        problem=re.compile(r"^mapping values are not allowed here$"),
        explanation=(
            "a colon followed by a space makes YAML read this line as a key and "
            "a value; quote the value if the colon belongs to the text, or "
            "indent this line under the key it continues"
        ),
    ),
    _YamlErrorShape(
        context="while scanning a quoted scalar",
        problem=re.compile(r"^found unexpected end of stream$"),
        explanation="a quoted value is never closed; add the closing quote",
        at_context=True,
    ),
    _YamlErrorShape(
        context="while scanning a simple key",
        problem=re.compile(r"^could not find expected ':'$"),
        explanation=(
            "this line is neither a key with a value nor part of the value "
            "above it; indent it under the key it continues, or quote the value"
        ),
        at_context=True,
    ),
    _YamlErrorShape(
        context="while scanning a block scalar",
        problem=re.compile(r"^expected a comment or a line break"),
        explanation=(
            "a block scalar indicator (| or >) must end its line; move the text "
            "to the following indented lines, or quote the value instead"
        ),
        at_context=True,
    ),
    # Before the general reserved-character shape that follows, which would
    # otherwise report a tab as an unquotable first character.
    _YamlErrorShape(
        problem=re.compile(r"^found character '\\t' that cannot start any token$"),
        explanation=(
            "a tab character indents this line; YAML accepts only spaces for "
            "indentation"
        ),
    ),
    _YamlErrorShape(
        problem=re.compile(
            r"^found character '(?P<character>[^']*)' that cannot start any token$"
        ),
        explanation=(
            "a value cannot begin with {character!r}, which YAML reserves; "
            "quote the value"
        ),
    ),
    _YamlErrorShape(
        problem=re.compile(r"^sequence entries are not allowed here$"),
        explanation=(
            "a dash after the colon starts a list item; put list items on their "
            "own indented lines, or quote the value"
        ),
    ),
    _YamlErrorShape(
        context="while parsing a flow",
        problem=re.compile(r".*"),  # any failure inside a flow collection
        explanation=(
            "a flow collection opened with [ or { is not closed as YAML "
            "expects; close it, or quote the value if the bracket belongs to "
            "the text"
        ),
        at_context=True,
    ),
    _YamlErrorShape(
        problem=re.compile(r"^expected <block end>, but found '<scalar>'$"),
        explanation=(
            "text follows a value YAML already read as complete, which is what "
            "a value starting with a quote, a bracket, or a brace does; quote "
            "the whole value"
        ),
    ),
    _YamlErrorShape(
        problem=re.compile(r"^expected <block end>, but found '<block \w+ start>'$"),
        explanation=(
            "this line is indented more deeply than the block it belongs to; "
            "align it with the keys beside it"
        ),
    ),
    _YamlErrorShape(
        problem=re.compile(r"^but found another document$"),
        explanation=(
            "the file holds more than one YAML document; a Degardis source file "
            "holds exactly one, so remove the --- separator"
        ),
    ),
)


def _yaml_error_reading(exc: yaml.YAMLError) -> tuple[int | None, str] | None:
    """Read a parser failure as a line and a plain-language fix, where known."""
    problem = str(getattr(exc, "problem", "") or "")
    context = str(getattr(exc, "context", "") or "")
    for shape in _YAML_ERROR_SHAPES:
        if shape.context and shape.context not in context:
            continue
        match = shape.problem.search(problem)
        if match is None:
            continue
        mark = getattr(exc, "problem_mark", None)
        if shape.at_context:
            mark = getattr(exc, "context_mark", None) or mark
        line = mark.line + 1 if mark is not None else None
        captured = match.groupdict()
        explanation = shape.explanation
        return line, explanation.format(**captured) if captured else explanation
    return None


def _source_error(path: Path, code: str, reading: str, line: int | None) -> SourceError:
    location = f"{path}:{line}" if line else str(path)
    return SourceError(f"{location}: {reading}", code, path, line)


def load_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML source, reporting where and how it failed to load.

    Every failure is raised as a SourceError so that a caller collecting
    diagnostics can place it in a report without re-deriving the position from
    the message. Each message opens with that same position, which is what the
    report strips back off when it already shows the location in its own column.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SourceError(
            f"{path}: cannot be read: {exc}", "source.unreadable", path
        ) from exc
    try:
        data = yaml.load(text, Loader=StrictLoader)
    except _Rejected as exc:
        raise _source_error(
            path, "source.rejected-yaml", f"rejected YAML: {exc.explanation}", exc.line
        ) from exc
    except yaml.YAMLError as exc:
        reading = _yaml_error_reading(exc)
        if reading is None:
            raise SourceError(
                f"{path}: invalid YAML: {exc}", "source.invalid-yaml", path
            ) from exc
        line, explanation = reading
        raise _source_error(
            path, "source.invalid-yaml", f"invalid YAML: {explanation}", line
        ) from exc
    if not isinstance(data, dict):
        raise SourceError(
            f"{path}: invalid YAML: the file holds no mapping of fields",
            "source.invalid-yaml",
            path,
        )
    return data


def _yaml_warning(path: Path, line: int, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        severity="warning",
        message=f"{path}:{line}: {message}",
        code=code,
        path=path,
        line=line,
    )


def _plain_value_warnings(path: Path, token: yaml.ScalarToken) -> list[Diagnostic]:
    """Warn when one unquoted value keeps its text but changes meaning on load."""
    line = token.start_mark.line + 1
    value = token.value
    lowered = value.lower()
    if lowered in YAML_AMBIGUOUS_SCALARS:
        return [
            _yaml_warning(
                path,
                line,
                "yaml.ambiguous-scalar",
                f"plain scalar {value!r} may coerce in YAML; quote the value",
            )
        ]
    if value.isdigit() and len(value) > 1 and value.startswith("0"):
        return [
            _yaml_warning(
                path,
                line,
                "yaml.numeric-scalar",
                f"plain numeric scalar {value!r} may lose formatting; quote the value",
            )
        ]
    if YAML_NUMERIC_SCALAR.fullmatch(value) and str(float(value)) != value:
        return [
            _yaml_warning(
                path,
                line,
                "yaml.numeric-scalar",
                f"plain scalar {value!r} parses as the number "
                f"{float(value)!r}; quote the value",
            )
        ]
    if YAML_SEXAGESIMAL_SCALAR.fullmatch(value):
        return [
            _yaml_warning(
                path,
                line,
                "yaml.sexagesimal-scalar",
                f"plain scalar {value!r} may parse as a "
                "sexagesimal number; quote the value",
            )
        ]
    return []


# Tokens after which YAML expects one value: a mapping value, a block sequence
# entry, or a flow sequence's first or later entry. A plain scalar sitting in any
# of these slots can still silently change its own meaning.
_VALUE_SLOT_TOKENS = (
    yaml.ValueToken,
    yaml.BlockEntryToken,
    yaml.FlowSequenceStartToken,
    yaml.FlowEntryToken,
)


def yaml_scalar_warnings(path: Path) -> list[Diagnostic]:
    """Warn about unquoted values YAML reads as something other than their text.

    The loader already refuses every construct that makes a source mean
    something the page does not show. What is left is the value that loads
    exactly as YAML says it should and still surprises its author: `no` as a
    boolean, `1:30` as a number, `08` without its leading zero. Each keeps its
    text on the page, so only a warning beside the line tells the author.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    try:
        tokens = list(yaml.scan(text))
    except yaml.YAMLError:
        return []
    warnings: list[Diagnostic] = []
    for index, token in enumerate(tokens):
        if not isinstance(token, _VALUE_SLOT_TOKENS):
            continue
        value_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if isinstance(value_token, yaml.ScalarToken) and value_token.plain:
            warnings.extend(_plain_value_warnings(path, value_token))
    return warnings
