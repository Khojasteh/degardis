"""Every check the compiler runs, and the one inspection result each report reads.

`inspect_skills` compiles each selected skill once and returns one dictionary per
skill. `validate`, the `inspect` line report, and `build` all read that same
dictionary, so the three cannot disagree about what a source contains or about
which findings it has. Anything that checks a source belongs in `_inspect_skill`
rather than on one output path.

The checks fall into three groups. Reading and schema checks are delegated to the
modules that own them — the loader, the manifest reader, the construct readers,
and the graph builder. Relation checks live here: whether every declared
reference names a construct of the right kind, whether every bound binding item
reached the execution graph, and whether every protocol frame can close in an
accepting state. Render checks are delegated to the renderer, which is the only
part that knows which text it put in an execution-bearing role.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .content import (
    CONTENT_KEYS,
    COPIED_CONTENT_KEYS,
    PARSED_CONTENT_KEYS,
    content_files,
)
from .fingerprint import source_fingerprint
from .graph import WorkflowGraph, build_graph, call_order
from .icons import IconError, render_icon_assets, resolve_icon_sources
from .lowering import Frame, LoweredSkill, Lowerer, Node
from .model import (
    DegardisError,
    Diagnostic,
    Diagnostics,
    Skill,
)
from .package import artifact_mode, openai_metadata
from .registry import check_manifest, discover_skill_paths, load_skill_path
from .render import (
    MODULE_BUDGET_BYTES,
    ROOT_BUDGET_BYTES,
    BundleContent,
    RenderedBundle,
    render_skill,
)
from .sources import (
    CONSTRUCT_LABELS,
    CONSTRUCT_READERS,
    SourceSet,
)
from .yamlsource import load_yaml, yaml_scalar_warnings


# What one construct kind is stored under, keyed by the manifest content key
# that selected it. The key decides the schema, so nothing infers a kind from a
# directory name.
CONSTRUCT_KINDS: tuple[str, ...] = PARSED_CONTENT_KEYS

# The node forms a `during` invariant cannot attach to. Each states a choice
# rather than an action, so there is no command for an invariant to sit beside.
INVARIANT_REFUSING_FORMS: frozenset[str] = frozenset({"decision", "gate", "branch"})

INSPECT_DIMENSIONS: dict[str, str] = {
    "skill": (
        "name, version, title, root, description length, primary workflow, and "
        "selected construct counts"
    ),
    "identity": "the full description, license, copyright, and source digest",
    "sources": "every selected source file, its construct kind, id, and size",
    "workflows": (
        "each reachable workflow, the call that reaches it, its source steps, "
        "its lowered nodes, and its entry command"
    ),
    "execution": "every lowered node, its kind, its source, and its transitions",
    "lowering": (
        "what happened to each bound binding item: the nodes it was lowered "
        "into, or that it matched nothing"
    ),
    "policies": "each policy provision, its phase, and the nodes it constrains",
    "rules": "each rule, its phase, and the nodes where it triggers",
    "protocols": "each protocol frame, hook, and generated node",
    "patterns": "each pattern application and the procedure nodes it expanded to",
    "heuristics": "each heuristic and the decision or gate nodes it advises",
    "guidance": "each guidance unit and the nodes its synopsis renders on",
    "profiles": "each profile, its description, and its supplementary contributions",
    "attention": (
        "root control-plane bytes, execution-module bytes/count/maximum, worst-path "
        "execution bytes and loads, supplementary "
        "reference bytes, and outbound links with their generated roles"
    ),
    "outputs": "every file a build would write, with size and mode",
    "diagnostics": "aggregated errors and warnings",
}
DEFAULT_INSPECT_DIMENSIONS: tuple[str, ...] = (
    "skill",
    "workflows",
    "attention",
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
# Loading one skill's selected source
# --------------------------------------------------------------------------


@dataclass
class SkillContent:
    """One skill's manifest, every construct it selects, and the files it copies."""

    skill: Skill
    sources: SourceSet = field(default_factory=SourceSet)
    selected: dict[str, list[Path]] = field(default_factory=dict)
    icon_sources: dict[str, Path] = field(default_factory=dict)
    icon_assets: dict[str, bytes] = field(default_factory=dict)
    profile_guides: dict[str, str] = field(default_factory=dict)

    def copied(self, key: str) -> list[Path]:
        return self.selected.get(key, [])

    def relative(self, key: str) -> tuple[str, ...]:
        root = self.skill.root
        return tuple(
            path.relative_to(root).as_posix() for path in self.copied(key)
        )


def load_content(skill: Skill, diagnostics: Diagnostics) -> SkillContent:
    """Select, read, and schema-check every source the manifest names."""
    content = SkillContent(skill=skill)
    config = check_manifest(skill, diagnostics)
    for key in CONTENT_KEYS:
        content.selected[key] = content_files(skill, config, key, diagnostics)
    for key in CONSTRUCT_KINDS:
        _read_constructs(content, key, diagnostics)
    _check_profile_titles(content, diagnostics)
    _check_copied_kinds(content, diagnostics)
    content.profile_guides = _load_profile_guides(content, diagnostics)
    content.icon_sources, content.icon_assets = _load_icons(skill, diagnostics)
    return content


def _read_constructs(
    content: SkillContent, key: str, diagnostics: Diagnostics
) -> None:
    reader = CONSTRUCT_READERS[key]
    label = CONSTRUCT_LABELS[key]
    store = content.sources.kind(key)
    origins: dict[str, Path] = {}
    for path in content.copied(key):
        if path.suffix != ".yaml":
            diagnostics.error(
                f"{path}: a {label} source is a .yaml file",
                "source.unsupported",
                path,
            )
            continue
        diagnostics.add(yaml_scalar_warnings(path))
        try:
            data = load_yaml(path)
        except DegardisError as exc:
            diagnostics.source_failure(exc, path, "source.invalid-yaml")
            continue
        construct = reader(path, data, diagnostics)
        if construct is None:
            continue
        # Profiles are not reference targets, so their source-relative key can
        # preserve two auxiliary profiles that deliberately share a file stem.
        identifier = (
            path.relative_to(content.skill.root).with_suffix("").as_posix()
            if key == "profiles"
            else construct.id
        )
        previous = origins.get(identifier)
        if previous is not None:
            diagnostics.error(
                f"{path}: {label} id {identifier} is already taken by "
                f"{previous}; a file stem is a construct's identity, so two "
                "files cannot share one",
                "source.duplicate-id",
                path,
            )
            continue
        origins[identifier] = path
        store[identifier] = construct


def _check_profile_titles(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Keep index labels distinct even when profile source paths differ."""
    seen: dict[str, Path] = {}
    for profile in content.sources.profiles.values():
        previous = seen.get(profile.title.casefold())
        if previous is not None:
            diagnostics.error(
                f"{profile.path}: profile title {profile.title!r} is already used "
                f"by {previous}; profile titles must be unique",
                "profile.duplicate-title",
                profile.path,
            )
            continue
        seen[profile.title.casefold()] = profile.path


def _check_copied_kinds(content: SkillContent, diagnostics: Diagnostics) -> None:
    for path in content.copied("references"):
        if path.suffix.casefold() not in (".md", ".markdown"):
            diagnostics.error(
                f"{path}: content.references selects Markdown pages, and this "
                "file is not one",
                "source.unsupported",
                path,
            )


LEVEL_ONE_HEADING = re.compile(r"^\s{0,3}#\s", re.MULTILINE)


def _load_profile_guides(
    content: SkillContent, diagnostics: Diagnostics
) -> dict[str, str]:
    """Read each profile's guide files into the body its generated page carries.

    A guide is structured Markdown whose meaning depends on sections, examples,
    or tables, which is why it is a file rather than another `guidance` line. It
    is appended to the profile's page, so the page supplies the level-one
    heading and a guide may not bring one of its own.
    """
    root = content.skill.root
    bodies: dict[str, str] = {}
    for identifier, profile in content.sources.profiles.items():
        chunks: list[str] = []
        for guide in profile.guides:
            source = (profile.path.parent / guide).resolve()
            try:
                source.relative_to(root.resolve())
            except ValueError:
                diagnostics.error(
                    f"{profile.path}: guide must stay within the skill "
                    f"directory: {guide}",
                    "profile.guide-outside-skill",
                    profile.path,
                )
                continue
            if source.suffix != ".md":
                diagnostics.error(
                    f"{profile.path}: guide must reference a Markdown file: {guide}",
                    "profile.guide-not-markdown",
                    profile.path,
                )
                continue
            if not source.is_file():
                diagnostics.error(
                    f"{profile.path}: guide not found: {guide}",
                    "profile.guide-missing",
                    profile.path,
                )
                continue
            chunks.append(source.read_text(encoding="utf-8").strip())
        body = "\n\n".join(chunks).replace("\r\n", "\n").replace("\r", "\n")
        if LEVEL_ONE_HEADING.search(body):
            diagnostics.error(
                f"{profile.path}: guides must not contain a level-one heading; "
                "the profile page supplies it",
                "profile.guide-heading",
                profile.path,
            )
            continue
        bodies[identifier] = body
    return bodies


def _load_icons(
    skill: Skill, diagnostics: Diagnostics
) -> tuple[dict[str, Path], dict[str, bytes]]:
    """Resolve the declared icon and rasterize it, keeping what it rendered.

    Rendering is how an icon source is checked at all — an unusable image is
    found by converting it — so these bytes exist here whether or not anything
    asks for them. Keeping them is what lets the outputs report state the size
    a build will write, for a file that is not yet on disk anywhere.
    """
    try:
        sources = resolve_icon_sources(skill)
        assets = render_icon_assets(sources)
    except IconError as exc:
        diagnostics.error(exc, exc.code, skill.root / "skill.yaml")
        return {}, {}
    return sources, assets


def _check_resource_uses(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Every typed runtime resource must be selected into the bundle."""
    selected = {
        path
        for key in ("references", "scripts", "assets")
        for path in content.relative(key)
    }
    for workflow in content.sources.workflows.values():
        for step in workflow.steps:
            if step.resource is None:
                continue
            if step.resource.path not in selected:
                diagnostics.error(
                    f"{workflow.path}: steps.{step.id}.resource names "
                    f"{step.resource.path}, which the manifest does not select into "
                    "the bundle",
                    "resource.not-selected",
                    workflow.path,
                )


# --------------------------------------------------------------------------
# Compiling one skill
# --------------------------------------------------------------------------


@dataclass
class Compiled:
    content: SkillContent
    graphs: dict[str, WorkflowGraph] = field(default_factory=dict)
    lowered: LoweredSkill | None = None
    rendered: RenderedBundle | None = None
    bundle: BundleContent = field(default_factory=BundleContent)


def compile_skill(skill: Skill, diagnostics: Diagnostics) -> Compiled:
    """Read, check, lower, and render one skill, collecting every problem found."""
    content = load_content(skill, diagnostics)
    result = Compiled(content=content)
    sources = content.sources
    _check_references(content, diagnostics)
    _check_resource_uses(content, diagnostics)
    primary = skill.primary_workflow
    if primary and primary not in sources.workflows:
        diagnostics.error(
            f"{skill.root / 'skill.yaml'}: primary_workflow names {primary}, "
            "which content.workflows does not select",
            "source.unknown-reference",
            skill.root / "skill.yaml",
        )
        return result
    order, callers = call_order(primary, sources, diagnostics)
    _warn_unreached_workflows(content, order, diagnostics)
    for identifier in order:
        workflow = sources.workflows[identifier]
        result.graphs[identifier] = build_graph(workflow, sources, diagnostics)
    if any(not graph.usable for graph in result.graphs.values()):
        return result
    lowerer = Lowerer(skill, sources, result.graphs, order, callers, diagnostics)
    result.lowered = lowerer.lower()
    _check_lowering(result.lowered, diagnostics)
    _check_conflicting_obligations(result.lowered, diagnostics)
    _check_protocol_states(result.lowered, diagnostics)
    result.bundle = BundleContent(profile_guides=content.profile_guides)
    result.rendered = render_skill(result.lowered, result.bundle, diagnostics)
    _check_attention_budgets(result, diagnostics)
    _check_outputs(result, diagnostics)
    return result



# --------------------------------------------------------------------------
# Relation checks
# --------------------------------------------------------------------------


def _check_references(content: SkillContent, diagnostics: Diagnostics) -> None:
    """Check that every declared id names a selected construct of the right kind."""
    sources = content.sources
    skill = content.skill
    manifest_path = skill.root / "skill.yaml"
    for key in ("policies", "rules", "protocols", "guidance"):
        for identifier in skill.bound(key):
            _check_reference(
                sources, key, identifier, manifest_path, key, diagnostics
            )
    for workflow in sources.workflows.values():
        for key in ("policies", "rules", "protocols"):
            for identifier in getattr(workflow, key):
                _check_reference(
                    sources, key, identifier, workflow.path, key, diagnostics
                )
        for use in workflow.guidance:
            _check_guidance(sources, use.id, use.inline, workflow.path, diagnostics)
        for step in workflow.steps:
            where = f"steps.{step.id}"
            for key in ("policies", "rules", "protocols", "heuristics"):
                for identifier in getattr(step, key):
                    _check_reference(
                        sources,
                        key,
                        identifier,
                        workflow.path,
                        f"{where}.{key}",
                        diagnostics,
                    )
            for use in step.guidance:
                _check_guidance(
                    sources, use.id, use.inline, workflow.path, diagnostics
                )
            if step.form == "pattern":
                _check_reference(
                    sources,
                    "patterns",
                    step.pattern,
                    workflow.path,
                    f"{where}.pattern",
                    diagnostics,
                )
            if step.form == "use":
                _check_reference(
                    sources,
                    "workflows",
                    step.call,
                    workflow.path,
                    f"{where}.use",
                    diagnostics,
                )
    _check_record_references(sources, diagnostics)


def _check_reference(
    sources: SourceSet,
    key: str,
    identifier: str,
    path: Path,
    where: str,
    diagnostics: Diagnostics,
) -> None:
    if identifier in sources.kind(key):
        return
    other = _other_kind(sources, identifier, key)
    if other == "profiles":
        diagnostics.error(
            f"{path}: {where} names profile {identifier}; a profile is selected "
            "at runtime and nothing a workflow does may depend on one",
            "profile.workflow-dependency",
            path,
        )
        return
    if other == "guidance":
        diagnostics.error(
            f"{path}: {where} names guidance unit {identifier}; guidance is "
            "non-binding and cannot stand where a binding construct is expected",
            "guidance.invalid-application",
            path,
        )
        return
    if other:
        diagnostics.error(
            f"{path}: {where} names {identifier}, which content.{other} selects "
            f"as a {CONSTRUCT_LABELS[other]} rather than a "
            f"{CONSTRUCT_LABELS[key]}",
            "source.cross-kind-reference",
            path,
        )
        return
    diagnostics.error(
        f"{path}: {where} names {identifier}, which content.{key} does not select",
        "source.unknown-reference",
        path,
    )


def _check_guidance(
    sources: SourceSet,
    identifier: str,
    inline: bool,
    path: Path,
    diagnostics: Diagnostics,
) -> None:
    unit = sources.guidance.get(identifier)
    if unit is None:
        _check_reference(
            sources, "guidance", identifier, path, "guidance", diagnostics
        )
        return
    if inline and not unit.points:
        diagnostics.error(
            f"{path}: guidance {identifier} is applied with detail: inline, and "
            "the unit declares no points to render",
            "guidance.invalid-application",
            path,
        )


def _other_kind(sources: SourceSet, identifier: str, key: str) -> str:
    for kind in CONSTRUCT_KINDS:
        if kind == key:
            continue
        if kind == "profiles" and any(
            profile.id == identifier for profile in sources.profiles.values()
        ):
            return kind
        if identifier in sources.kind(kind):
            return kind
    return ""


def _check_record_references(
    sources: SourceSet, diagnostics: Diagnostics
) -> None:
    """Check every record a type names, wherever a type is declared."""
    for kind in ("records", "patterns", "workflows", "protocols"):
        for construct in sources.kind(kind).values():
            for name, declared in _declared_types(construct):
                record = declared.base.record
                if not record or record in sources.records:
                    continue
                diagnostics.error(
                    f"{construct.path}: {name} names record {record}, which "
                    "content.records does not select",
                    "source.unknown-reference",
                    construct.path,
                )
    for workflow in sources.workflows.values():
        for outcome in workflow.outcomes:
            if outcome.record and outcome.record not in sources.records:
                diagnostics.error(
                    f"{workflow.path}: outcomes.{outcome.id}.record names "
                    f"{outcome.record}, which content.records does not select",
                    "source.unknown-reference",
                    workflow.path,
                )


def _declared_types(construct: Any) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    for name, declared in getattr(construct, "inputs", ()):
        found.append((f"inputs.{name}", declared))
    for item in getattr(construct, "fields", ()):
        found.append((f"fields.{item.name}", item.type))
    for item in getattr(construct, "data", ()):
        found.append((f"data.{item.name}", item.type))
    for step in getattr(construct, "steps", ()):
        for name, declared in step.produces:
            found.append((f"steps.{step.id}.produces.{name}", declared))
    return found


def _warn_unreached_workflows(
    content: SkillContent, order: tuple[str, ...], diagnostics: Diagnostics
) -> None:
    for identifier, workflow in content.sources.workflows.items():
        if identifier in order:
            continue
        diagnostics.warning(
            f"{workflow.path}: no reached step calls workflow {identifier}, and "
            "it is not the primary workflow, so nothing renders it and no run "
            "can enter it",
            "workflow.unreached",
            workflow.path,
        )


def _check_lowering(lowered: LoweredSkill, diagnostics: Diagnostics) -> None:
    """Report every bound binding item lowering did not place, and every one it
    placed nowhere because its selector matched no reachable node.

    The first is an error: an active provision, rule, or hook that is not in the
    execution graph is a requirement the installed skill never states, and no
    agent can act on it. The second is a warning: shipping a construct before
    anything matches it is what mid-design work looks like, and a project that
    will not accept one passes `--fail-on-warning`.
    """
    sources = lowered.sources
    for identifier, policy in sources.policies.items():
        for provision in policy.provisions:
            key = (identifier, provision.id)
            if key not in lowered.bound_provisions:
                continue
            if key in lowered.lowered_provisions:
                continue
            if key in lowered.matched_provisions:
                form = lowered.misphased_provisions.get(key)
                diagnostics.error(
                    f"{policy.path}: provision {provision.id} "
                    + _unlowered_reason(form),
                    "policy.unlowered-provision",
                    policy.path,
                )
                continue
            diagnostics.warning(
                f"{policy.path}: provision {provision.id} is bound and its "
                f"selector ({provision.selector.render()}) matches no reachable "
                f"{provision.phase} node, so nothing enforces it",
                "policy.unmatched-provision",
                policy.path,
            )
    for identifier, rule in sources.rules.items():
        if identifier not in lowered.bound_rules:
            continue
        if identifier in lowered.lowered_rules:
            continue
        if identifier in lowered.matched_rules:
            form = lowered.misphased_rules.get(identifier)
            diagnostics.error(
                f"{rule.path}: rule {identifier} " + _unlowered_reason(form),
                "rule.unlowered",
                rule.path,
            )
            continue
        diagnostics.warning(
            f"{rule.path}: rule {identifier} is bound and its selector "
            f"({rule.provision.selector.render()}) matches no reachable "
            f"{rule.provision.phase} node, so nothing enforces it",
            "rule.unmatched",
            rule.path,
        )
    for identifier, protocol in sources.protocols.items():
        for hook in protocol.hooks:
            key = (identifier, hook.id)
            if key not in lowered.active_hooks or key in lowered.lowered_hooks:
                continue
            severity = (
                diagnostics.error
                if hook.phase in ("enter", "exit")
                else diagnostics.warning
            )
            severity(
                f"{protocol.path}: hook {hook.id} is active and reached no "
                "generated node, so nothing carries its command or its state "
                "change",
                "protocol.unlowered-hook",
                protocol.path,
            )
    for key in sorted(lowered.applied_patterns - lowered.expanded_patterns):
        workflow = sources.workflows[key[0]]
        diagnostics.error(
            f"{workflow.path}: steps.{key[1]} applies a pattern that expanded "
            "into no node, so the step performs nothing",
            "pattern.unexpanded",
            workflow.path,
        )
    _warn_unused_constructs(lowered, diagnostics)


def _warn_unused_constructs(
    lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """Warn about a selected construct no reached scope names.

    A bundle carries what its manifest selects. A construct nothing reaches is
    weight an installed skill pays for and an agent never meets, and the bundle
    itself cannot show it.
    """
    sources = lowered.sources
    reached = lowered.reached_constructs()
    for kind in ("policies", "rules", "protocols", "patterns", "heuristics", "guidance"):
        reached_kind = reached[kind]
        for identifier, construct in sources.kind(kind).items():
            if identifier in reached_kind:
                continue
            diagnostics.warning(
                f"{construct.path}: {CONSTRUCT_LABELS[kind]} {identifier} is "
                "selected and nothing this run reaches names it, so the bundle "
                "ships a page no agent meets",
                "source.unbound-construct",
                construct.path,
            )


def _unlowered_reason(form: str | None) -> str:
    """Why a matched binding item reached no node, in the terms of the repair.

    A `during` item that selected a decision, a gate, or a branch is the one
    case where the author's selector is right and the phase is wrong, and the
    generic message would send them to re-tag the step. Naming the form and the
    forms that do carry an invariant says which field to change.
    """
    if form in INVARIANT_REFUSING_FORMS:
        return (
            f"is `during` and matched a {form} node, which states a choice "
            "rather than an action, so it carries no invariant. A `during` "
            "item renders on an action, a call, a pattern procedure item, or a "
            "return; select one of those, or move the requirement to `before` "
            f"to check it ahead of the {form}"
        )
    return (
        "matched a reached node and reached no generated node, so the "
        "requirement is in no installed page"
    )


def _check_conflicting_obligations(
    lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """Report one command both required and prohibited at one boundary.

    This is the whole of the conflict the compiler can see. Two provisions
    matching one selector at one phase are not in conflict — requiring that a
    boundary be established and prohibiting a write outside it is exactly how a
    policy is written — and the compiler cannot read two different sentences to
    decide whether they disagree. What it can decide is that the same sentence
    is both required and forbidden at the same step and phase, which no reading
    makes coherent.

    The phase is part of the key because a command prohibited before a node and
    required after it is a sequence rather than a contradiction.

    The key is the node and the phase, never how the provision reached them, so
    an obligation selected by `effects` is compared exactly like one selected
    by `forms` or `subjects`. That is the whole of the effect-level case: a step
    whose declared effect a policy forbids is not expressible, because effects
    are opaque tags and no field names an effect to forbid.
    """
    obligations: dict[tuple[str, str, str, str], dict[bool, str]] = {}
    for node in lowered.all_nodes():
        found = []
        if node.kind == "check" and node.phase:
            found.append((node.phase, node.command, node.prohibits, node.source))
        for invariant in node.invariants:
            found.append(
                ("during", invariant.command, invariant.prohibits, invariant.source)
            )
        for phase, command, prohibits, source in found:
            key = (node.workflow, node.step, phase, " ".join(command.split()).casefold())
            obligations.setdefault(key, {}).setdefault(prohibits, source)
    for (workflow, step, phase, _), sources in sorted(obligations.items()):
        if len(sources) < 2:
            continue
        path = lowered.sources.workflows[workflow].path
        diagnostics.error(
            f"{path}: at {phase} `{workflow}.{step}` one command is both "
            f"required and prohibited: {sources[False]} requires it, and "
            f"{sources[True]} prohibits it",
            "workflow.conflicting-obligation",
            path,
        )


def _check_protocol_states(
    lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    """Establish, per frame, which states are possible where each hook runs.

    The analysis is a fixed point over the lowered graph because a run frame's
    state crosses a call: a callee's entry state is the state at each of its
    call sites, and a caller's state after the call is whatever the callee left.
    Both sets only grow, and the state set is finite, so repeating the pass
    until nothing changes terminates and is exact rather than conservative.
    """
    for frame in lowered.frames:
        _check_frame(frame, lowered, diagnostics)


def _check_frame(
    frame: Frame, lowered: LoweredSkill, diagnostics: Diagnostics
) -> None:
    protocol = frame.protocol
    path = protocol.path
    reachable = {protocol.initial, *(hook.to for hook in protocol.hooks if hook.to)}
    unreachable = sorted(set(protocol.states) - reachable)
    if unreachable:
        diagnostics.error(
            f"{path}: states {', '.join(unreachable)} cannot be reached: the "
            "initial state is not one of them and no hook moves to one",
            "protocol.invalid-state",
            path,
        )
    scope = (
        [item.workflow.id for item in lowered.workflows]
        if frame.scope == "run"
        else [frame.workflow]
    )
    nodes_by_step = _frame_nodes(frame, lowered, scope)
    entry_step = _frame_entry(frame, lowered)
    states: dict[tuple[str, str], frozenset[str]] = {}
    for _ in range(len(scope) + 2):
        changed = _propagate(frame, lowered, scope, entry_step, nodes_by_step, states)
        if not changed:
            break
    _report_frame(frame, lowered, scope, nodes_by_step, states, diagnostics)


def _frame_nodes(
    frame: Frame, lowered: LoweredSkill, scope: list[str]
) -> dict[tuple[str, str], list[Node]]:
    found: dict[tuple[str, str], list[Node]] = {}
    for item in lowered.workflows:
        if item.workflow.id not in scope:
            continue
        for node in item.nodes:
            if node.frame != frame.label:
                continue
            if frame.scope == "step" and node.step != frame.step:
                continue
            found.setdefault((node.workflow, node.step), []).append(node)
    return found


def _frame_entry(frame: Frame, lowered: LoweredSkill) -> tuple[str, str]:
    if frame.scope == "step":
        return (frame.workflow, frame.step)
    workflow = (
        lowered.skill.primary_workflow if frame.scope == "run" else frame.workflow
    )
    entry = lowered.sources.workflows.get(workflow)
    return (workflow, entry.entry if entry is not None else "")


def _propagate(
    frame: Frame,
    lowered: LoweredSkill,
    scope: list[str],
    entry_step: tuple[str, str],
    nodes_by_step: dict[tuple[str, str], list[Node]],
    states: dict[tuple[str, str], frozenset[str]],
) -> bool:
    protocol = frame.protocol
    changed = False

    def merge(key: tuple[str, str], values: frozenset[str]) -> None:
        nonlocal changed
        current = states.get(key, frozenset())
        if not values <= current:
            states[key] = current | values
            changed = True

    merge(entry_step, frozenset({protocol.initial}))
    for item in lowered.workflows:
        workflow = item.workflow
        if workflow.id not in scope:
            continue
        steps = {step.id: step for step in workflow.steps}
        for identifier in item.graph.order:
            if frame.scope == "step" and identifier != frame.step:
                continue
            incoming = states.get((workflow.id, identifier), frozenset())
            if not incoming:
                continue
            outgoing = _apply_hooks(
                frame, nodes_by_step.get((workflow.id, identifier), []), incoming
            )
            step = steps[identifier]
            if step.form == "use" and frame.scope == "run":
                callee = lowered.sources.workflows.get(step.call)
                if callee is not None:
                    merge((callee.id, callee.entry), outgoing)
                    outgoing = _callee_exit(callee, states, outgoing)
            for target in step.successors:
                merge((workflow.id, target), outgoing)
    return changed


def _callee_exit(
    callee: Any,
    states: dict[tuple[str, str], frozenset[str]],
    fallback: frozenset[str],
) -> frozenset[str]:
    exits = frozenset()
    seen = False
    for step in callee.steps:
        if step.form != "return":
            continue
        current = states.get((callee.id, step.id))
        if current:
            seen = True
            exits |= current
    return exits if seen else fallback


def _apply_hooks(
    frame: Frame, nodes: list[Node], incoming: frozenset[str]
) -> frozenset[str]:
    protocol = frame.protocol
    hooks = {hook.id: hook for hook in protocol.hooks}
    current = set(incoming)
    for node in nodes:
        hook = hooks.get(node.hook)
        if hook is None:
            continue
        firing = current & set(hook.from_states)
        if not firing:
            continue
        remaining = current - firing
        if hook.to:
            remaining.add(hook.to)
        else:
            remaining |= firing
        if hook.when is not None:
            remaining |= firing
        current = remaining
    return frozenset(current)


def _report_frame(
    frame: Frame,
    lowered: LoweredSkill,
    scope: list[str],
    nodes_by_step: dict[tuple[str, str], list[Node]],
    states: dict[tuple[str, str], frozenset[str]],
    diagnostics: Diagnostics,
) -> None:
    protocol = frame.protocol
    path = protocol.path
    hooks = {hook.id: hook for hook in protocol.hooks}
    for key, nodes in sorted(nodes_by_step.items()):
        current = states.get(key, frozenset())
        if not current:
            continue
        for node in nodes:
            hook = hooks.get(node.hook)
            if hook is None:
                if node.kind == "accepting" and not (
                    current & set(protocol.accepting)
                ):
                    diagnostics.error(
                        f"{path}: the {frame.name} closes at "
                        f"`{key[0]}.{key[1]}` where its state can only be "
                        f"{', '.join(sorted(current))}, and no accepting state "
                        "is among them",
                        "protocol.impossible-transition",
                        path,
                    )
                continue
            if not current & set(hook.from_states):
                diagnostics.error(
                    f"{path}: hook {hook.id} runs from "
                    f"{', '.join(hook.from_states)}, and at "
                    f"`{key[0]}.{key[1]}` the frame's state can only be "
                    f"{', '.join(sorted(current))}",
                    "protocol.impossible-transition",
                    path,
                )
            current = _apply_hooks(frame, [node], current)


# --------------------------------------------------------------------------
# Output checks
# --------------------------------------------------------------------------


def _check_attention_budgets(result: Compiled, diagnostics: Diagnostics) -> None:
    if result.rendered is None:
        return
    manifest = result.content.skill.root / "skill.yaml"
    root_bytes = len(result.rendered.skill_text.encode("utf-8"))
    if root_bytes > ROOT_BUDGET_BYTES:
        diagnostics.warning(
            f"{manifest}: generated SKILL.md is {root_bytes} bytes, above the "
            f"{ROOT_BUDGET_BYTES}-byte control-plane budget",
            "render.root-budget",
            manifest,
        )
    # The partition sizes every module against this same budget, so a module
    # over it holds either one node too large to divide, which reports itself,
    # or a workflow header too large to fit a node around.
    for relative, text in result.rendered.execution_modules.items():
        size = len(text.encode("utf-8"))
        if size > MODULE_BUDGET_BYTES:
            diagnostics.warning(
                f"{manifest}: generated execution module {relative} is {size} bytes, "
                f"above the {MODULE_BUDGET_BYTES}-byte budget for one loaded module, "
                "so an agent may receive it truncated",
                "render.module-budget",
                manifest,
            )


def _check_outputs(result: Compiled, diagnostics: Diagnostics) -> None:
    """Check what a build would write: collisions, and every reference it links."""
    if result.rendered is None:
        return
    content = result.content
    root = content.skill.root
    written: dict[str, Path] = {}
    for key in COPIED_CONTENT_KEYS:
        for path in content.copied(key):
            relative = path.relative_to(root).as_posix()
            previous = written.get(relative)
            if previous is not None:
                diagnostics.error(
                    f"{path}: two selected files would be written to {relative}",
                    "output.path-collision",
                    path,
                )
            written[relative] = path
    generated = {**result.rendered.execution_modules, **result.rendered.pages}
    for relative in generated:
        if relative in written:
            diagnostics.error(
                f"{written[relative]}: a generated page is written to "
                f"{relative}, and a selected file already occupies it; rename "
                "one of them",
                "output.path-collision",
                written[relative],
            )
    shipped = set(written) | set(generated) | {"SKILL.md"}
    manifest = root / "skill.yaml"
    for link in result.rendered.links:
        if link.target not in shipped:
            diagnostics.error(
                f"{manifest}: the supplementary reference {link.target}, linked from "
                f"{link.node}, is not a file this bundle ships",
                "output.broken-reference",
                manifest,
            )
    linked = {link.target for link in result.rendered.links}
    # Generated pages are checked beside the copied files they link to. A page
    # that is itself unreached makes every file it links unreached too, so
    # checking only the last hop of the chain passes a reference no route
    # actually arrives at.
    reachable = {**written, **dict.fromkeys(generated, manifest)}
    for relative, path in sorted(reachable.items()):
        if relative.startswith("references/") and relative not in linked:
            diagnostics.warning(
                f"{path}: no generated page links {relative}, so the bundle "
                "ships a reference nothing points at",
                "output.unlinked-reference",
                path,
            )


# --------------------------------------------------------------------------
# The inspection result
# --------------------------------------------------------------------------


@dataclass
class Inspection:
    """One skill as this run read it: its identity, its compilation, its findings."""

    root: Path
    diagnostics: Diagnostics
    skill: Skill | None = None
    compiled: Compiled | None = None


def compile_all(skill_paths: Iterable[Path]) -> list[Inspection]:
    """Compile every selected skill once, so no caller compiles one twice.

    `validate`, the `inspect` report, and `build` all need the same compilation.
    Reading it once is not only cheaper: it is what makes the three agree, since
    a second pass could observe a source edited between them.
    """
    inspections: list[Inspection] = []
    for root in skill_paths:
        diagnostics = Diagnostics()
        try:
            skill = load_skill_path(root)
        except DegardisError as exc:
            diagnostics.source_failure(
                exc, root / "skill.yaml", "manifest.unreadable"
            )
            inspections.append(Inspection(root=root, diagnostics=diagnostics))
            continue
        compiled = compile_skill(skill, diagnostics)
        inspections.append(
            Inspection(
                root=root, diagnostics=diagnostics, skill=skill, compiled=compiled
            )
        )
    return inspections


def inspect_skills(
    skill_paths: Iterable[Path], *, include_body: bool = False
) -> list[dict[str, Any]]:
    return [
        result_dict(inspection, include_body=include_body)
        for inspection in compile_all(skill_paths)
    ]


def result_dict(
    inspection: Inspection, *, include_body: bool = False
) -> dict[str, Any]:
    if inspection.skill is None or inspection.compiled is None:
        return _unreadable_result(inspection.root, inspection.diagnostics)
    return _result_dict(
        inspection.skill,
        inspection.compiled,
        inspection.diagnostics,
        include_body=include_body,
    )


def _unreadable_result(root: Path, diagnostics: Diagnostics) -> dict[str, Any]:
    return {
        "name": root.name,
        "title": root.name,
        "version": "",
        "description": "",
        "license": None,
        "copyright": None,
        "source": root,
        "primary_workflow": "",
        "format_version": None,
        "source_fingerprint": source_fingerprint(root, {}),
        "counts": dict.fromkeys(CONTENT_KEYS, 0),
        "sources": [],
        "workflows": [],
        "execution": [],
        "lowering": [],
        "policies": [],
        "rules": [],
        "protocols": [],
        "patterns": [],
        "heuristics": [],
        "guidance": [],
        "profiles": [],
        "attention": {
            "root_bytes": 0,
            "root_lines": 0,
            "root_words": 0,
            "execution_bytes": 0,
            "execution_modules": 0,
            "largest_execution_module_bytes": 0,
            "execution_path_bytes": 0,
            "execution_path_loads": 0,
            "reference_bytes": 0,
            "execution_links": 0,
            "optional_links": [],
        },
        "outputs": [],
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "skill_text": None,
    }


def _result_dict(
    skill: Skill,
    compiled: Compiled,
    diagnostics: Diagnostics,
    *,
    include_body: bool,
) -> dict[str, Any]:
    content = compiled.content
    lowered = compiled.lowered
    rendered = compiled.rendered
    text = rendered.skill_text if rendered is not None else ""
    result: dict[str, Any] = {
        "name": skill.name,
        "title": skill.title,
        "version": skill.version,
        "description": skill.description,
        "license": skill.manifest.get("license"),
        "copyright": skill.manifest.get("copyright"),
        "source": skill.root,
        "primary_workflow": skill.primary_workflow,
        "format_version": skill.manifest.get("format_version"),
        "source_fingerprint": source_fingerprint(skill.root, content.selected),
        "counts": {key: len(content.copied(key)) for key in CONTENT_KEYS},
        "sources": _source_rows(content),
        "workflows": _workflow_rows(compiled),
        "execution": _execution_rows(lowered),
        "lowering": _lowering_rows(lowered),
        "policies": _policy_rows(lowered),
        "rules": _rule_rows(lowered),
        "protocols": _protocol_rows(lowered),
        "patterns": _pattern_rows(lowered),
        "heuristics": _heuristic_rows(lowered),
        "guidance": _guidance_rows(lowered),
        "profiles": _profile_rows(content),
        "attention": _attention(compiled, text, diagnostics),
        "outputs": _output_rows(compiled),
        "diagnostics": list(diagnostics.records),
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "skill_text": text if include_body else None,
    }
    return result


def _source_rows(content: SkillContent) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = content.skill.root
    for key in CONTENT_KEYS:
        store = content.sources.kind(key) if key in CONSTRUCT_KINDS else {}
        by_path = {construct.path: identifier for identifier, construct in store.items()}
        for path in content.copied(key):
            rows.append(
                {
                    "kind": key,
                    "id": by_path.get(path, ""),
                    "path": path.relative_to(root).as_posix(),
                    "bytes": _size(path),
                }
            )
    return rows


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _workflow_rows(compiled: Compiled) -> list[dict[str, Any]]:
    lowered = compiled.lowered
    rows: list[dict[str, Any]] = []
    root = compiled.content.skill.root
    primary = compiled.content.skill.primary_workflow
    reached = {item.workflow.id: item for item in lowered.workflows} if lowered else {}
    for identifier, workflow in sorted(compiled.content.sources.workflows.items()):
        item = reached.get(identifier)
        caller = lowered.callers.get(identifier) if lowered else None
        entry = None
        if item is not None:
            entry = next(
                (node for node in item.nodes if node.label == item.entry), None
            )
        rows.append(
            {
                "id": identifier,
                "title": workflow.title,
                "description": workflow.description,
                "status": (
                    "primary"
                    if identifier == primary
                    else "reached"
                    if item is not None
                    else "unreached"
                ),
                "from": f"{caller[0]}/{caller[1]}" if caller else "",
                "steps": len(workflow.steps),
                "nodes": len(item.nodes) if item is not None else 0,
                "inputs": [name for name, _ in workflow.inputs],
                "outcomes": [outcome.id for outcome in workflow.outcomes],
                "entry": item.entry if item is not None else "",
                "entry_command": entry.command if entry is not None else "",
                "path": workflow.path.relative_to(root).as_posix(),
                "bytes": _size(workflow.path),
            }
        )
    return rows


def _execution_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    for item in lowered.workflows:
        for node in item.nodes:
            rows.append(
                {
                    "workflow": node.workflow,
                    "label": node.label,
                    "kind": node.kind,
                    "step": node.step,
                    "command": node.command,
                    "source": node.source,
                    "transitions": [
                        {
                            "label": transition.label,
                            "target": BLOCKED_TARGET
                            if transition.blocked
                            else transition.target,
                        }
                        for transition in node.transitions
                    ],
                }
            )
    return rows


BLOCKED_TARGET = "blocked"


def _construct_nodes(lowered: LoweredSkill) -> dict[tuple[str, str, str], list[str]]:
    """Where each provision, rule, or hook ended up, keyed by its own identity.

    A check node names the construct and the local id it came from, and a
    `during` provision names the same pair on the invariant it became, so both
    ways a binding item can reach the document are indexed the same way.
    """
    found: dict[tuple[str, str, str], list[str]] = {}

    def record(key: tuple[str, str, str], label: str) -> None:
        labels = found.setdefault(key, [])
        if label not in labels:
            labels.append(label)

    for node in lowered.all_nodes():
        kind, _, construct = node.origin.partition(":")
        if node.kind == "check":
            record((kind, construct, node.provision), node.label)
        elif node.hook:
            record(("protocol", construct, node.hook), node.label)
        for invariant in node.invariants:
            record((invariant.kind, invariant.construct, invariant.local), node.label)
    return found


def _lowering_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    placed = _construct_nodes(lowered)
    for policy, provision in sorted(lowered.bound_provisions):
        rows.append(
            {
                "kind": "policy",
                "id": f"{policy}.{provision}",
                "nodes": placed.get(("policy", policy, provision), []),
                "lowered": (policy, provision) in lowered.lowered_provisions,
            }
        )
    for rule in sorted(lowered.bound_rules):
        rows.append(
            {
                "kind": "rule",
                "id": rule,
                "nodes": placed.get(("rule", rule, ""), []),
                "lowered": rule in lowered.lowered_rules,
            }
        )
    for protocol, hook in sorted(lowered.active_hooks):
        rows.append(
            {
                "kind": "protocol",
                "id": f"{protocol}.{hook}",
                "nodes": placed.get(("protocol", protocol, hook), []),
                "lowered": (protocol, hook) in lowered.lowered_hooks,
            }
        )
    for workflow, step in sorted(lowered.applied_patterns):
        rows.append(
            {
                "kind": "pattern",
                "id": f"{workflow}.{step}",
                "nodes": [
                    node.label
                    for node in lowered.all_nodes()
                    if node.kind == "procedure"
                    and node.workflow == workflow
                    and node.step == step
                ],
                "lowered": (workflow, step) in lowered.expanded_patterns,
            }
        )
    return rows


def _policy_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    placed = _construct_nodes(lowered)
    for identifier, policy in sorted(lowered.sources.policies.items()):
        provisions = []
        for provision in policy.provisions:
            provisions.append(
                {
                    "id": provision.id,
                    "phase": provision.phase,
                    "obligation": "prohibit" if provision.prohibits else "require",
                    "match": provision.selector.render(),
                    "nodes": placed.get(("policy", identifier, provision.id), []),
                }
            )
        rows.append(
            {
                "id": identifier,
                "title": policy.title,
                "summary": policy.summary,
                "provisions": provisions,
            }
        )
    return rows


def _rule_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    placed = _construct_nodes(lowered)
    for identifier, rule in sorted(lowered.sources.rules.items()):
        rows.append(
            {
                "id": identifier,
                "phase": rule.provision.phase,
                "obligation": "prohibit" if rule.provision.prohibits else "require",
                "match": rule.provision.selector.render(),
                "nodes": placed.get(("rule", identifier, ""), []),
            }
        )
    return rows


def _protocol_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    placed = _construct_nodes(lowered)
    for identifier, protocol in sorted(lowered.sources.protocols.items()):
        frames = [frame.name for frame in lowered.frames if frame.protocol.id == identifier]
        hooks = []
        for hook in protocol.hooks:
            hooks.append(
                {
                    "id": hook.id,
                    "phase": hook.phase,
                    "from": list(hook.from_states),
                    "to": hook.to,
                    "nodes": placed.get(("protocol", identifier, hook.id), []),
                }
            )
        rows.append(
            {
                "id": identifier,
                "states": list(protocol.states),
                "initial": protocol.initial,
                "accepting": list(protocol.accepting),
                "frames": frames,
                "hooks": hooks,
            }
        )
    return rows


def _pattern_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    for identifier, pattern in sorted(lowered.sources.patterns.items()):
        applications = []
        for workflow, step in sorted(lowered.applied_patterns):
            source_step = lowered.sources.workflows[workflow].step(step)
            if source_step is None or source_step.pattern != identifier:
                continue
            applications.append(
                {
                    "at": f"{workflow}.{step}",
                    "nodes": [
                        node.label
                        for node in lowered.all_nodes()
                        if node.kind == "procedure"
                        and node.workflow == workflow
                        and node.step == step
                    ],
                }
            )
        rows.append(
            {
                "id": identifier,
                "procedure": [item.id for item in pattern.procedure],
                "applications": applications,
            }
        )
    return rows


def _heuristic_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    for identifier, heuristic in sorted(lowered.sources.heuristics.items()):
        placements: list[str] = []
        for item in lowered.workflows:
            for step in item.workflow.steps:
                if identifier in step.heuristics and step.id in item.graph.reachable:
                    placements.append(f"{item.workflow.id}/{step.id}")
        rows.append(
            {
                "id": identifier,
                "question": heuristic.question,
                "advice": [item.id for item in heuristic.advice],
                "placements": placements,
                "binding": False,
            }
        )
    return rows


def _guidance_rows(lowered: LoweredSkill | None) -> list[dict[str, Any]]:
    if lowered is None:
        return []
    rows: list[dict[str, Any]] = []
    for identifier, unit in sorted(lowered.sources.guidance.items()):
        placements = [
            node.label
            for node in lowered.all_nodes()
            if any(note.id == identifier for note in node.context)
        ]
        rows.append(
            {
                "id": identifier,
                "summary": unit.summary,
                "placements": placements,
                "binding": False,
                "page": (
                    f"references/guidance/{identifier}.md"
                    if unit.has_auxiliary_material
                    else ""
                ),
            }
        )
    return rows


def _profile_rows(content: SkillContent) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for identifier, profile in sorted(content.sources.profiles.items()):
        rows.append(
            {
                "id": identifier,
                "title": profile.title,
                "description": profile.description,
                "points": len(profile.points),
                "guides": len(profile.guides),
            }
        )
    return rows


def _attention(
    compiled: Compiled, text: str, diagnostics: Diagnostics
) -> dict[str, Any]:
    rendered = compiled.rendered
    pages = rendered.pages if rendered is not None else {}
    modules = rendered.execution_modules if rendered is not None else {}
    module_sizes = [len(page.encode("utf-8")) for page in modules.values()]
    reference_bytes = sum(
        len(page.encode("utf-8")) for page in pages.values()
    ) + sum(_size(path) for path in compiled.content.copied("references"))
    execution_links = sum(
        1
        for record in diagnostics.records
        if record.code
        in ("render.load-bearing-reference", "render.external-execution-link")
    )
    optional = [
        {"target": link.target, "node": link.node}
        for link in (rendered.links if rendered is not None else [])
    ]
    return {
        "root_bytes": len(text.encode("utf-8")),
        "root_lines": len(text.splitlines()),
        "root_words": len(text.split()),
        "execution_bytes": sum(module_sizes),
        "execution_modules": len(modules),
        "largest_execution_module_bytes": max(module_sizes, default=0),
        "execution_path_bytes": rendered.execution_path_bytes if rendered else 0,
        "execution_path_loads": rendered.execution_path_loads if rendered else 0,
        "reference_bytes": reference_bytes,
        "execution_links": execution_links,
        "optional_links": optional,
    }


def _output_rows(compiled: Compiled) -> list[dict[str, Any]]:
    rendered = compiled.rendered
    if rendered is None:
        return []
    content = compiled.content
    root = content.skill.root
    rows: list[dict[str, Any]] = [
        {
            "path": "SKILL.md",
            "bytes": len(rendered.skill_text.encode("utf-8")),
            "mode": artifact_mode("SKILL.md"),
        }
    ]
    for relative, page in sorted(rendered.execution_modules.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(page.encode("utf-8")),
                "mode": artifact_mode(relative),
            }
        )
    for relative, page in sorted(rendered.pages.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(page.encode("utf-8")),
                "mode": artifact_mode(relative),
            }
        )
    for key in COPIED_CONTENT_KEYS:
        for path in content.copied(key):
            relative = path.relative_to(root).as_posix()
            rows.append(
                {
                    "path": relative,
                    "bytes": _size(path),
                    "mode": artifact_mode(relative),
                }
            )
    for relative, data in sorted(content.icon_assets.items()):
        rows.append(
            {
                "path": relative,
                "bytes": len(data),
                "mode": artifact_mode(relative),
            }
        )
    metadata = openai_metadata(
        content.skill.interface, set(content.icon_sources), content.skill.name
    )
    rows.append(
        {
            "path": "agents/openai.yaml",
            "bytes": len(metadata.encode("utf-8")),
            "mode": artifact_mode("agents/openai.yaml"),
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
