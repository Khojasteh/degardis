"""Shared fixtures and helpers for the compiler test suite.

Three conventions this module exists to make easy, because all three are about
where a test takes its expected value from.

A test asserts a behavior, a value, or a check code — never the wording of a
diagnostic, which is editorial and carries no contract: pinning it fails on
every reword and passes while the check itself is broken. Assert the code, from
`diagnostic_codes` or `codes` below, from the `(code)` the validate report
appends, or from `error.code` on a raised failure. Report rows, summary lines,
and help text are the exception: those are contract, and `tests/test_cli.py`
asserts them as they are.

Generated prose is the same kind of value, and its one owner is
`degardis.wording`. A test that needs a heading or a lead the compiler writes
names the constant rather than repeating what it currently says, so rewording
that constant stays one file to edit rather than a suite to chase. What the
test is actually asserting is the structure around it — the heading depth, the
link syntax, the order two sections appear in — and that stays literal. A field
the author wrote is read back from its source file through `field_of`, for the
same reason.

A source field is read as the text on the page. `on:` is a field name, not the
boolean `true`, so anything constructing YAML for a test loads it back through
`degardis.yamlsource.StrictLoader` — which is what `edit_yaml` and
`edit_frontmatter` below do — rather than through PyYAML's default loader.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import yaml
from PIL import Image

from degardis.cli import main
from degardis.inspection import inspect_skills
from degardis.markdown import read_markdown
from degardis.model import Diagnostics, Skill
from degardis.registry import load_skill_path
from degardis.validate import compile_skill
from degardis.yamlsource import StrictLoader


REPO_ROOT = Path(__file__).resolve().parents[1]
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "skills" / "demo"
CANONICAL_EXAMPLE = REPO_ROOT / "examples" / "structured-summary"


class Terminal(io.StringIO):
    """A stream that claims to be a terminal, which is the only thing checked."""

    encoding = "utf-8"

    def isatty(self) -> bool:
        return True


def run(*argv: str, columns: int | None = None) -> tuple[int, str, str]:
    """Run the CLI in process, returning its exit status, stdout, and stderr.

    With `columns`, both streams are terminals of that width, which is what
    decides where person-facing text wraps; without it they are redirected. A
    terminal is always a colored one, where the interpreter colors help at all,
    so a run does not depend on the color settings of the shell running tests.
    """
    if columns is None:
        stdout, stderr = io.StringIO(), io.StringIO()
        environment: dict[str, str] = {}
    else:
        stdout, stderr = Terminal(), Terminal()
        environment = {"COLUMNS": str(columns), "PYTHON_COLORS": "1"}
    with (
        mock.patch.dict(os.environ, environment),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            status = main(list(argv))
        except SystemExit as exit:
            # Help and usage errors leave through argparse rather than `main`.
            status = exit.code
    return status, stdout.getvalue(), stderr.getvalue()


def words(text: str) -> list[str]:
    """Text as its sequence of words, so a rewrap can be compared with its source.

    A quote marker is left out: rewrapping a quote repeats it on every line it
    now spans, which moves no word the author wrote.
    """
    return [word for word in visible(text).split() if word != ">"]


def visible(text: str) -> str:
    """Text as a terminal shows it, without the escape sequences that color it.

    They occupy bytes and no columns, so a width is measured without them.
    """
    return ANSI_ESCAPE.sub("", text)


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


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under one directory, keyed by its path, for an unchanged check.

    A command that reads a source must leave it exactly as it found it, and
    comparing names alone would let a rewrite in place pass. Bytecode is left
    out because importing a fixture script writes it and that is not the
    command under test.
    """
    return {
        entry.relative_to(root).as_posix(): entry.read_bytes()
        for entry in sorted(root.rglob("*"))
        if entry.is_file() and "__pycache__" not in entry.parts
    }


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
    """
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
    yield data
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@contextmanager
def edit_frontmatter(path: Path) -> Iterator[dict]:
    """Change one Markdown source's fields, leaving its body exactly as it was.

    The body is prose a test almost never cares about, and rewriting it would
    make every frontmatter edit also a content edit. So the body is read as text
    and written back unchanged, and only the fields round-trip through YAML.
    """
    source = read_markdown(path)
    fields = dict(source.fields)
    yield fields
    front = yaml.safe_dump(fields, sort_keys=False).strip("\n")
    path.write_text(
        f"---\n{front}\n---\n\n{source.body}\n", encoding="utf-8", newline="\n"
    )


def field_of(path: Path, name: str) -> str:
    """One frontmatter field, read from the source file that owns it.

    A test whose expected value is the author's takes it from the author's file
    rather than repeating it as a literal. A second spelling in the test is a
    copy that can disagree with the fixture, and re-titling a fixture or
    rephrasing its activation would fail the test without any compiler change.
    """
    return str(read_markdown(path).fields[name])


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_source(path: Path, fields: str, body: str = "Body text.") -> None:
    """Write one Markdown source from its frontmatter text and its body."""
    write_text(path, f"---\n{fields.strip()}\n---\n\n{body}\n")


def alpha(root: Path) -> Path:
    return root / "alpha"


def task_path(root: Path, skill_name: str, task: str) -> Path:
    return root / skill_name / "tasks" / f"{task}.md"


def set_content_patterns(root: Path, skill_name: str, **patterns: list[str]) -> None:
    with edit_yaml(root / skill_name / "skill.yaml") as data:
        data.setdefault("content", {}).update(patterns)


def set_interface_fields(root: Path, skill_name: str, **fields: str) -> None:
    with edit_yaml(root / skill_name / "skill.yaml") as data:
        data["interface"].update(fields)


def diagnostic_codes(result: dict, severity: str) -> set[str]:
    """The codes one inspection result reports at one severity."""
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
    """Compile one skill directly, for a test that needs the plan or the pages."""
    skill = load_skill_path(path)
    diagnostics = Diagnostics()
    return skill, compile_skill(skill, diagnostics), diagnostics


def pages(path: Path) -> dict[str, str]:
    """Every generated page of one skill, keyed by its path in the bundle."""
    _, result, _ = compiled(path)
    assert result.rendered is not None
    return result.rendered.page_texts()
