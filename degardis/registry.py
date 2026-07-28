from __future__ import annotations

import re
from pathlib import Path

from .model import (
    DegardisError,
    Profile,
    Skill,
    ensure_within,
    load_yaml,
)


class SkillRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def names(self) -> list[str]:
        return sorted(
            path.parent.name for path in self.root.glob("*/skill.yaml")
        )

    def load(self, name: str) -> Skill:
        path = self.root / name / "skill.yaml"
        if not path.exists():
            raise DegardisError(f"Unknown skill: {name}")
        manifest = load_yaml(path)
        manifest_name = str(manifest.get("name", ""))
        if manifest_name != name:
            raise DegardisError(
                f"Skill directory {name} does not match manifest name "
                f"{manifest_name or '<missing>'}"
            )
        return Skill(name=name, root=path.parent, manifest=manifest)

    def profile_owners(self) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = {}
        for skill_name in self.names():
            skill = self.load(skill_name)
            for profile in load_skill_profiles(skill):
                owners.setdefault(profile.name, []).append(skill_name)
        return {
            name: sorted(values) for name, values in sorted(owners.items())
        }


def available_skills(root: Path) -> list[str]:
    return SkillRepository(root).names()


def load_skill(root: Path, name: str) -> Skill:
    return SkillRepository(root).load(name)


def load_skill_path(root: Path) -> Skill:
    path = root / "skill.yaml"
    if not path.is_file():
        raise DegardisError(f"Missing skill manifest: {path}")
    manifest = load_yaml(path)
    name = str(manifest.get("name", ""))
    if not name:
        raise DegardisError(f"Missing skill name: {path}")
    if root.name != name:
        raise DegardisError(
            f"Skill directory {root.name} does not match manifest name {name}"
        )
    return Skill(name=name, root=root, manifest=manifest)


def discover_skill_paths(sources: list[Path] | tuple[Path, ...]) -> list[Path]:
    discovered: list[Path] = []
    for source in sources:
        path = source.resolve()
        if not path.is_dir():
            raise DegardisError(f"Skill path is not a directory: {path}")
        if (path / "skill.yaml").is_file():
            candidates = [path]
        else:
            candidates = _discover_skill_directories(path)
            if not candidates:
                raise DegardisError(f"No skills found inside: {path}")
        for candidate in candidates:
            if candidate not in discovered:
                discovered.append(candidate)

    names: dict[str, Path] = {}
    for path in discovered:
        skill = load_skill_path(path)
        previous = names.get(skill.name)
        if previous and previous != path:
            raise DegardisError(
                f"Duplicate skill name {skill.name}: {previous}, {path}"
            )
        names[skill.name] = path
    return discovered


def _discover_skill_directories(root: Path) -> list[Path]:
    """Find descendant skills without treating their contents as collections."""
    discovered: list[Path] = []
    pending = [root]
    visited: set[Path] = set()
    while pending:
        directory = pending.pop()
        resolved = directory.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        children = sorted(
            (
                child.resolve()
                for child in directory.iterdir()
                if child.is_dir()
            ),
            reverse=True,
        )
        for child in children:
            if (child / "skill.yaml").is_file():
                discovered.append(child)
            else:
                pending.append(child)
    return sorted(discovered)


def profile_source_paths(skill: Skill) -> list[Path]:
    config = skill.manifest.get("profiles", {})
    if not isinstance(config, dict):
        raise DegardisError(f"{skill.name}: profiles must be a mapping")
    directory_value = config.get("directory", "profiles")
    if not isinstance(directory_value, str) or not directory_value.strip():
        raise DegardisError(
            f"{skill.name}: profiles.directory must be a non-empty string"
        )
    directory = skill.root / directory_value
    ensure_within(directory, skill.root, f"{skill.name}: profile directory")
    return sorted(directory.glob("*.yaml"))


def load_profile(
    path: Path,
    skill_name: str,
    skill_root: Path | None = None,
) -> Profile:
    if path.suffix != ".yaml":
        raise DegardisError(f"Unsupported profile source: {path}")

    data = load_yaml(path)
    allowed = {
        "name",
        "label",
        "description",
        "instructions",
        "details",
        "details_files",
    }
    unknown = set(data) - allowed
    if unknown:
        raise DegardisError(
            f"{path}: unsupported profile fields: {', '.join(sorted(unknown))}"
        )
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DegardisError(f"{path}: name must be a non-empty string")
    if name != path.stem:
        raise DegardisError(f"{path}: profile name must match filename")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise DegardisError(f"{path}: description must be a non-empty string")
    label = data.get("label")
    if not isinstance(label, str) or not label.strip():
        raise DegardisError(f"{path}: label must be a non-empty string")
    instructions = data.get("instructions")
    if (
        not isinstance(instructions, list)
        or not instructions
        or any(not isinstance(item, str) or not item.strip() for item in instructions)
    ):
        raise DegardisError(
            f"{path}: instructions must be a non-empty list of strings"
        )
    details = data.get("details")
    if details is not None and not isinstance(details, str):
        raise DegardisError(f"{path}: details must be a string")
    details_files = data.get("details_files")
    if details_files is not None and (
        not isinstance(details_files, list)
        or not details_files
        or any(
            not isinstance(item, str) or not item.strip()
            for item in details_files
        )
    ):
        raise DegardisError(
            f"{path}: details_files must be a non-empty list of strings"
        )
    if details is not None and details_files is not None:
        raise DegardisError(
            f"{path}: details and details_files are mutually exclusive"
        )
    appended_details = str(details or "")
    if details_files:
        allowed_root = (skill_root or path.parent).resolve()
        chunks: list[str] = []
        for detail_file in details_files:
            source = (path.parent / detail_file).resolve()
            try:
                source.relative_to(allowed_root)
            except ValueError as exc:
                raise DegardisError(
                    f"{path}: detail files must stay within the skill directory"
                ) from exc
            if source.suffix != ".md":
                raise DegardisError(
                    f"{path}: detail files must reference Markdown files"
                )
            if not source.is_file():
                raise DegardisError(f"{path}: detail file not found: {detail_file}")
            chunks.append(source.read_text(encoding="utf-8").strip())
        appended_details = "\n\n".join(chunks)
    appended_details = appended_details.replace("\r\n", "\n").replace("\r", "\n")
    if _contains_level_one_heading(appended_details):
        raise DegardisError(f"{path}: details must not contain a level-one heading")
    return Profile(
        path=path,
        data=data,
        skill=skill_name,
        appended_details=appended_details,
    )


def _contains_level_one_heading(markdown: str) -> bool:
    fence_character: str | None = None
    fence_length = 0
    for line in markdown.splitlines():
        candidate = line[0:3].lstrip() + line[3:] if line.startswith(" ") else line
        fence = re.match(r"^(`{3,}|~{3,})", candidate)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None and re.match(r"^ {0,3}#(?:[ \t]|$)", line):
            return True
    return False


def load_skill_profiles(skill: Skill) -> list[Profile]:
    config = skill.manifest.get("profiles", {})
    if not isinstance(config, dict):
        raise DegardisError(f"{skill.name}: profiles must be a mapping")
    return [
        load_profile(path, skill.name, skill.root)
        for path in profile_source_paths(skill)
    ]


def available_profile_owners(root: Path) -> dict[str, list[str]]:
    return SkillRepository(root).profile_owners()
