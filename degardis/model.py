from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from textwrap import TextWrapper
from typing import Any, Iterable


SUPPORTED_FORMAT_VERSIONS = frozenset({1})


class DegardisError(ValueError):
    pass


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
        super().__init__(str(message))
        self.code = code
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

    def _add(
        self,
        severity: str,
        message: object,
        code: str,
        path: Path | None,
        line: int | None,
    ) -> None:
        record = Diagnostic(
            severity=severity,
            message=str(message),
            code=code,
            path=path,
            line=line,
        )
        if all(existing.key != record.key for existing in self.records):
            self.records.append(record)

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
        on, so both are taken from it; anything else is recorded under the code
        the caller expected.
        """
        if isinstance(exc, SourceError):
            self.error(exc, exc.code, exc.path or path, exc.line)
            return
        self.error(exc, code, path)

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
            if all(existing.key != record.key for existing in self.records):
                self.records.append(record)

    def select(self, severity: str) -> list[Diagnostic]:
        return [record for record in self.records if record.severity == severity]

    @property
    def errors(self) -> list[str]:
        return [record.message for record in self.select("error")]

    @property
    def warnings(self) -> list[str]:
        return [record.message for record in self.select("warning")]

    def merge(self, other: "Diagnostics") -> None:
        self.add(other.records)

    def raise_if_errors(self) -> None:
        errors = self.errors
        if not errors:
            return
        if len(errors) == 1:
            raise DegardisError(errors[0])
        body = "\n".join(f"  - {error}" for error in errors)
        raise DegardisError(f"{len(errors)} errors:\n{body}")


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
class Entry:
    path: Path
    data: dict[str, Any]
    skill: str

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def title(self) -> str:
        return str(self.data.get("title", self.id))

    @property
    def kind(self) -> str:
        return str(self.data.get("kind", "rule"))

    @property
    def priority(self) -> int:
        return int(self.data.get("priority", 100))


@dataclass(frozen=True)
class Profile:
    path: Path
    data: dict[str, Any]
    skill: str
    appended_details: str = ""

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def description(self) -> str | None:
        description = self.data.get("description")
        return None if description is None else str(description)

    @property
    def title(self) -> str:
        return self.label

    @property
    def filename(self) -> str:
        return f"{self.name}.md"

    @property
    def label(self) -> str:
        return str(self.data["label"])

    @property
    def text(self) -> str:
        lines = [f"# {self.title}", ""]
        wrapper = TextWrapper(
            width=100,
            initial_indent="- ",
            subsequent_indent="  ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        for instruction in self.data["instructions"]:
            lines.extend(wrapper.wrap(instruction))
        details = self.appended_details.strip()
        if details:
            lines.extend(["", details])
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class Skill:
    name: str
    root: Path
    manifest: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.manifest.get("title", self.name.replace("-", " ").title()))

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
    def primary_workflow(self) -> str:
        return str(self.manifest.get("primary_workflow", ""))

    @property
    def interface(self) -> dict[str, Any]:
        value = self.manifest.get("interface", {})
        return value if isinstance(value, dict) else {}


@dataclass
class SkillContent:
    skill: Skill
    entries: list[Entry] = field(default_factory=list)
    workflows: list[dict[str, Any]] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    scripts: list[Path] = field(default_factory=list)
    assets: list[Path] = field(default_factory=list)
    icon_sources: dict[str, Path] = field(default_factory=dict)


@dataclass
class SkillBundle:
    primary: Skill
    contents: list[SkillContent]

    @property
    def requested(self) -> str:
        return self.primary.name

    def content(self, skill_name: str) -> SkillContent:
        for item in self.contents:
            if item.skill.name == skill_name:
                return item
        raise DegardisError(f"Skill {skill_name} is not resolved for {self.primary.name}")

    @property
    def resolved_names(self) -> list[str]:
        return [item.skill.name for item in self.contents]
