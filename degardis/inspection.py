"""The one inspection result every report reads.

`inspect_skills` compiles each selected skill once, through `validate.py`, and
returns one dictionary per skill. `validate`, the `inspect` line report, and
`build` all read that same dictionary, so the three cannot disagree about what a
source contains or about which findings it has.

The rows below are that dictionary's shape, and the shape is an interface —
`output.py` renders it, and `inspect` prints it for an agent that has the CLI and
nothing else. A row spelled two ways disagrees in silence, because the reader of
the missing key sees a field that was never filled rather than a failure. So each
dimension's rows are built in one place here, and a source too broken to compile
reports the same keys as one that did compile.

Nothing here decides whether a source is valid. Every finding it carries was
collected by the checks in `validate.py`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .analysis import Quality
from .bundlepaths import (
    OPENAI_METADATA,
    FACET_INDEX,
    ROOT,
    copied_path,
    guide_path,
    principle_path,
    facet_path,
)
from .content import (
    CONTENT_KEYS,
    COPIED_CONTENT_KEYS,
    PARSED_CONTENT_KEYS,
)
from .fingerprint import source_fingerprint
from .model import DegardisError, Diagnostic, Diagnostics, Skill
from .package import artifact_mode, openai_metadata
from .progress import Progress
from .registry import discover_skill_paths
from .render import (
    PRINCIPLE_BUDGET_BYTES,
    FACET_BUDGET_BYTES,
    GUIDE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    TASK_BUDGET_BYTES,
)
from .sources import (
    KNOWLEDGE_KINDS,
)
from .validate import Compiled, Inspection, SkillContent, compile_all


# --------------------------------------------------------------------------
# The inspect dimensions
# --------------------------------------------------------------------------


INSPECT_DIMENSIONS: dict[str, str] = {
    "skill": (
        "name, version, title, root, description length, generated page sizes, "
        "and one count per selected content key"
    ),
    "identity": (
        "the full description and purpose, license, copyright, and source digest"
    ),
    "sources": "every selected source file, its construct kind, id, and size",
    "tasks": (
        "each task, its recognition cues, its goal, and the page it compiles to"
    ),
    "knowledge": (
        "each knowledge unit, what it requires, and which task pages carry it"
    ),
    "principles": (
        "each principle this skill names, its source, owners, and activation conditions"
    ),
    "guides": (
        "each guide, its activation, and the tasks and facets that name it"
    ),
    "facets": "each facet, its category, and its description",
    "composition": (
        "why each task page carries what it carries: direct knowledge, required "
        "knowledge and the page written"
    ),
    "quality": (
        "orphan and near-duplicate knowledge, constraint ratio, "
        "closure duplication, startup bytes, page-budget headroom, and one-load "
        "bytes by task"
    ),
    "outputs": "every file a build would write, with size and mode",
    "diagnostics": "aggregated errors and warnings",
}
DEFAULT_INSPECT_DIMENSIONS: tuple[str, ...] = (
    "skill",
    "tasks",
    "principles",
    "diagnostics",
)


def describe_inspect_dimensions() -> str:
    width = max(len(name) for name in INSPECT_DIMENSIONS)
    return "".join(
        f"  {name:<{width}}  {text}\n" for name, text in INSPECT_DIMENSIONS.items()
    )


def select_inspect_dimensions(dimensions: list[str] | None) -> tuple[str, ...]:
    if not dimensions:
        return DEFAULT_INSPECT_DIMENSIONS
    requested = [*dimensions, "skill"]
    unknown = sorted({name for name in requested if name not in INSPECT_DIMENSIONS})
    if unknown:
        raise DegardisError(
            f"unknown dimensions: {', '.join(unknown)}; the dimensions are "
            f"{', '.join(INSPECT_DIMENSIONS)}"
        )
    return tuple(name for name in INSPECT_DIMENSIONS if name in set(requested))


# --------------------------------------------------------------------------
# The inspection result
# --------------------------------------------------------------------------


def inspect_skills(
    skill_paths: Iterable[Path],
    *,
    body_pages: Sequence[str] = (),
    progress: Progress | None = None,
) -> list[dict[str, Any]]:
    return [
        result_dict(inspection, body_pages=body_pages)
        for inspection in compile_all(skill_paths, progress)
    ]


def result_dict(
    inspection: Inspection, *, body_pages: Sequence[str] = ()
) -> dict[str, Any]:
    if inspection.skill is None or inspection.compiled is None:
        return _unreadable_result(inspection.root, inspection.diagnostics)
    return _result_dict(
        inspection.skill,
        inspection.compiled,
        inspection.diagnostics,
        body_pages=body_pages,
    )


def _attention_row(
    *,
    root_text: str = "",
    task_sizes: Sequence[int] = (),
    principle_sizes: Sequence[int] = (),
    guide_sizes: Sequence[int] = (),
    facet_sizes: Sequence[int] = (),
    facet_index_bytes: int = 0,
) -> dict[str, Any]:
    """What one load of each generated page costs, against the budget it is held to.

    A source too broken to compile still reports this row, so the shape is
    stated once here rather than once for a compiled skill and again for an
    unreadable one.
    """
    return {
        "root_bytes": len(root_text.encode("utf-8")),
        "root_lines": len(root_text.splitlines()),
        "task_pages": len(task_sizes),
        "task_bytes": sum(task_sizes),
        "largest_task_bytes": max(task_sizes, default=0),
        "average_task_bytes": (
            round(sum(task_sizes) / len(task_sizes)) if task_sizes else 0
        ),
        "principle_bytes": sum(principle_sizes),
        "largest_principle_bytes": max(principle_sizes, default=0),
        "guide_bytes": sum(guide_sizes),
        "largest_guide_bytes": max(guide_sizes, default=0),
        "facet_bytes": facet_index_bytes + sum(facet_sizes),
        "largest_facet_bytes": max(facet_sizes, default=0),
        "root_budget": ROOT_BUDGET_BYTES,
        "task_budget": TASK_BUDGET_BYTES,
        "principle_budget": PRINCIPLE_BUDGET_BYTES,
        "guide_budget": GUIDE_BUDGET_BYTES,
        "facet_budget": FACET_BUDGET_BYTES,
    }


def _unreadable_result(root: Path, diagnostics: Diagnostics) -> dict[str, Any]:
    return {
        "name": root.name,
        "title": root.name,
        "version": "",
        "description": "",
        "purpose": "",
        "license": None,
        "copyright": None,
        "source": root,
        "format_version": None,
        "source_fingerprint": source_fingerprint(root, {}),
        "counts": dict.fromkeys(CONTENT_KEYS, 0),
        "sources": [],
        "tasks": [],
        "knowledge": [],
        "principles": {
            "selected": [],
            "states": [],
        },
        "facets": [],
        "composition": [],
        "quality": _quality_rows(Quality(), _attention_row(), []),
        "attention": _attention_row(),
        "outputs": [],
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "pages": [],
        "page_text": {},
    }


def _result_dict(
    skill: Skill,
    compiled: Compiled,
    diagnostics: Diagnostics,
    *,
    body_pages: Sequence[str],
) -> dict[str, Any]:
    content = compiled.content
    rendered = compiled.rendered
    generated = rendered.page_texts() if rendered is not None else {}
    text = rendered.skill_text if rendered is not None else ""
    tasks = _task_rows(compiled)
    attention = _attention(compiled, text)
    return {
        "name": skill.name,
        "title": skill.title,
        "version": skill.version,
        "description": skill.description,
        "purpose": skill.purpose,
        "license": skill.manifest.get("license"),
        "copyright": skill.manifest.get("copyright"),
        "source": skill.root,
        "format_version": skill.manifest.get("format_version"),
        "source_fingerprint": source_fingerprint(skill.root, content.selected),
        "counts": {key: len(content.files(key)) for key in CONTENT_KEYS},
        "sources": _source_rows(content),
        "tasks": tasks,
        "knowledge": _knowledge_rows(compiled),
        "principles": _principle_rows(compiled),
        "facets": _facet_rows(content),
        "guides": _guide_rows(compiled),
        "composition": _composition_rows(compiled),
        "quality": _quality_rows(compiled.quality, attention, tasks),
        "attention": attention,
        "outputs": _output_rows(compiled),
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "pages": list(generated),
        "page_text": {
            page: generated[page] for page in body_pages if page in generated
        },
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _source_rows(content: SkillContent) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = content.skill.root
    for key in CONTENT_KEYS:
        store = content.sources.kind(key) if key in PARSED_CONTENT_KEYS else {}
        by_path = {construct.path: construct for construct in store.values()}
        for path in content.files(key):
            construct = by_path.get(path)
            rows.append(
                {
                    "kind": (
                        construct.kind
                        if key == "knowledge" and construct is not None
                        else key
                    ),
                    "id": construct.id if construct is not None else "",
                    "path": path.relative_to(root).as_posix(),
                    "bytes": _size(path),
                }
            )
    return rows


def _task_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    return [
        {
            "id": item.id,
            "title": item.task.title,
            "goal": item.task.goal,
            "recognize": list(item.task.recognize),
            "page": item.page,
            "bytes": rendered.page_bytes(item.page) if rendered else 0,
            "knowledge": len(item.closure),
            "guides": list(item.task.guides),
            "principles": [
                {"id": principle.id, "activation": principle.activation}
                for principle in item.principles
            ],
        }
        for item in compiled.plan.tasks
    ]


def _knowledge_rows(compiled: Compiled) -> list[dict[str, Any]]:
    carriers: dict[str, list[str]] = {}
    for item in compiled.plan.tasks:
        for unit in item.closure:
            carriers.setdefault(unit.key, []).append(item.id)
    return [
        {
            "key": key,
            "kind": unit.kind,
            "id": unit.id,
            "title": unit.title,
            "requires": list(unit.requires),
            "tasks": carriers.get(key, []),
            "bytes": len(unit.body.encode("utf-8")),
        }
        for key, unit in sorted(compiled.content.sources.knowledge.items())
    ]


def _principle_rows(compiled: Compiled) -> dict[str, Any]:
    """Every principle this skill states, with its provenance and its placement.

    The source path is part of the row because a principle is now authored here
    rather than supplied, so the first question about one is which file in this
    skill says it.
    """
    sources = compiled.content.sources
    root = compiled.content.skill.root
    selected = {item.id for item in compiled.plan.principles}
    placements: dict[str, list[dict[str, str]]] = {}
    for reference in compiled.plan.root_principles:
        placements.setdefault(reference.id, []).append(
            {"owner": ROOT, "activation": reference.activation}
        )
    for task in compiled.plan.tasks:
        for reference in task.principles:
            placements.setdefault(reference.id, []).append(
                {"owner": f"task:{task.id}", "activation": reference.activation}
            )
    return {
        "selected": [item.id for item in compiled.plan.principles],
        "states": [
            {
                "id": name,
                "title": item.title,
                "path": item.path.relative_to(root).as_posix(),
                "selected": name in selected,
                "activation": item.activation,
                "placements": placements.get(name, []),
                "page": principle_path(name) if name in selected else "-",
                "bytes": len(item.body.encode("utf-8")),
            }
            for name, item in sorted(sources.principles.items())
        ],
    }


def _facet_rows(content: SkillContent) -> list[dict[str, Any]]:
    return [
        {
            "id": identifier,
            "title": facet.title,
            "category": facet.category,
            "description": facet.description,
            "bytes": len(facet.body.encode("utf-8")),
        }
        for identifier, facet in sorted(content.sources.facets.items())
    ]


def _guide_rows(compiled: Compiled) -> list[dict[str, Any]]:
    """Every guide, with the tasks and facets that open it.

    An owner is qualified, the way a principle's placements are, because two
    kinds of owner now name guides and a bare id would not say which reached
    this one. A guide reached only from a facet would otherwise report no owner
    at all, which reads as a guide nothing uses.
    """
    root = compiled.content.skill.root
    owners: dict[str, list[dict[str, str]]] = {
        identifier: [] for identifier in compiled.content.sources.guides
    }
    for item in compiled.plan.tasks:
        for identifier in item.task.guides:
            if identifier in owners:
                owners[identifier].append({"owner": f"task:{item.id}"})
    for facet in compiled.plan.facets:
        for identifier in facet.guides:
            if identifier in owners:
                owners[identifier].append({"owner": f"facet:{facet.id}"})
    return [
        {
            "id": identifier,
            "title": guide.title,
            "activation": guide.activation,
            "path": guide.path.relative_to(root).as_posix(),
            "owners": owners[identifier],
            "bytes": len(guide.body.encode("utf-8")),
        }
        for identifier, guide in sorted(compiled.content.sources.guides.items())
    ]


def _composition_rows(compiled: Compiled) -> list[dict[str, Any]]:
    """Why each page carries what it carries, for the author asking exactly that."""
    return [
        {
            "id": item.id,
            "direct": list(item.direct),
            "required": list(item.required),
            "groups": [
                {"kind": kind, "knowledge": [unit.id for unit in item.of_kind(kind)]}
                for kind in KNOWLEDGE_KINDS
                if item.of_kind(kind)
            ],
            "page": item.page,
        }
        for item in compiled.plan.tasks
    ]


def _quality_rows(
    quality: Quality, attention: dict[str, Any], tasks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Add per-load costs to quality without treating the root as optional.

    A run always loads SKILL.md, then it deliberately opens exactly one task
    page. Startup bytes and each task's minimum read therefore come from the
    rendered files rather than source-file sizes. Headroom is the tightest
    remaining margin among those two independently enforced page budgets.
    """
    startup_bytes = attention["root_bytes"]
    headroom = min(
        [
            attention["root_budget"] - startup_bytes,
            *(attention["task_budget"] - task["bytes"] for task in tasks),
        ]
    )
    return {
        "tasks": quality.tasks,
        "knowledge_units": quality.knowledge_units,
        "orphan_knowledge": list(quality.orphan_knowledge),
        "near_duplicates": [
            {"left": left, "right": right, "similarity": similarity}
            for left, right, similarity in quality.near_duplicates
        ],
        "constraint_ratio": quality.constraint_ratio,
        "principles": quality.principles,
        "duplicated_bytes": quality.duplicated_bytes,
        "unique_bytes": quality.unique_bytes,
        "headroom": headroom,
        "startup_bytes": startup_bytes,
        "minimum_read_bytes_by_task": {
            task["id"]: startup_bytes + task["bytes"] for task in tasks
        },
    }


def _attention(compiled: Compiled, text: str) -> dict[str, Any]:
    rendered = compiled.rendered
    pages = rendered.pages if rendered is not None else {}

    def size(page: str) -> int:
        return len(pages.get(page, "").encode("utf-8"))

    return _attention_row(
        root_text=text,
        task_sizes=[size(item.page) for item in compiled.plan.tasks],
        principle_sizes=[
            size(principle_path(item.id)) for item in compiled.plan.principles
        ],
        guide_sizes=[
            size(guide_path(guide.id))
            for guide in compiled.content.sources.guides.values()
        ],
        facet_sizes=[size(facet_path(item.id)) for item in compiled.plan.facets],
        facet_index_bytes=size(FACET_INDEX),
    )


def _output_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    if rendered is None:
        return []
    content = compiled.content
    root = content.skill.root
    rows: list[dict[str, Any]] = [
        {
            "path": ROOT,
            "bytes": len(rendered.skill_text.encode("utf-8")),
            "mode": artifact_mode(ROOT),
        }
    ]
    for relative, page in sorted(rendered.pages.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(page.encode("utf-8")),
                "mode": artifact_mode(relative),
            }
        )
    for key in COPIED_CONTENT_KEYS:
        for path in content.files(key):
            relative = copied_path(key, path.relative_to(root).as_posix())
            rows.append(
                {
                    "path": relative,
                    "bytes": _size(path),
                    "mode": artifact_mode(relative),
                }
            )
    for relative, data in sorted(content.icon_assets.items()):
        rows.append(
            {"path": relative, "bytes": len(data), "mode": artifact_mode(relative)}
        )
    metadata = openai_metadata(
        content.skill.interface, set(content.icon_sources), content.skill.name
    )
    rows.append(
        {
            "path": OPENAI_METADATA,
            "bytes": len(metadata.encode("utf-8")),
            "mode": artifact_mode(OPENAI_METADATA),
        }
    )
    return sorted(rows, key=lambda row: row["path"])


def promote_warnings(results: list[dict[str, Any]]) -> None:
    """Report every warning as an error, without changing which checks ran."""
    for result in results:
        records: list[Diagnostic] = []
        for record in result["diagnostics"]:
            records.append(
                Diagnostic(
                    severity="error",
                    message=record.message,
                    code=record.code,
                    path=record.path,
                    line=record.line,
                )
                if record.severity == "warning"
                else record
            )
        result["diagnostics"] = records
        result["errors"] = [
            record.message for record in records if record.severity == "error"
        ]
        result["warnings"] = []


def validate(paths: Path | list[Path]) -> list[str]:
    """Every error one or more skills report, for an embedded caller."""
    sources = [paths] if isinstance(paths, Path) else list(paths)
    results = inspect_skills(discover_skill_paths(sources))
    return [message for result in results for message in result["errors"]]
