"""Shared fixtures and helpers for the compiler test suite.

Two conventions this module exists to make easy, because both are about where a
test takes its expected value from.

A test asserts a behavior, a value, or a check code — never the wording of a
diagnostic, which is editorial and carries no contract: pinning it fails on
every reword and passes while the check itself is broken. Assert the code, from
`diagnostic_codes` or `codes` below, from the `(code)` the validate report
appends, or from `error.code` on a raised failure. Report rows, summary lines,
and help text are the exception: those are contract, and `tests/test_cli.py`
asserts them as they are.

A source field is read as the text on the page. `on:` is a step field, not the
boolean `true`, so anything constructing YAML for a test loads it back through
`degardis.yamlsource.StrictLoader` — which is what `edit_yaml` below does —
rather than through PyYAML's default loader.
"""

from __future__ import annotations

import shutil
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from degardis.model import Diagnostics, Skill
from degardis.registry import load_skill_path
from degardis.validate import compile_skill, inspect_skills
from degardis.yamlsource import StrictLoader


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
        FIXTURES, root, ignore=shutil.ignore_patterns("__pycache__", "*.py[co]")
    )
    return root


def write_raster_icon(
    path: Path, color: tuple[int, int, int, int], *, format_name: str = "PNG"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 192), color)
    if format_name == "ICO":
        image = Image.new("RGBA", (256, 256), color)
        image.save(path, format=format_name, sizes=[(32, 32), (128, 128), (256, 256)])
    else:
        image.save(path, format=format_name)


@contextmanager
def edit_yaml(path: Path) -> Iterator[dict]:
    """Load one YAML source, hand it over to be changed, and write it back.

    A fixture edit is read as UTF-8 and written with `sort_keys=False`, so the
    file keeps the key order its author gave it and a check that reports a line
    number still points where the test expects. Reach for this rather than
    spelling the round trip again, so what a test changed is the only thing its
    body has to say.

    The compiler's own loader reads the file, because PyYAML's safe loader
    would resolve a field named `on` to the boolean true and the round trip
    would silently delete a call step's outcome mapping.
    """
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
    yield data
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def alpha(root: Path) -> Path:
    return root / "alpha"


def set_content_patterns(root: Path, skill_name: str, **patterns: list[str]) -> None:
    with edit_yaml(root / skill_name / "skill.yaml") as data:
        data.setdefault("content", {}).update(patterns)


def set_interface_fields(root: Path, skill_name: str, **fields: str) -> None:
    with edit_yaml(root / skill_name / "skill.yaml") as data:
        data["interface"].update(fields)


def edit_workflow(root: Path, skill_name: str, workflow: str):
    return edit_yaml(root / skill_name / "workflows" / f"{workflow}.yaml")


def diagnostic_codes(result: dict, severity: str) -> set[str]:
    """Return the public diagnostic codes emitted at one severity."""
    return {
        record.code
        for record in result["diagnostics"]
        if record.severity == severity
    }


def inspect_one(path: Path, **kwargs: Any) -> dict:
    """Inspect one skill directory, returning its single result dictionary."""
    return inspect_skills([path], **kwargs)[0]


def codes(path: Path, severity: str = "error") -> set[str]:
    """The codes one skill directory reports at one severity."""
    return diagnostic_codes(inspect_one(path), severity)


def compiled(path: Path) -> tuple[Skill, Any, Diagnostics]:
    """Compile one skill directly, for a test that needs the lowered graph."""
    skill = load_skill_path(path)
    diagnostics = Diagnostics()
    return skill, compile_skill(skill, diagnostics), diagnostics


def lowered_nodes(path: Path) -> dict[str, Any]:
    """Every generated node of one skill, keyed by its node label."""
    _, result, _ = compiled(path)
    assert result.lowered is not None
    return {node.label: node for node in result.lowered.all_nodes()}
