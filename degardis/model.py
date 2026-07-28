from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from textwrap import TextWrapper
from typing import Any

import yaml


SUPPORTED_FORMAT_VERSIONS = frozenset({1})


class DegardisError(ValueError):
    pass


class DegardisWarning(UserWarning):
    pass


def ensure_within(path: Path, root: Path, label: str) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise DegardisError(
            f"{label} must stay within {resolved_root}: {path}"
        ) from exc


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DegardisError(f"Cannot read YAML {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DegardisError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DegardisError(f"Expected mapping in {path}")
    return data


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
    def description(self) -> str:
        return str(self.data["description"])

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
        frontmatter = yaml.safe_dump(
            {"name": self.name, "description": self.description},
            sort_keys=False,
            width=1000,
        ).strip()
        lines = [f"---\n{frontmatter}\n---", "", f"# {self.title}", ""]
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
