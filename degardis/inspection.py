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
    shortest_address,
)
from .fingerprint import source_fingerprint
from .model import DegardisError, Diagnostic, Skill
from .package import artifact_mode, executable_paths, openai_metadata
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
        "name, version, title, root, description length, one count per selected "
        "content key, and generated page sizes against their budgets"
    ),
    "identity": (
        "the full description and purpose, license, copyright, and source digest"
    ),
    "sources": "every selected source file, its construct kind, id, and size",
    "tasks": (
        "each task, its recognition cues, its goal, the page it compiles to, and "
        "the pages whose authored text links it"
    ),
    "knowledge": (
        "each knowledge unit, what it requires, and which task pages carry it"
    ),
    "principles": (
        "each principle this skill names, its source, owners, activation "
        "conditions, and the pages whose authored text links it"
    ),
    "guides": (
        "each guide, its activation, the tasks and facets that name it, and the "
        "pages whose authored text links it"
    ),
    "facets": (
        "each facet, its category, its description, and the pages whose authored "
        "text links it"
    ),
    "scripts": (
        "each selected script, its size, and the pages whose authored text links it"
    ),
    "assets": (
        "each selected asset, its size, and the pages whose authored text links it"
    ),
    "composition": (
        "why each task page carries what it carries: direct knowledge, required "
        "knowledge and the page written"
    ),
    "quality": (
        "orphan and near-duplicate knowledge, constraint ratio, "
        "closure duplication, startup bytes, page-budget headroom, and minimum "
        "and maximum read bytes by task"
    ),
    "outputs": "every file a build would write, with size and mode, and their total",
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
    """One skill's inspection, in the shape every report reads.

    A manifest too broken to load leaves no skill and no compilation. It still
    reports every key a compiled skill does: its identity falls back to the
    directory it was found in, and its rows come from a compilation of nothing,
    so each dimension reads as empty rather than absent and the keys are listed
    once for both cases.
    """
    root = inspection.root
    skill = inspection.skill
    compiled = inspection.compiled
    if skill is None or compiled is None:
        skill = None
        compiled = Compiled(
            content=SkillContent(skill=Skill(name=root.name, root=root, manifest={}))
        )
    manifest = skill.manifest if skill is not None else {}
    content = compiled.content
    rendered = compiled.rendered
    generated = rendered.page_texts() if rendered is not None else {}
    linked = _linked_from(compiled)
    tasks = _task_rows(compiled, linked)
    attention = _attention(compiled)
    diagnostics = inspection.diagnostics
    return {
        "name": skill.name if skill is not None else root.name,
        "title": skill.title if skill is not None else root.name,
        "version": skill.version if skill is not None else "",
        "description": skill.description if skill is not None else "",
        "purpose": skill.purpose if skill is not None else "",
        "license": manifest.get("license"),
        "copyright": manifest.get("copyright"),
        "source": root,
        "format_version": manifest.get("format_version"),
        "source_fingerprint": source_fingerprint(
            root, content.selected, content.icon_sources.values()
        ),
        "counts": {key: len(content.files(key)) for key in CONTENT_KEYS},
        "sources": _source_rows(content),
        "tasks": tasks,
        "knowledge": _knowledge_rows(compiled),
        "principles": _principle_rows(compiled, linked),
        "facets": _facet_rows(content, linked),
        "guides": _guide_rows(compiled, linked),
        "scripts": _copied_rows(compiled, "scripts", linked),
        "assets": _copied_rows(compiled, "assets", linked),
        "composition": _composition_rows(compiled),
        "quality": _quality_rows(
            compiled.quality, attention, tasks, _maximum_reads(compiled)
        ),
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


def _task_rows(
    compiled: Compiled, linked: dict[str, list[str]]
) -> list[dict[str, Any]]:
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
            "linked": linked.get(item.page, []),
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


def _linked_from(compiled: Compiled) -> dict[str, list[str]]:
    """Each page an authored link reaches, with every page whose text carries one.

    What the compiler links from a declaration, the root's routes, the facet
    index, and each owner's list, the rows already say. Authored text reaches
    further, and not where it was written: a link in a knowledge unit lands on
    every task page carrying that unit. So the pages are read off what the
    renderer emitted rather than off the sources, and each is named the way an
    owner is, so the two read together as every page that links the target.
    """
    rendered = compiled.rendered
    if rendered is None:
        return {}
    plan = compiled.plan
    names = {
        **{item.page: f"task:{item.id}" for item in plan.tasks},
        **{principle_path(item.id): f"principle:{item.id}" for item in plan.principles},
        **{facet_path(item.id): f"facet:{item.id}" for item in plan.facets},
        **{
            guide_path(identifier): f"guide:{identifier}"
            for identifier in compiled.content.sources.guides
        },
    }
    linked: dict[str, dict[str, None]] = {}
    for link in rendered.links:
        if link.authored:
            linked.setdefault(link.target, {})[names.get(link.page, link.page)] = None
    return {target: list(pages) for target, pages in linked.items()}


def _principle_rows(
    compiled: Compiled, linked: dict[str, list[str]]
) -> dict[str, Any]:
    """Every principle this skill states, with its provenance and its placement.

    The source path is part of the row because a principle is now authored here
    rather than supplied, so the first question about one is which file in this
    skill says it. A placement names its owner and nothing else: a principle has
    one activation wherever it is placed, and the row already states it.
    """
    sources = compiled.content.sources
    root = compiled.content.skill.root
    selected = {item.id for item in compiled.plan.principles}
    placements: dict[str, list[dict[str, str]]] = {}
    for reference in compiled.plan.root_principles:
        placements.setdefault(reference.id, []).append({"owner": ROOT})
    for task in compiled.plan.tasks:
        for reference in task.principles:
            placements.setdefault(reference.id, []).append(
                {"owner": f"task:{task.id}"}
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
                "linked": linked.get(principle_path(name), []),
                "page": principle_path(name) if name in selected else "-",
                "bytes": len(item.body.encode("utf-8")),
            }
            for name, item in sorted(sources.principles.items())
        ],
    }


def _facet_rows(
    content: SkillContent, linked: dict[str, list[str]]
) -> list[dict[str, Any]]:
    return [
        {
            "id": identifier,
            "title": facet.title,
            "category": facet.category,
            "description": facet.description,
            "linked": linked.get(facet_path(identifier), []),
            "bytes": len(facet.body.encode("utf-8")),
        }
        for identifier, facet in sorted(content.sources.facets.items())
    ]


def _copied_rows(
    compiled: Compiled, key: str, linked: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Every file one copied key selects, keyed by the shortest target naming it.

    Nothing declares a script or an asset, so inline references are all that
    reach one. A target may be any trailing part of the file's path, so the id
    is the shortest that names this file and no other one the key selects:
    what an author can write to reference it.
    """
    root = compiled.content.skill.root
    sources = [path.relative_to(root).as_posix() for path in compiled.content.files(key)]
    rows: list[dict[str, Any]] = []
    for path, source in zip(compiled.content.files(key), sources):
        page = copied_path(key, source)
        rows.append(
            {
                "id": shortest_address(source, sources),
                "path": source,
                "linked": linked.get(page, []),
                "bytes": _size(path),
            }
        )
    return rows


def _guide_rows(
    compiled: Compiled, linked: dict[str, list[str]]
) -> list[dict[str, Any]]:
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
            "linked": linked.get(guide_path(identifier), []),
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
    quality: Quality,
    attention: dict[str, Any],
    tasks: list[dict[str, Any]],
    maximum_reads: dict[str, int],
) -> dict[str, Any]:
    """Add per-load costs to quality without treating the root as optional.

    A run always loads SKILL.md, then it deliberately opens exactly one task
    page. Startup bytes and each task's minimum read therefore come from the
    rendered files rather than source-file sizes.

    Headroom is the tightest remaining margin across every page held to a
    one-load budget, so it goes negative exactly when some page draws a budget
    warning. A kind of page the bundle does not ship has no margin at all,
    rather than the whole of its budget: counting an absent kind would let a
    smaller budget than the root's stand in for pages that do not exist.
    """
    startup_bytes = attention["root_bytes"]
    headroom = min(
        [
            attention["root_budget"] - startup_bytes,
            *(
                attention[f"{kind}_budget"] - attention[f"largest_{kind}_bytes"]
                for kind in ("task", "principle", "guide", "facet")
                if attention[f"{kind}_pages"]
            ),
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
        "maximum_read_bytes_by_task": maximum_reads,
    }


def _maximum_reads(compiled: Compiled) -> dict[str, int]:
    """The most one run of each task can be directed to read, in bytes.

    A run reads the root, copies the register, opens its task page, and reads
    the facet index; every principle, guide, and facet page it may go on to open
    is linked from one of those, or from a page reached the same way. The root
    links every task page, and a run that opens another task's page has changed
    task, so no other task page is followed. Each page counts once however many
    links reach it, and only generated pages count: a copied script or asset is
    run or used where it is linked, not read as guidance.
    """
    rendered = compiled.rendered
    if rendered is None:
        return {}
    texts = rendered.page_texts()
    addresses = compiled.content.addresses
    edges: dict[str, set[str]] = {}
    for link in rendered.links:
        edges.setdefault(link.page, set()).add(link.target)
    # The index names every facet by a link the renderer does not record as a
    # reference, because it is written from the facets rather than from a body.
    edges.setdefault(addresses.facet_index, set()).update(
        facet_path(item.id) for item in compiled.plan.facets
    )
    task_pages = {item.page for item in compiled.plan.tasks}
    opening = [
        page
        for page in (ROOT, addresses.register, addresses.facet_index)
        if page in texts
    ]
    reads: dict[str, int] = {}
    for item in compiled.plan.tasks:
        reached: set[str] = set()
        pending = [*opening, item.page]
        while pending:
            page = pending.pop()
            if page in reached or page not in texts:
                continue
            if page in task_pages and page != item.page:
                continue
            reached.add(page)
            pending.extend(edges.get(page, ()))
        reads[item.id] = sum(len(texts[page].encode("utf-8")) for page in reached)
    return reads


def _attention(compiled: Compiled) -> dict[str, Any]:
    """What one load of each generated page costs, against the budget it is held to."""
    rendered = compiled.rendered
    pages = rendered.pages if rendered is not None else {}
    root_text = rendered.skill_text if rendered is not None else ""

    def size(page: str) -> int:
        return len(pages.get(page, "").encode("utf-8"))

    task_sizes = [size(item.page) for item in compiled.plan.tasks]
    principle_sizes = [
        size(principle_path(item.id)) for item in compiled.plan.principles
    ]
    guide_sizes = [
        size(guide_path(guide.id))
        for guide in compiled.content.sources.guides.values()
    ]
    facet_sizes = [size(facet_path(item.id)) for item in compiled.plan.facets]
    facet_index_bytes = size(compiled.content.addresses.facet_index)
    return {
        "root_bytes": len(root_text.encode("utf-8")),
        "root_lines": len(root_text.splitlines()),
        "register_bytes": size(compiled.content.addresses.register),
        "task_pages": len(task_sizes),
        "task_bytes": sum(task_sizes),
        "largest_task_bytes": max(task_sizes, default=0),
        "average_task_bytes": (
            round(sum(task_sizes) / len(task_sizes)) if task_sizes else 0
        ),
        "principle_pages": len(principle_sizes),
        "principle_bytes": sum(principle_sizes),
        "largest_principle_bytes": max(principle_sizes, default=0),
        "guide_pages": len(guide_sizes),
        "guide_bytes": sum(guide_sizes),
        "largest_guide_bytes": max(guide_sizes, default=0),
        "facet_pages": len(facet_sizes),
        "facet_bytes": facet_index_bytes + sum(facet_sizes),
        "facet_index_bytes": facet_index_bytes,
        "largest_facet_bytes": max(facet_sizes, default=0),
        "root_budget": ROOT_BUDGET_BYTES,
        "task_budget": TASK_BUDGET_BYTES,
        "principle_budget": PRINCIPLE_BUDGET_BYTES,
        "guide_budget": GUIDE_BUDGET_BYTES,
        "facet_budget": FACET_BUDGET_BYTES,
    }


def _output_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    if rendered is None:
        return []
    content = compiled.content
    root = content.skill.root
    executable = executable_paths(root, content.selected)
    rows: list[dict[str, Any]] = [
        {
            "path": ROOT,
            "bytes": len(rendered.skill_text.encode("utf-8")),
            "mode": artifact_mode(ROOT, executable),
        }
    ]
    for relative, page in sorted(rendered.pages.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(page.encode("utf-8")),
                "mode": artifact_mode(relative, executable),
            }
        )
    for key in COPIED_CONTENT_KEYS:
        for path in content.files(key):
            relative = copied_path(key, path.relative_to(root).as_posix())
            rows.append(
                {
                    "path": relative,
                    "bytes": _size(path),
                    "mode": artifact_mode(relative, executable),
                }
            )
    for relative, data in sorted(content.icon_assets.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(data),
                "mode": artifact_mode(relative, executable),
            }
        )
    metadata = openai_metadata(
        content.skill.interface, content.icon_addresses, content.skill.name
    )
    rows.append(
        {
            "path": OPENAI_METADATA,
            "bytes": len(metadata.encode("utf-8")),
            "mode": artifact_mode(OPENAI_METADATA, executable),
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
