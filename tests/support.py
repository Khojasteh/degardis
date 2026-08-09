"""Shared fixtures and helpers for the compiler test suite."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import yaml
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "skills" / "demo"
CANONICAL_EXAMPLE = REPO_ROOT / "examples" / "structured-summary"


def zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def zip_text(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def folder_names(path: Path) -> set[str]:
    return {
        entry.relative_to(path).as_posix()
        for entry in path.rglob("*")
        if entry.is_file()
    }


def folder_text(path: Path, name: str) -> str:
    return (path / name).read_text(encoding="utf-8")


def copy_skills(destination: Path) -> Path:
    """Copy the fixture skills, without any bytecode a local run left behind.

    Running the fixture scripts writes `__pycache__` beside them. Leaving it out
    keeps a copied tree identical whether or not that has happened, so a test
    that cares about bytecode creates its own.
    """
    root = destination / "demo"
    shutil.copytree(
        FIXTURES,
        root,
        ignore=shutil.ignore_patterns("__pycache__", "*.py[co]"),
    )
    return root


def write_raster_icon(
    path: Path,
    color: tuple[int, int, int, int],
    *,
    format_name: str = "PNG",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 192), color)
    if format_name == "ICO":
        image = Image.new("RGBA", (256, 256), color)
        image.save(
            path,
            format=format_name,
            sizes=[(32, 32), (128, 128), (256, 256)],
        )
    else:
        image.save(path, format=format_name)


def set_content_patterns(root: Path, skill_name: str, **patterns: list[str]) -> None:
    source = root / skill_name / "skill.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data.setdefault("content", {}).update(patterns)
    source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def set_interface_fields(root: Path, skill_name: str, **fields: str) -> None:
    source = root / skill_name / "skill.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data["interface"].update(fields)
    source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def diagnostic_codes(result: dict, severity: str) -> set[str]:
    """Return the public diagnostic codes emitted at one severity."""
    return {
        record.code
        for record in result["diagnostics"]
        if record.severity == severity
    }

