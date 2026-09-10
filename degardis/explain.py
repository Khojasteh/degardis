"""What each check code means, for a reader who has the package but not its source.

Every diagnostic carries a code and one line of message. The line is enough to
locate the problem; it is not enough to decide whether the problem matters, or
what the source should say instead. The table answers both, and is written by
hand rather than derived from the checks: a check knows the condition it tests,
not why an author should care.

That makes the table prose, so it lives in data beside this module rather than
in it. `explain_codes/` holds one file per code, named for the code it explains,
so the directory listing is the vocabulary itself and no catalog can disagree
with it. Sentences a family of codes shares are stated once in
`explain_wording.yaml`, which a code file names and supplies the values for.
This module reads that data and prints nothing of its own.

A code is `<namespace>.<check>`, and the check reads as hyphenated words with one
exception: where it names a field of the source, it spells that field exactly as
the key does. `interface.missing-short_description` and
`interface.short_description-length` both carry `short_description` because the
manifest key is `short_description`. A reader who knows the key can therefore
build the code rather than look it up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from textwrap import fill

import yaml

from .model import CURRENT_FORMAT_VERSION


CODES_DIR = "explain_codes"
WORDING = "explain_wording.yaml"

CODE_NAME = re.compile(r"[a-z][a-z0-9]*\.[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*")
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

EXAMPLE_FIELDS = ("failing", "passing")
STATED_FIELDS = ("trigger", "impact", *EXAMPLE_FIELDS)


@dataclass(frozen=True)
class CheckExplanation:
    """One check code, in the terms an author or agent has to act on."""

    trigger: str
    impact: str
    failing: str
    passing: str


def _resource(*parts: str) -> str:
    return files("degardis").joinpath(*parts).read_text(encoding="utf-8")


@cache
def _versions() -> dict[str, str]:
    """The versions an explanation may name, none of which it states itself.

    Each is derived from the version the check enforces, so a printed example
    cannot drift from the format `validate` accepts.
    """
    return {
        "format_version": str(CURRENT_FORMAT_VERSION),
        "older_format_version": str(CURRENT_FORMAT_VERSION - 1),
        "newer_format_version": str(CURRENT_FORMAT_VERSION + 1),
    }


@cache
def _code_names() -> tuple[str, ...]:
    """Every explainable code, taken from the names of the files explaining them.

    The filename is the code, so this answers which codes exist without reading
    one of them. The CLI states the count in its help and lists them on an
    unrecognized code, so both run on every invocation; neither pays for prose
    it will not print.
    """
    codes = []
    for entry in files("degardis").joinpath(CODES_DIR).iterdir():
        if not entry.name.endswith(".yaml"):
            continue
        code = entry.name[: -len(".yaml")]
        if not CODE_NAME.fullmatch(code):
            raise ValueError(f"{CODES_DIR}/{entry.name} is not named for a check code.")
        codes.append(code)
    if not codes:
        raise ValueError(f"{CODES_DIR}/ holds no check code.")
    return tuple(sorted(codes))


@cache
def _wording() -> dict[str, dict[str, str]]:
    return yaml.safe_load(_resource(WORDING))


def _supplied(wording: dict[str, str]) -> set[str]:
    """The placeholders a wording leaves for the code file to fill.

    A wording may also name a version, which this module supplies, so those are
    not the code file's to state.
    """
    names: set[str] = set()
    for text in wording.values():
        names.update(PLACEHOLDER.findall(text))
    return names - set(_versions())


def _fill(text: str, values: dict[str, str], where: str) -> str:
    """Substitute by name, and refuse a placeholder nothing supplies.

    A misspelled placeholder would otherwise reach a reader verbatim, as the
    instruction to read something the data never stated.
    """
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", value)
    left = PLACEHOLDER.search(text)
    if left:
        raise ValueError(f"{where} states the unknown placeholder {left.group()}.")
    return text


@cache
def _read(code: str) -> CheckExplanation:
    """Read one code's explanation, resolving the wording it names.

    A code file states its own four fields or names a wording and supplies that
    wording's values; the fields it must carry follow from which it does, so a
    file cannot half-state an entry and leave a reader a blank trigger.
    """
    where = f"{CODES_DIR}/{code}.yaml"
    data = yaml.safe_load(_resource(CODES_DIR, f"{code}.yaml"))
    if not isinstance(data, dict):
        raise ValueError(f"{where} does not state a mapping.")

    named = data.get("wording")
    if named is None:
        prose = {label: data.get(label, "") for label in ("trigger", "impact")}
        expected = set(STATED_FIELDS)
        values = {}
    else:
        wording = _wording().get(named)
        if wording is None:
            raise ValueError(f"{where} names the unknown wording {named!r}.")
        prose = dict(wording)
        supplied = _supplied(wording)
        expected = {"wording", *EXAMPLE_FIELDS, *supplied}
        values = {name: str(data.get(name, "")) for name in supplied}

    missing = sorted(expected - set(data))
    unknown = sorted(set(data) - expected)
    if missing:
        raise ValueError(f"{where} states no {', '.join(missing)}.")
    if unknown:
        raise ValueError(f"{where} states the unknown field {', '.join(unknown)}.")

    values.update(_versions())
    return CheckExplanation(
        trigger=_fill(prose["trigger"], values, where),
        impact=_fill(prose["impact"], values, where),
        **{label: _fill(data[label], values, where) for label in EXAMPLE_FIELDS},
    )


def explanation(code: str) -> CheckExplanation | None:
    """The rule for one check code, or None when the code is not known.

    A code is matched against the listing before its file is read, so a name
    that is not a code — `../cli`, say — never reaches the filesystem.
    """
    if code not in _code_names():
        return None
    return _read(code)


def checks() -> dict[str, CheckExplanation]:
    """Every explanation, for a caller that has to see the whole table at once."""
    return {code: _read(code) for code in _code_names()}


def known_codes() -> list[str]:
    return list(_code_names())


def codes_by_namespace() -> dict[str, list[str]]:
    """Known codes grouped by the construct their namespace names."""
    grouped: dict[str, list[str]] = {}
    for code in known_codes():
        namespace, _, name = code.partition(".")
        grouped.setdefault(namespace, []).append(name)
    return grouped


def known_codes_message() -> str:
    """List every explainable code, one namespace at a time, for an error path.

    The naming rule comes first. A reader who reached this list guessed a code,
    and the rule is what makes the next guess right without reading the list.
    """
    lines = [
        "A code is <namespace>.<check>, hyphenated, except where the check names "
        "a field of",
        "the source, which it spells exactly as the key does: "
        "interface.short_description-length.",
        "",
        "Known check codes:",
    ]
    for namespace, names in codes_by_namespace().items():
        codes = ", ".join(f"{namespace}.{name}" for name in names)
        lines.extend(
            fill(
                codes,
                width=100,
                initial_indent="  ",
                subsequent_indent="  ",
                break_long_words=False,
                break_on_hyphens=False,
            ).splitlines()
        )
    return "\n".join(lines)
