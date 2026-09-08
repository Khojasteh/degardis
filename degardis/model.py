"""The values every other module passes around: findings, failures, and identity.

Nothing here knows a source schema. What it holds is the vocabulary the rest of
the compiler reports in — one finding, a collection of findings that never stops
at the first, and the failure a command raises when it cannot produce a report at
all — plus the manifest identity a skill is loaded as.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dexpr import Binding, parse_binding


CURRENT_FORMAT_VERSION = 2

# The outcome the compiler owns. Every workflow returns it when a binding check
# cannot be satisfied, so a source may neither declare it nor map it.
BLOCKED_OUTCOME = "blocked"


def filename_title(stem: str) -> str:
    """The human-readable default title for a source filename stem."""
    return stem.replace("-", " ").title()


class DegardisError(ValueError):
    """Any failure the compiler reports to whoever ran it.

    A failure raised instead of collected still belongs to a check, so it may
    carry that check's code. Without one, a caller who hits it has the message
    and nothing to look up: `degardis explain` needs a code. The code stays
    optional because most of these failures are one-offs no check names.
    """

    def __init__(self, message: object, code: str = "") -> None:
        super().__init__(str(message))
        self.code = code


class SourceError(DegardisError):
    """A source file that cannot be read, with where it failed and which check.

    Reading a file is the one failure that happens before any check runs, so the
    reader is the only part of the compiler that knows which of the source checks
    applies and which line to point at. Carrying both on the error keeps that
    knowledge with the failure instead of leaving each caller to guess it.
    """

    def __init__(
        self,
        message: object,
        code: str,
        path: Path | None = None,
        line: int | None = None,
    ) -> None:
        super().__init__(message, code)
        self.path = path
        self.line = line


@dataclass(frozen=True)
class Diagnostic:
    """One problem, with the location and check an agent needs to act on it."""

    severity: str
    message: str
    code: str = ""
    path: Path | None = None
    line: int | None = None

    @property
    def key(self) -> tuple:
        return (self.severity, self.code, self.path, self.line, self.message)

    @property
    def coded(self) -> str:
        """The message with its check code appended, the way a report spells one.

        A reader holding the message still needs the code to look the check up,
        so the two travel together wherever a finding is rendered as a single
        string: the validation report's numbered lines, and the errors a raise
        carries when it stands in for a report.
        """
        return f"{self.message} ({self.code})" if self.code else self.message

    def location(self, root: Path | None = None) -> str:
        """Render the source position, relative to root where possible."""
        if self.path is None:
            return "-"
        text = self.path.as_posix()
        if root is not None:
            try:
                text = self.path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                pass
        return f"{text}:{self.line}" if self.line else text

    def summary(self, skill_name: str = "") -> str:
        """Strip the prefix the message repeats from its own location."""
        text = self.message
        prefixes = [f"{skill_name}: "] if skill_name else []
        if self.path is not None:
            prefixes.append(f"{self.path}: ")
            if self.line:
                prefixes.append(f"{self.path}:{self.line}: ")
        for prefix in sorted(prefixes, key=len, reverse=True):
            if text.startswith(prefix):
                return text[len(prefix) :]
        return text


@dataclass
class Diagnostics:
    """Collects every problem found in one run instead of stopping at the first."""

    records: list[Diagnostic] = field(default_factory=list)

    def _append(self, record: Diagnostic) -> None:
        """Keep one record per distinct finding, whichever path reported it.

        The same problem reaches a collector more than once — a file read by two
        checks, a warning gathered by both the loader and the inspection — and a
        reader acting on a report needs each finding once. Identity is the whole
        of what a reader sees, so `Diagnostic.key` decides it.
        """
        if all(existing.key != record.key for existing in self.records):
            self.records.append(record)

    def _add(
        self,
        severity: str,
        message: object,
        code: str,
        path: Path | None,
        line: int | None,
    ) -> None:
        self._append(
            Diagnostic(
                severity=severity,
                message=str(message),
                code=code,
                path=path,
                line=line,
            )
        )

    def error(
        self,
        message: object,
        code: str = "",
        path: Path | None = None,
        line: int | None = None,
    ) -> None:
        self._add("error", message, code, path, line)

    def warning(
        self,
        message: object,
        code: str = "",
        path: Path | None = None,
        line: int | None = None,
    ) -> None:
        self._add("warning", message, code, path, line)

    def source_failure(self, exc: Exception, path: Path, code: str) -> None:
        """Record one source that could not be read, as the reader described it.

        A SourceError already knows the check it failed and the line it failed
        on, so both are taken from it. Any other failure carrying a code keeps
        it too: the code the raiser named is more precise than the one the
        caller expected, and replacing it would send the reader to look up a
        check that is not the one that refused their source. `code` is the
        fallback for a failure no check named at all.
        """
        if isinstance(exc, SourceError):
            self.error(exc, exc.code, exc.path or path, exc.line)
            return
        found = getattr(exc, "code", "")
        self.error(exc, found or code, path)

    def add_errors(
        self,
        messages: Iterable[object],
        code: str = "",
        path: Path | None = None,
    ) -> None:
        for message in messages:
            self.error(message, code, path)

    def add_warnings(
        self,
        messages: Iterable[object],
        code: str = "",
        path: Path | None = None,
    ) -> None:
        for message in messages:
            self.warning(message, code, path)

    def add(self, records: Iterable[Diagnostic]) -> None:
        for record in records:
            self._append(record)

    def select(self, severity: str) -> list[Diagnostic]:
        return [record for record in self.records if record.severity == severity]

    @property
    def errors(self) -> list[str]:
        return [record.message for record in self.select("error")]

    @property
    def warnings(self) -> list[str]:
        return [record.message for record in self.select("warning")]

    @property
    def failed(self) -> bool:
        return any(record.severity == "error" for record in self.records)

    def raise_if_errors(self) -> None:
        """Raise what was collected, keeping each finding's check code with it.

        A caller who hits the raise needs the same `degardis explain CODE` a
        report offers, so a lone error carries its code on the exception for
        `main` to append, and a run of them spells each code inline because one
        exception has room for only one.
        """
        records = self.select("error")
        if not records:
            return
        if len(records) == 1:
            raise DegardisError(records[0].message, records[0].code)
        body = "\n".join(f"  - {record.coded}" for record in records)
        raise DegardisError(f"{len(records)} errors:\n{body}")


def ensure_within(path: Path, root: Path, label: str) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise DegardisError(
            f"{label} must stay within {resolved_root}: {path}"
        ) from exc


@dataclass(frozen=True)
class Entrypoint:
    """One route into the skill, chosen before any workflow runs.

    An entrypoint is activation identity rather than content: `when` is the
    sentence an agent matches the request against, and `target` names the
    workflow the run enters at that workflow's own entry.

    A route with no `when` is taken whatever the request says, which is what
    makes it the route taken when no other matched, and why the manifest allows
    it only in last place. Nothing marks it as such: position is the whole of
    what says so, so there is no second field to disagree with the absent one.

    `supplied` is here because the value a route hands its target is part of
    that activation identity: two routes may enter one workflow at the same
    entry node, and what each supplied is the only thing that tells the run
    which way in it came. A binding is carried as parsed rather than as raw
    YAML so the renderer states one the way every other supplied value is
    stated; the checks that hold it against the target's declared inputs still
    read the manifest mapping, where the key that failed is there to name.
    """

    id: str
    target: str
    when: str = ""
    supplied: tuple[tuple[str, Binding], ...] = ()


@dataclass(frozen=True)
class Skill:
    """One manifest, as identity rather than as content.

    Everything a command needs before any source file is parsed lives here: the
    name a bundle is written under, the description a host selects the skill by,
    and the interface metadata a target renders. The constructs the manifest
    selects are resolved separately, because a manifest that names a missing
    workflow is still a manifest whose identity a report can name.
    """

    name: str
    root: Path
    manifest: dict[str, Any]

    @property
    def title(self) -> str:
        """The skill's human-readable name, as the interface declares it.

        There is one display name in a manifest, not two: `interface.display_name`
        is what a host labels the skill with, and the generated `SKILL.md` heading
        and every report say the same thing. A manifest that declares no usable
        one is reported under `interface.missing-display_name`; the name-derived
        value here only keeps a report renderable while that failure is on its way
        to the reader, and is never an authoring option.
        """
        display_name = self.interface.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name
        return self.name.replace("-", " ").title()

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", "0.0.0"))

    @property
    def format_version(self) -> int:
        return int(self.manifest["format_version"])

    @property
    def description(self) -> str:
        return str(self.manifest.get("description", ""))

    def _optional_string(self, field_name: str) -> str | None:
        value = self.manifest.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise DegardisError(
                f"{self.name}: {field_name} must be a non-empty string"
            )
        return value

    @property
    def license(self) -> str | None:
        return self._optional_string("license")

    @property
    def copyright(self) -> str | None:
        return self._optional_string("copyright")

    @property
    def entrypoints(self) -> tuple[Entrypoint, ...]:
        """The declared routes, in the order the manifest declares them.

        Declaration order is priority order: the first entrypoint whose
        discriminator matches the request is the one taken. Nothing here sorts
        or deduplicates, because either would change which route a run takes
        rather than only how the manifest reads.

        A malformed entry is skipped rather than refused. A report can name a
        skill whose manifest is wrong, and the checks that refuse one read the
        raw mapping, where the key that failed is still there to name. A
        binding that will not parse is skipped the same way, and for the same
        reason: `entrypoint.invalid-with` names it from the mapping, and a
        route that kept an unreadable value would carry it into the document.
        """
        declared = self.manifest.get("entrypoints")
        if not isinstance(declared, dict):
            return ()
        found: list[Entrypoint] = []
        for identifier, body in declared.items():
            if not isinstance(identifier, str) or not isinstance(body, dict):
                continue
            target = body.get("target")
            when = body.get("when")
            supplied = body.get("with")
            bindings: list[tuple[str, Binding]] = []
            if isinstance(supplied, dict):
                for name, item in supplied.items():
                    binding, _ = parse_binding(item)
                    if isinstance(name, str) and binding is not None:
                        bindings.append((name, binding))
            found.append(
                Entrypoint(
                    id=identifier,
                    target=target if isinstance(target, str) else "",
                    when=when if isinstance(when, str) else "",
                    supplied=tuple(bindings),
                )
            )
        return tuple(found)

    @property
    def roots(self) -> tuple[str, ...]:
        """Every workflow a run can enter, once each, in declaration order.

        Two entrypoints may target one workflow — that is how a skill offers
        several modes of one job — so the reachability walk takes the targets
        deduplicated while the routing table keeps both rows.
        """
        return tuple(
            dict.fromkeys(item.target for item in self.entrypoints if item.target)
        )

    @property
    def default_entrypoint(self) -> Entrypoint | None:
        """The route taken when no discriminator matched, where one is declared.

        It is the last route, and only when that route states no condition of
        its own. A skill may state one on every route instead, and an unmatched
        request then has nowhere to go: the rendered table says so by returning
        `blocked` rather than by falling through to whichever route came last.
        """
        routes = self.entrypoints
        return routes[-1] if routes and not routes[-1].when else None

    @property
    def interface(self) -> dict[str, Any]:
        value = self.manifest.get("interface", {})
        return value if isinstance(value, dict) else {}

    def bound(self, key: str) -> list[str]:
        """The construct identifiers the manifest binds for the complete run."""
        value = self.manifest.get(key)
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]
