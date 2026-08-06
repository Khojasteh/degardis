"""Read a YAML source file, and report what YAML did to the text in it.

Two failures live here. A file that does not parse at all is raised as a
DegardisError carrying the line and a plain-language reading of the parser's
own complaint. A file that parses but whose text YAML quietly rewrote - a
value consumed as an anchor, a tag, or a comment, or one coerced to a boolean
or a number - is reported as warnings the caller collects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .model import Diagnostic, SourceError


YAML_AMBIGUOUS_SCALARS = {
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "null",
    "~",
    ".nan",
    ".inf",
    "-.inf",
}

YAML_NUMERIC_SCALAR = re.compile(r"^-?\d+\.\d+$")
YAML_SEXAGESIMAL_SCALAR = re.compile(r"^-?\d+(?::[0-5]?\d)+$")


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
    # A local tag, which is what an unquoted content exclusion becomes. PyYAML
    # only complains once construction reaches it, so the reading has to name the
    # tag: the line holds a pattern, and nothing about it looks like YAML syntax.
    _YamlErrorShape(
        problem=re.compile(
            r"^could not determine a constructor for the tag "
            r"'(?P<tag>![^']*)'$"
        ),
        explanation=(
            "a value that begins with ! is read as a YAML type tag rather than "
            "as text, so {tag} is not the value; quote the value"
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
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        reading = _yaml_error_reading(exc)
        if reading is None:
            raise SourceError(
                f"{path}: invalid YAML: {exc}", "source.invalid-yaml", path
            ) from exc
        line, explanation = reading
        location = f"{path}:{line}" if line else str(path)
        raise SourceError(
            f"{location}: invalid YAML: {explanation}",
            "source.invalid-yaml",
            path,
            line,
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


def _duplicate_key_warnings(path: Path, text: str) -> list[Diagnostic]:
    """Warn about repeated mapping keys, which YAML resolves by silent override."""
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return []
    warnings: list[Diagnostic] = []
    pending = [root] if root is not None else []
    while pending:
        node = pending.pop()
        if isinstance(node, yaml.MappingNode):
            seen: set[str] = set()
            for key_node, value_node in node.value:
                key = str(getattr(key_node, "value", ""))
                if key in seen:
                    warnings.append(
                        _yaml_warning(
                            path,
                            key_node.start_mark.line + 1,
                            "yaml.duplicate-key",
                            f"duplicate key {key!r} silently overrides "
                            "the earlier value",
                        )
                    )
                seen.add(key)
                pending.append(value_node)
        elif isinstance(node, yaml.SequenceNode):
            pending.extend(node.value)
    return sorted(warnings, key=lambda record: record.message)


def _plain_value_warnings(
    path: Path, token: yaml.ScalarToken
) -> list[Diagnostic]:
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
# of these slots can still silently lose or change its text.
_VALUE_SLOT_TOKENS = (
    yaml.ValueToken,
    yaml.BlockEntryToken,
    yaml.FlowSequenceStartToken,
    yaml.FlowEntryToken,
)

# Tokens that open a collection. An author who wrote one chose YAML structure
# over a plain value, so the source in that slot is not a scalar to compare.
_COLLECTION_START_TOKENS = (
    yaml.BlockMappingStartToken,
    yaml.BlockSequenceStartToken,
    yaml.FlowMappingStartToken,
    yaml.FlowSequenceStartToken,
)

# Tokens that occupy a value slot's source without being the text an author
# wrote there, and what each does with that text. A token type missing from this
# table still reports, under the generic label: the check finds the loss by
# comparing source against tokens, so it needs no list of the ways to cause one.
_CONSUMING_TOKEN_LABELS: tuple[tuple[type, str], ...] = (
    (yaml.AnchorToken, "consumed as an anchor name"),
    (yaml.AliasToken, "resolved as an alias reference"),
    (yaml.TagToken, "consumed as a type tag"),
)
_CONSUMING_TOKEN_TYPES = tuple(token_type for token_type, _ in _CONSUMING_TOKEN_LABELS)
_CONSUMED_AS_SYNTAX = "consumed as YAML syntax"


def _consuming_label(token: yaml.Token | None) -> str:
    for token_type, label in _CONSUMING_TOKEN_LABELS:
        if isinstance(token, token_type):
            return label
    return _CONSUMED_AS_SYNTAX


def _line_start(mark: yaml.Mark) -> int:
    return mark.index - mark.column


def _source_span(text: str, start: int, boundary: int | None) -> str:
    """The source from start to the end of its line, or to an earlier boundary.

    A boundary keeps a flow collection's later entries out of one entry's span,
    where the end of the line is not the end of the value.
    """
    while start < len(text) and text[start] in " \t":
        start += 1
    end = text.find("\n", start)
    if end < 0:
        end = len(text)
    if boundary is not None and start <= boundary < end:
        end = boundary
    return text[start:end].rstrip()


def _value_tokens(
    tokens: list[yaml.Token], index: int
) -> tuple[yaml.ScalarToken | None, yaml.Token | None]:
    """The scalar YAML read for one value slot, and the token after that value.

    Anchors, tags, and aliases stand inside the slot's source without carrying
    the author's text, so the value is the first token past them - a scalar, or
    nothing when YAML read no scalar there at all.
    """
    for offset in range(index, len(tokens)):
        token = tokens[offset]
        if isinstance(token, _CONSUMING_TOKEN_TYPES):
            continue
        following = tokens[offset + 1] if offset + 1 < len(tokens) else None
        if isinstance(token, yaml.ScalarToken):
            return token, following
        return None, token
    return None, None


def _altered_scalar_warning(
    path: Path, text: str, tokens: list[yaml.Token], index: int
) -> Diagnostic | None:
    """Warn when the source in one value slot is not the value YAML read there.

    One comparison stands in for every construct that can quietly rewrite an
    unquoted value: the source the author wrote in the slot, against the source
    YAML actually read as the value. Whatever explains a difference - an anchor,
    an alias, a tag, a comment, or a construct this compiler has never seen -
    took text the entry was meant to carry.
    """
    slot = tokens[index]
    in_slot = tokens[index + 1] if index + 1 < len(tokens) else None
    scalar, after = _value_tokens(tokens, index + 1)

    def warn(line: int, message: str) -> Diagnostic:
        return _yaml_warning(path, line, "yaml.altered-scalar", message)

    def boundary_of(token: yaml.Token | None, mark: yaml.Mark) -> int | None:
        if token is None or token.start_mark.line != mark.line:
            return None
        return token.start_mark.index

    if scalar is None:
        # YAML read no scalar in the slot: either the value is a collection the
        # author wrote deliberately, or the source there became something else.
        if isinstance(in_slot, _COLLECTION_START_TOKENS):
            return None
        written = _source_span(
            text, slot.end_mark.index, boundary_of(after, slot.end_mark)
        )
        if not written:
            return None
        if written.startswith("#"):
            return warn(
                slot.start_mark.line + 1,
                "plain scalar follows an inline comment marker, so YAML reads no "
                "value here; quote the value",
            )
        return warn(
            slot.start_mark.line + 1,
            f"plain scalar {written!r} is {_consuming_label(in_slot)} instead of "
            "the value; quote the value",
        )

    if not scalar.plain:
        return None
    # The source written in the slot, against the source read as the value. Both
    # are the value's own line, so a plain scalar that folds over several lines
    # compares only where the two can differ.
    written = _source_span(
        text,
        max(slot.end_mark.index, _line_start(scalar.start_mark)),
        boundary_of(after, scalar.end_mark),
    )
    span = text[scalar.start_mark.index : scalar.end_mark.index]
    read = span.split("\n", 1)[0].rstrip()
    if written == read:
        return None
    line = scalar.start_mark.line + 1
    taken = written[: written.find(read)].strip() if read in written else written
    if not taken:
        return warn(
            line, "plain scalar contains an inline comment marker; quote the value"
        )
    return warn(
        line,
        f"plain scalar begins with {taken!r}; it is {_consuming_label(in_slot)} "
        "instead of the value; quote the value",
    )


def yaml_scalar_warnings(path: Path) -> list[Diagnostic]:
    """Warn about YAML that can silently give an entry an unexpected value."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    warnings: list[Diagnostic] = _duplicate_key_warnings(path, text)
    try:
        tokens = list(yaml.scan(text))
    except yaml.YAMLError:
        return warnings
    for index, token in enumerate(tokens):
        if not isinstance(token, _VALUE_SLOT_TOKENS):
            continue
        altered = _altered_scalar_warning(path, text, tokens, index)
        if altered is not None:
            warnings.append(altered)
        value_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if isinstance(value_token, yaml.ScalarToken) and value_token.plain:
            warnings.extend(_plain_value_warnings(path, value_token))
    return warnings
