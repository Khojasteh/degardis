"""Lower every binding construct into the workflow location where it is enforced.

At runtime an agent is not asked to identify which rules apply, or to keep an
obligation ledger. So the compiler does that work here: each policy provision,
rule, and protocol hook becomes a generated execution node at the boundary it
constrains, carrying its own complete command, its active invariants, the values
available to it, its verification, its state update, and its transitions.

The result is a graph of nodes rather than a document. Nothing here renders
Markdown, and nothing here decides wording; what it decides is which node exists
where, what each one is for, and where each one goes next. That separation is
what lets the renderer prove that every executable transition names a node
defined in the same file.

A `before` check is one node in front of the node it constrains, so a linear run
of them is enough. An `after` check is not: the boundary it guards is *after
this node did what it does*, and a decision, a gate, a branch, and a call each
leave by more than one edge. So an after check is generated once per outgoing
edge, with that edge in its label. A decision with three choices and one after
provision therefore has three generated checks, each stating the choice it
follows, which is the only arrangement in which each one is true.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from .dexpr import (
    Binding,
    TypeEnvironment,
    ValueType,
    check_binding,
    check_expression,
    references,
)
from .graph import WorkflowGraph
from .model import BLOCKED_OUTCOME, Diagnostics, Skill
from .sources import (
    Advice,
    GuidanceUse,
    Hook,
    NodeFacts,
    Outcome,
    Pattern,
    Protocol,
    Provision,
    SourceSet,
    Step,
    Verification,
    Workflow,
)


# The marker a transition carries while its destination is still a source step
# rather than a node label. Resolution turns it into the first node of that
# step's own lowered chain.
STEP_PREFIX = "step:"


@dataclass(frozen=True)
class Frame:
    """One protocol application, and the scope whose lifetime it follows.

    A protocol may be active at more than one scope at once, and each
    application is independent: a run frame and a workflow frame of the same
    protocol hold their own state and their own data, and neither reads the
    other. The scope name is part of every node label the frame generates, which
    is what keeps the two apart in the document as well as in the compiler.
    """

    scope: str
    protocol: Protocol
    workflow: str = ""
    step: str = ""

    @property
    def label(self) -> str:
        return f"protocol-{self.scope}-{self.protocol.id}"

    @property
    def name(self) -> str:
        if self.scope == "run":
            return f"run frame of protocol {self.protocol.id}"
        if self.scope == "workflow":
            return f"workflow {self.workflow} frame of protocol {self.protocol.id}"
        return f"step {self.workflow}.{self.step} frame of protocol {self.protocol.id}"

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.scope, self.protocol.id, self.workflow, self.step)

    def state_types(self) -> dict[str, ValueType]:
        return {item.name: item.type for item in self.protocol.data}


@dataclass(frozen=True)
class Transition:
    """One edge out of a generated node, named by its destination's own command."""

    label: str
    target: str = ""
    command: str = ""
    blocked: bool = False


@dataclass(frozen=True)
class Invariant:
    """One `during` provision or rule, rendered where the action it bounds is.

    The construct and its local id are carried rather than a rendered sentence,
    because the inspect report indexes invariants by the provision they came
    from, and the renderer is the only part that decides how to spell one.
    """

    command: str
    kind: str
    construct: str
    local: str
    prohibits: bool

    @property
    def source(self) -> str:
        origin = f"{self.kind} `{self.construct}`"
        return f"{origin}, provision `{self.local}`" if self.local else origin


@dataclass(frozen=True)
class ContextNote:
    """One non-binding guidance synopsis, as it renders where it applies."""

    id: str
    summary: str
    points: tuple[str, ...] = ()


@dataclass
class Node:
    """One generated execution node: what to do here, and where to go next."""

    label: str
    kind: str
    command: str
    workflow: str
    step: str
    source: str = ""
    available: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    supplies: tuple[str, ...] = ()
    verify: str = ""
    activation: str = ""
    state_update: str = ""
    prohibits: bool = False
    invariants: tuple[Invariant, ...] = ()
    consider: tuple[str, ...] = ()
    heuristics: tuple[str, ...] = ()
    pattern: str = ""
    context: tuple[ContextNote, ...] = ()
    transitions: tuple[Transition, ...] = ()
    outcome: str = ""
    call_workflow: str = ""
    resource_operation: str = ""
    resource_path: str = ""
    origin: str = ""
    frame: str = ""
    hook: str = ""
    provision: str = ""
    phase: str = ""


@dataclass
class LoweredWorkflow:
    workflow: Workflow
    graph: WorkflowGraph
    entry: str = ""
    nodes: list[Node] = field(default_factory=list)
    outcomes: tuple[str, ...] = ()
    context: tuple[ContextNote, ...] = ()


@dataclass
class LoweredSkill:
    """Every generated node one skill's reachable execution consists of."""

    skill: Skill
    sources: SourceSet
    workflows: list[LoweredWorkflow] = field(default_factory=list)
    callers: dict[str, tuple[str, str]] = field(default_factory=dict)
    reached: tuple[str, ...] = ()
    # What lowering did with each bound construct, for the checks that ask
    # whether an active binding item reached the execution graph at all.
    matched_provisions: set[tuple[str, str]] = field(default_factory=set)
    lowered_provisions: set[tuple[str, str]] = field(default_factory=set)
    bound_provisions: set[tuple[str, str]] = field(default_factory=set)
    matched_rules: set[str] = field(default_factory=set)
    lowered_rules: set[str] = field(default_factory=set)
    bound_rules: set[str] = field(default_factory=set)
    # A `during` item whose selector matched a node that carries no invariant.
    # Keyed the same way as the matched sets, valued by the node form that
    # refused it, so the finding can name the phase and the form rather than
    # only reporting that nothing was lowered.
    misphased_provisions: dict[tuple[str, str], str] = field(default_factory=dict)
    misphased_rules: dict[str, str] = field(default_factory=dict)
    active_hooks: set[tuple[str, str]] = field(default_factory=set)
    lowered_hooks: set[tuple[str, str]] = field(default_factory=set)
    expanded_patterns: set[tuple[str, str]] = field(default_factory=set)
    applied_patterns: set[tuple[str, str]] = field(default_factory=set)
    used_heuristics: set[str] = field(default_factory=set)
    used_guidance: set[str] = field(default_factory=set)
    frames: list[Frame] = field(default_factory=list)

    def all_nodes(self) -> list[Node]:
        return [node for lowered in self.workflows for node in lowered.nodes]

    def node_labels(self) -> set[str]:
        return {node.label for node in self.all_nodes()}

    def reached_constructs(self) -> dict[str, set[str]]:
        """Which selected constructs this run actually reaches, by kind.

        A construct nothing reaches is weight the bundle would ship and no
        agent would meet, so it gets no page and no index entry, and the author
        is warned instead. The renderer and that warning read this one answer,
        so a bundle cannot ship a page the report says nobody reaches.

        Every profile is reached: a profile is chosen at runtime, so which ones
        apply is the reader's answer rather than the compiler's.
        """
        patterns: set[str] = set()
        for workflow, step in self.applied_patterns:
            source = self.sources.workflows[workflow].step(step)
            if source is not None:
                patterns.add(source.pattern)
        found = {
            "policies": {policy for policy, _ in self.bound_provisions},
            "rules": set(self.bound_rules),
            "protocols": {protocol for protocol, _ in self.active_hooks},
            "patterns": patterns,
            "heuristics": set(self.used_heuristics),
            "guidance": set(self.used_guidance),
            "profiles": set(self.sources.profiles),
            "records": set(self.sources.records),
            "workflows": set(self.reached),
        }
        return found


# --------------------------------------------------------------------------
# Scope resolution
# --------------------------------------------------------------------------


@dataclass
class Scopes:
    """Which binding constructs reach one step, and from which scope each came.

    Candidates are ordered run, workflow, step, because that is the order a
    reader meets them and the order precedence resolves them in. A repeated id
    at a nested scope is an error rather than a merge: a provision bound twice
    would be lowered twice at the same boundary, and the second copy states
    nothing the first did not.
    """

    policies: tuple[tuple[str, str], ...] = ()
    rules: tuple[tuple[str, str], ...] = ()
    protocols: tuple[tuple[str, str], ...] = ()
    guidance: tuple[tuple[str, GuidanceUse], ...] = ()


def _scope_values(
    skill: Skill, workflow: Workflow, step: Step | None, key: str
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for scope, values in (
        ("run", skill.bound(key)),
        ("workflow", getattr(workflow, key)),
        ("step", getattr(step, key) if step is not None else ()),
    ):
        found.extend((scope, value) for value in values)
    return found


def resolve_scopes(
    skill: Skill,
    workflow: Workflow,
    step: Step | None,
    diagnostics: Diagnostics,
) -> Scopes:
    resolved: dict[str, tuple[tuple[str, str], ...]] = {}
    for key in ("policies", "rules", "protocols"):
        seen: dict[str, str] = {}
        kept: list[tuple[str, str]] = []
        for scope, value in _scope_values(skill, workflow, step, key):
            if value in seen:
                where = f"steps.{step.id}: " if step is not None else ""
                diagnostics.error(
                    f"{workflow.path}: {where}{key} names {value} at {scope} "
                    f"scope, and {seen[value]} scope already binds it",
                    "workflow.duplicate-binding",
                    workflow.path,
                )
                continue
            seen[value] = scope
            kept.append((scope, value))
        resolved[key] = tuple(kept)
    # A guidance unit applied at more than one scope keeps the narrowest
    # application, because that is the one that says most: a step asking for
    # `detail: inline` has asked for more than the run-level synopsis, and
    # dropping it would silently ignore the request.
    guidance: dict[str, tuple[str, GuidanceUse]] = {}
    for scope, uses in (
        ("run", tuple(GuidanceUse(name) for name in skill.bound("guidance"))),
        ("workflow", workflow.guidance),
        ("step", step.guidance if step is not None else ()),
    ):
        for use in uses:
            guidance[use.id] = (scope, use)
    return Scopes(
        policies=resolved["policies"],
        rules=resolved["rules"],
        protocols=resolved["protocols"],
        guidance=tuple(guidance.values()),
    )


# --------------------------------------------------------------------------
# Node labels
# --------------------------------------------------------------------------


NODE_LABEL_DIGITS = 10


def node_label(workflow: str, step: str, suffix: str = "") -> str:
    """Return a deterministic, short runtime label for one node.

    The label is paid on the node's own heading and again on every edge that
    targets it, so its length is charged to the module budget several times
    over. Spelling out the provenance instead — workflow, step, phase, kind,
    construct, and local id — reached a hundred characters on real skills and
    bought the executing agent nothing it cannot read from the heading beside
    it. Provenance stays in `inspect`, which is where anyone tracing a node
    back to its source is already looking.

    The digest is over the same semantic identity the readable form spelled,
    so a label is stable across rebuilds and independent of discovery order.
    Truncation makes a collision possible rather than impossible; the renderer
    rejects one as a build error rather than repairing it with an
    order-dependent suffix.
    """
    parts = [workflow, step]
    if suffix:
        parts.append(suffix)
    identity = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.blake2s(identity, digest_size=NODE_LABEL_DIGITS).hexdigest()
    return f"n-{digest[:NODE_LABEL_DIGITS]}"


def check_suffix(phase: str, kind: str, construct: str, local: str = "") -> str:
    body = f"{phase}-{kind}-{construct}"
    return f"{body}-{local}" if local else body


@dataclass
class _Anchor:
    """One source or generated node that checks attach to, with its own facts."""

    node: Node
    facts: NodeFacts
    prefix: str = ""


# --------------------------------------------------------------------------
# Lowering
# --------------------------------------------------------------------------


class Lowerer:
    """Lower one skill's reachable workflows into generated execution nodes."""

    def __init__(
        self,
        skill: Skill,
        sources: SourceSet,
        graphs: dict[str, WorkflowGraph],
        order: tuple[str, ...],
        callers: dict[str, tuple[str, str]],
        diagnostics: Diagnostics,
    ) -> None:
        self.skill = skill
        self.sources = sources
        self.graphs = graphs
        self.order = order
        self.callers = callers
        self.diagnostics = diagnostics
        self.records = sources.record_types()
        self.result = LoweredSkill(
            skill=skill, sources=sources, callers=callers, reached=order
        )
        self.primary = skill.primary_workflow

    # -- helpers ---------------------------------------------------------

    def error(self, workflow: Workflow, message: str, code: str) -> None:
        self.diagnostics.error(f"{workflow.path}: {message}", code, workflow.path)

    def lower(self) -> LoweredSkill:
        for identifier in self.order:
            workflow = self.sources.workflows.get(identifier)
            graph = self.graphs.get(identifier)
            if workflow is None or graph is None or not graph.usable:
                continue
            self.result.workflows.append(self._lower_workflow(workflow, graph))
        _resolve_transitions(self.result)
        return self.result

    def _lower_workflow(
        self, workflow: Workflow, graph: WorkflowGraph
    ) -> LoweredWorkflow:
        lowered = LoweredWorkflow(workflow=workflow, graph=graph)
        lowered.outcomes = (
            *(outcome.id for outcome in workflow.outcomes),
            BLOCKED_OUTCOME,
        )
        lowered.context = tuple(
            self.context_note(self.sources.guidance[use.id], use.inline)
            for use in workflow.guidance
            if use.id in self.sources.guidance
        )
        for use in workflow.guidance:
            if use.id in self.sources.guidance:
                self.result.used_guidance.add(use.id)
        steps = {step.id: step for step in workflow.steps}
        for identifier in graph.order:
            lowered.nodes.extend(
                self._lower_step(workflow, graph, steps[identifier])
            )
        entry = [node for node in lowered.nodes if node.step == workflow.entry]
        lowered.entry = entry[0].label if entry else ""
        return lowered

    # -- one source step -------------------------------------------------

    def _lower_step(
        self, workflow: Workflow, graph: WorkflowGraph, step: Step
    ) -> list[Node]:
        scopes = resolve_scopes(self.skill, workflow, step, self.diagnostics)
        self._register_bindings(scopes)
        frames = self._frames(workflow, step, scopes)
        emitted: list[Node] = []

        opening = [frame for frame in frames if self._opens_at(frame, workflow, step)]
        closing = [
            frame for frame in reversed(frames) if self._closes_at(frame, workflow, step)
        ]

        prefix: list[Node] = []
        for frame in opening:
            prefix.extend(self._boundary_hooks(workflow, graph, step, frame, "enter"))

        if step.form == "return":
            anchor = self._return_anchor(workflow, graph, step, scopes)
            prefix.extend(self._before(workflow, graph, step, scopes, frames, anchor))
            prefix.extend(
                self._phase_checks(
                    workflow, graph, step, scopes, anchor, "before-return", ""
                )
            )
            for frame in closing:
                prefix.extend(
                    self._boundary_hooks(workflow, graph, step, frame, "exit")
                )
                prefix.append(self._accepting_node(workflow, step, frame, ""))
            emitted.extend(prefix)
            emitted.append(anchor.node)
            _wire(prefix, anchor.node.label)
            return emitted

        anchors = self._anchors(workflow, graph, step, scopes)
        if not anchors:
            _wire(prefix, f"{STEP_PREFIX}{step.next}" if step.next else "")
            return prefix

        previous: list[Node] = []
        for index, anchor in enumerate(anchors):
            before = self._before(workflow, graph, step, scopes, frames, anchor)
            run = [*prefix, *before] if index == 0 else before
            # Pattern items initially point directly at the next procedure
            # node. Its before-checks are only known here, so redirect both the
            # previous item and any after-check tail before wiring this run.
            if run:
                for node in previous:
                    node.transitions = tuple(
                        replace(edge, target=run[0].label)
                        if edge.target == anchor.node.label else edge
                        for edge in node.transitions
                    )
            emitted.extend(run)
            emitted.append(anchor.node)
            _wire(run, anchor.node.label)
            prefix = []
            trailing = index == len(anchors) - 1
            edge_frames = closing if trailing else []
            after = self._after_edges(
                workflow, graph, step, scopes, frames, anchor, edge_frames
            )
            emitted.extend(after)
            previous = [anchor.node, *after]
        return emitted

    def _after_edges(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
        frames: list[Frame],
        anchor: _Anchor,
        closing: list[Frame],
    ) -> list[Node]:
        """Generate each outgoing edge's own `after` run, and rewire the edge.

        The edge key is part of every label in the run, so a decision's three
        choices produce three distinct checks, each stating the choice it
        follows.

        Edges are grouped by destination first. Two cases of one branch can
        route to the same step, and an `after` check precedes that step either
        way, so one run serves both: generating two would put two nodes under
        one label rather than checking anything twice.
        """
        emitted: list[Node] = []
        rewired: dict[str, str] = {}
        for target in dict.fromkeys(
            transition.target for transition in anchor.node.transitions
        ):
            transition = next(
                item for item in anchor.node.transitions if item.target == target
            )
            key = _edge_key(transition)
            run = self._phase_checks(
                workflow, graph, step, scopes, anchor, "after", key
            )
            for frame in closing:
                run.extend(
                    self._boundary_hooks(
                        workflow, graph, step, frame, "exit", edge=key
                    )
                )
                run.append(self._accepting_node(workflow, step, frame, key))
            if not run:
                continue
            _wire(run, target)
            emitted.extend(run)
            rewired[target] = run[0].label
        anchor.node.transitions = tuple(
            Transition(
                transition.label,
                rewired.get(transition.target, transition.target),
                blocked=transition.blocked,
            )
            for transition in anchor.node.transitions
        )
        return emitted

    def _before(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
        frames: list[Frame],
        anchor: _Anchor,
    ) -> list[Node]:
        return self._phase_checks(
            workflow, graph, step, scopes, anchor, "before", ""
        )

    # -- frames ----------------------------------------------------------

    def _frames(
        self, workflow: Workflow, step: Step, scopes: Scopes
    ) -> list[Frame]:
        frames: list[Frame] = []
        for scope, identifier in scopes.protocols:
            protocol = self.sources.protocols.get(identifier)
            if protocol is None:
                continue
            # A run frame is one frame for the whole run, so it carries no
            # workflow: naming the workflow it happens to be observed in would
            # make one frame look like several.
            frame = Frame(
                scope=scope,
                protocol=protocol,
                workflow="" if scope == "run" else workflow.id,
                step=step.id if scope == "step" else "",
            )
            frames.append(frame)
            if all(existing.key != frame.key for existing in self.result.frames):
                self.result.frames.append(frame)
        return frames

    def _opens_at(self, frame: Frame, workflow: Workflow, step: Step) -> bool:
        if frame.scope == "step":
            return True
        if frame.scope == "workflow":
            return step.id == workflow.entry
        return workflow.id == self.primary and step.id == workflow.entry

    def _closes_at(self, frame: Frame, workflow: Workflow, step: Step) -> bool:
        if frame.scope == "step":
            return True
        if step.form != "return":
            return False
        if frame.scope == "workflow":
            return True
        return workflow.id == self.primary

    # -- anchors ---------------------------------------------------------

    def _anchors(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
    ) -> list[_Anchor]:
        if step.form == "pattern":
            return self._expand_pattern(workflow, graph, step, scopes)
        node = self._source_node(workflow, graph, step, scopes)
        facts = NodeFacts(
            form=step.node_kind,
            subjects=step.subjects,
            effects=step.effects,
            call=step.call,
        )
        node.invariants = self._invariants(scopes, facts)
        return [_Anchor(node=node, facts=facts)]

    def _source_node(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
    ) -> Node:
        node = Node(
            label=node_label(workflow.id, step.id),
            kind=step.node_kind,
            command=step.command,
            workflow=workflow.id,
            step=step.id,
            source=f"workflow `{workflow.id}`, step `{step.id}`",
            available=self._reads(step),
            subjects=step.subjects,
            effects=step.effects,
            context=self._context(scopes),
            origin=step.form,
        )
        if step.form == "action":
            if step.resource is not None:
                node.resource_operation = step.resource.operation
                node.resource_path = step.resource.path
            node.produces = tuple(
                self._render_value(name, declared) for name, declared in step.produces
            )
            node.transitions = (
                Transition("On completion", f"{STEP_PREFIX}{step.next}"),
            )
        elif step.form == "branch":
            node.command = _branch_command(step)
            node.transitions = tuple(
                Transition(
                    f"When `{case.when.render()}`" if case.when else "Otherwise",
                    f"{STEP_PREFIX}{case.next}",
                )
                for case in step.cases
            )
        elif step.form in ("decide", "gate"):
            node.transitions = tuple(
                Transition(
                    f"`{option.id}` — {option.command}",
                    f"{STEP_PREFIX}{option.next}",
                )
                for option in step.options
            )
            node.consider = self._advice(step)
            node.heuristics = self._named_heuristics(step)
        elif step.form == "use":
            callee = self.sources.workflows.get(step.call)
            node.command = (
                callee.description
                if callee is not None
                else f"Run the workflow `{step.call}`."
            )
            node.call_workflow = step.call
            node.supplies = self._render_bindings(
                step.supplied, dict(callee.inputs) if callee is not None else {}
            )
            node.transitions = tuple(
                Transition(
                    f"Returns `{item.id}`"
                    + (f" as `result.{item.capture}`" if item.capture else ""),
                    f"{STEP_PREFIX}{item.next}",
                )
                for item in step.on
            )
        return node

    def _return_anchor(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
    ) -> _Anchor:
        outcome = workflow.outcome(step.outcome)
        record = (
            self.sources.records.get(outcome.record)
            if outcome is not None and outcome.record
            else None
        )
        node = Node(
            label=node_label(workflow.id, step.id),
            kind="return",
            command=_return_command(workflow, step, outcome),
            workflow=workflow.id,
            step=step.id,
            source=f"workflow `{workflow.id}`, step `{step.id}`",
            available=self._reads(step),
            subjects=step.subjects,
            effects=step.effects,
            outcome=step.outcome,
            supplies=self._render_bindings(
                step.supplied, record.types() if record is not None else {}
            ),
            context=self._context(scopes),
            origin="return",
        )
        facts = NodeFacts(
            form="return",
            subjects=step.subjects,
            effects=step.effects,
            outcome=step.outcome,
        )
        node.invariants = self._invariants(scopes, facts)
        return _Anchor(node=node, facts=facts)

    def _expand_pattern(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
    ) -> list[_Anchor]:
        self.result.applied_patterns.add((workflow.id, step.id))
        pattern = self.sources.patterns.get(step.pattern)
        if pattern is None:
            self.error(
                workflow,
                f"steps.{step.id}.pattern names {step.pattern}, which this skill "
                "does not select, so nothing expands here",
                "pattern.unexpanded",
            )
            return []
        self._check_pattern_inputs(workflow, graph, step, pattern)
        anchors: list[_Anchor] = []
        for index, item in enumerate(pattern.procedure):
            prefix = f"pattern-{pattern.id}-{item.id}"
            facts = NodeFacts(
                form="pattern",
                subjects=(*step.subjects, *item.subjects),
                effects=item.effects,
            )
            node = Node(
                label=node_label(workflow.id, step.id, prefix),
                kind="procedure",
                command=item.command,
                workflow=workflow.id,
                step=step.id,
                source=(
                    f"pattern `{pattern.id}`, procedure `{item.id}`, expanded at "
                    f"`{workflow.id}.{step.id}`"
                ),
                available=self._pattern_reads(step, item),
                pattern=pattern.id if index == 0 else "",
                subjects=facts.subjects,
                effects=facts.effects,
                supplies=self._render_bindings(step.supplied, dict(pattern.inputs))
                if index == 0
                else (),
                context=self._context(scopes) if index == 0 else (),
                origin="pattern",
            )
            node.invariants = self._invariants(scopes, facts)
            following = (
                node_label(
                    workflow.id,
                    step.id,
                    f"pattern-{pattern.id}-{pattern.procedure[index + 1].id}",
                )
                if index + 1 < len(pattern.procedure)
                else f"{STEP_PREFIX}{step.next}"
            )
            node.transitions = (Transition("On completion", following),)
            anchors.append(_Anchor(node=node, facts=facts, prefix=prefix))
        self.result.expanded_patterns.add((workflow.id, step.id))
        return anchors

    def _check_pattern_inputs(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        pattern: Pattern,
    ) -> None:
        environment = graph.environment(self.records, step.id)
        supplied = dict(step.supplied)
        declared_inputs = dict(pattern.inputs)
        for name, declared in pattern.inputs:
            binding = supplied.get(name)
            if binding is None:
                continue
            for problem in check_binding(binding, declared, environment):
                self.error(
                    workflow,
                    f"steps.{step.id}.with.{name}: {problem.message}",
                    problem.code,
                )
        for item in pattern.procedure:
            for reference in item.uses:
                if not reference.startswith("input."):
                    self.error(
                        workflow,
                        f"pattern {pattern.id} procedure {item.id} uses {reference!r}; "
                        "pattern reads must start with input.",
                        "pattern.invalid-use",
                    )
                    continue
                name = reference.split(".", 2)[1]
                if name not in declared_inputs:
                    self.error(
                        workflow,
                        f"pattern {pattern.id} procedure {item.id} uses input.{name}, "
                        "which the pattern does not declare",
                        "pattern.invalid-use",
                    )

    # -- checks ----------------------------------------------------------

    def _register_bindings(self, scopes: Scopes) -> None:
        for _, identifier in scopes.policies:
            policy = self.sources.policies.get(identifier)
            if policy is not None:
                for provision in policy.provisions:
                    self.result.bound_provisions.add((policy.id, provision.id))
        for _, identifier in scopes.rules:
            if identifier in self.sources.rules:
                self.result.bound_rules.add(identifier)
        for _, identifier in scopes.protocols:
            protocol = self.sources.protocols.get(identifier)
            if protocol is not None:
                for hook in protocol.hooks:
                    self.result.active_hooks.add((protocol.id, hook.id))

    def _phase_checks(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        scopes: Scopes,
        anchor: _Anchor,
        phase: str,
        edge: str,
    ) -> list[Node]:
        nodes: list[Node] = []
        after = phase == "after"
        for scope, identifier in scopes.policies:
            policy = self.sources.policies.get(identifier)
            if policy is None:
                continue
            for provision in policy.provisions:
                if provision.phase != phase:
                    continue
                if not provision.selector.matches(anchor.facts):
                    continue
                self.result.matched_provisions.add((policy.id, provision.id))
                nodes.append(
                    self._check_node(
                        workflow,
                        graph,
                        step,
                        anchor,
                        phase,
                        edge,
                        "policy",
                        policy.id,
                        provision,
                        scope,
                        local=provision.id,
                    )
                )
                self.result.lowered_provisions.add((policy.id, provision.id))
        for scope, identifier in scopes.rules:
            rule = self.sources.rules.get(identifier)
            if rule is None:
                continue
            provision = rule.provision
            if provision.phase != phase:
                continue
            if not provision.selector.matches(anchor.facts):
                continue
            self.result.matched_rules.add(rule.id)
            nodes.append(
                self._check_node(
                    workflow,
                    graph,
                    step,
                    anchor,
                    phase,
                    edge,
                    "rule",
                    rule.id,
                    provision,
                    scope,
                )
            )
            self.result.lowered_rules.add(rule.id)
        if phase in ("before", "after"):
            for frame in self._frames(workflow, step, scopes):
                for hook in frame.protocol.hooks:
                    if hook.phase != phase or hook.selector is None:
                        continue
                    if not hook.selector.matches(anchor.facts):
                        continue
                    nodes.append(
                        self._hook_node(
                            workflow,
                            graph,
                            step,
                            frame,
                            hook,
                            anchor.prefix,
                            edge,
                            after=after,
                        )
                    )
        return nodes

    def _check_node(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        anchor: _Anchor,
        phase: str,
        edge: str,
        kind: str,
        construct: str,
        provision: Provision,
        scope: str,
        local: str = "",
    ) -> Node:
        after = phase == "after"
        suffix = _compose_suffix(
            anchor.prefix, edge, check_suffix(phase, kind, construct, local)
        )
        environment = graph.environment(self.records, step.id, after=after)
        self._check_activation(workflow, provision, environment, construct, kind)
        origin = f"{kind} `{construct}`"
        if local:
            origin += f", provision `{local}`"
        where = f"{phase} `{workflow.id}.{step.id}`"
        if edge:
            where += f" via `{edge}`"
        return Node(
            label=node_label(workflow.id, step.id, suffix),
            kind="check",
            command=provision.command,
            workflow=workflow.id,
            step=step.id,
            source=f"{origin}, bound at {scope} scope, {where}",
            available=self._provision_reads(provision),
            subjects=anchor.facts.subjects,
            effects=anchor.facts.effects,
            verify=self._verification(
                workflow, graph, step, provision.verify, environment
            ),
            activation=_activation_line(provision),
            prohibits=provision.prohibits,
            transitions=(
                Transition("On success"),
                Transition("On failure", blocked=True),
            ),
            origin=f"{kind}:{construct}",
            provision=local,
            phase=phase,
        )

    def _hook_node(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        frame: Frame,
        hook: Hook,
        prefix: str,
        edge: str,
        *,
        after: bool,
    ) -> Node:
        suffix = _compose_suffix(prefix, edge, f"{frame.label}-{hook.id}")
        environment = graph.environment(
            self.records, step.id, after=after, state=frame.state_types()
        )
        if hook.when is not None:
            for problem in check_expression(hook.when, environment):
                self.error(
                    workflow,
                    f"protocol {frame.protocol.id}, hook {hook.id}, when: "
                    f"{problem.message}",
                    problem.code,
                )
        self._check_state_updates(workflow, frame, hook, environment)
        self.result.lowered_hooks.add((frame.protocol.id, hook.id))
        where = f"{hook.phase} `{workflow.id}.{step.id}`"
        if edge:
            where += f" via `{edge}`"
        activation = _hook_state_line(frame, hook)
        if hook.when is not None:
            activation += f" Active when `{hook.when.render()}`."
        return Node(
            label=node_label(workflow.id, step.id, suffix),
            kind="hook",
            command=hook.command or _verify_only_command(hook),
            workflow=workflow.id,
            step=step.id,
            source=(
                f"protocol `{frame.protocol.id}`, hook `{hook.id}`, "
                f"{frame.name}, {where}"
            ),
            available=self._hook_reads(hook),
            verify=self._verification(workflow, graph, step, hook.verify, environment),
            activation=activation,
            state_update=_state_update_line(hook),
            transitions=(
                Transition("On success"),
                Transition("On failure", blocked=True),
            ),
            origin=f"protocol:{frame.protocol.id}",
            frame=frame.label,
            hook=hook.id,
        )

    def _boundary_hooks(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        frame: Frame,
        phase: str,
        edge: str = "",
    ) -> list[Node]:
        return [
            self._hook_node(
                workflow, graph, step, frame, hook, "", edge, after=phase == "exit"
            )
            for hook in frame.protocol.hooks
            if hook.phase == phase
        ]

    def _accepting_node(
        self, workflow: Workflow, step: Step, frame: Frame, edge: str
    ) -> Node:
        protocol = frame.protocol
        accepting = ", ".join(f"`{name}`" for name in protocol.accepting)
        suffix = _compose_suffix("", edge, f"{frame.label}-accepting")
        return Node(
            label=node_label(workflow.id, step.id, suffix),
            kind="accepting",
            command=(
                f"Close the {frame.name} only from an accepting state: "
                f"{', '.join(protocol.accepting)}."
            ),
            workflow=workflow.id,
            step=step.id,
            source=(
                f"protocol `{protocol.id}`, accepting-state gate, {frame.name}, "
                f"before closing at `{workflow.id}.{step.id}`"
            ),
            verify=f"the frame's state is one of {accepting}.",
            transitions=(
                Transition("On success"),
                Transition("On failure", blocked=True),
            ),
            origin=f"protocol:{protocol.id}",
            frame=frame.label,
        )

    # -- fragments -------------------------------------------------------

    def _verification_reads(self, verify: Verification | None) -> set[str]:
        found: set[str] = set()
        if verify is None:
            return found
        if verify.kind == "expression" and verify.expression is not None:
            found.update(ref.render() for ref in references(verify.expression))
        elif verify.kind == "gate" and verify.gate:
            found.add(f"gate.{verify.gate}")
        return found

    def _provision_reads(self, provision: Provision) -> tuple[str, ...]:
        found = self._verification_reads(provision.verify)
        for expression in (provision.when, provision.unless):
            if expression is not None:
                found.update(ref.render() for ref in references(expression))
        return tuple(sorted(found))

    def _hook_reads(self, hook: Hook) -> tuple[str, ...]:
        found = self._verification_reads(hook.verify)
        if hook.when is not None:
            found.update(ref.render() for ref in references(hook.when))
        for _, binding in hook.updates:
            if binding.kind == "from" and binding.reference is not None:
                found.add(binding.reference.render())
        return tuple(sorted(found))

    def _reads(self, step: Step) -> tuple[str, ...]:
        """Values this source step actually reads, rather than every live value."""
        found = set(step.uses)
        for _, binding in step.supplied:
            if binding.kind == "from" and binding.reference is not None:
                found.add(binding.reference.render())
        if step.form == "branch":
            for case in step.cases:
                if case.when is not None:
                    found.update(ref.render() for ref in references(case.when))
        return tuple(sorted(found))

    def _pattern_reads(self, step: Step, item) -> tuple[str, ...]:
        """Translate a pattern procedure's declared reads through its bindings."""
        found = set(self._reads(step))
        supplied = dict(step.supplied)
        for text in item.uses:
            if not text.startswith("input."):
                found.add(text)
                continue
            parts = text.split(".")
            name = parts[1] if len(parts) > 1 else ""
            binding = supplied.get(name)
            if binding is not None and binding.kind == "from" and binding.reference is not None:
                mapped = binding.reference.render()
                if len(parts) > 2:
                    mapped += "." + ".".join(parts[2:])
                found.add(mapped)
        return tuple(sorted(found))

    def _available(
        self, graph: WorkflowGraph, step: str, *, after: bool = False
    ) -> tuple[str, ...]:
        keys = set(graph.available.get(step, frozenset()))
        if after:
            keys |= set(graph.produced.get(step, frozenset()))
        return tuple(f"{namespace}.{name}" for namespace, name in sorted(keys))

    def _render_value(self, name: str, declared: ValueType) -> str:
        return f"`{name}`: {declared.render()}"

    def _render_bindings(
        self,
        supplied: tuple[tuple[str, Binding], ...],
        expected: dict[str, ValueType],
    ) -> tuple[str, ...]:
        rendered: list[str] = []
        for name, binding in supplied:
            declared = expected.get(name)
            kind = f": {declared.render()}" if declared is not None else ""
            rendered.append(f"`{name}`{kind} from {binding.render()}")
        return tuple(rendered)

    def _verification(
        self,
        workflow: Workflow,
        graph: WorkflowGraph,
        step: Step,
        verify: Verification | None,
        environment: TypeEnvironment,
    ) -> str:
        if verify is None:
            return ""
        if verify.kind == "expression" and verify.expression is not None:
            for problem in check_expression(verify.expression, environment):
                self.error(
                    workflow,
                    f"steps.{step.id}: verify.expression: {problem.message}",
                    problem.code,
                )
            return f"`{verify.expression.render()}` is true."
        if verify.kind == "confirm":
            return verify.confirm
        return self._gate_verification(workflow, graph, step, verify.gate)

    def _gate_verification(
        self, workflow: Workflow, graph: WorkflowGraph, step: Step, gate: str
    ) -> str:
        if gate in self.sources.heuristics:
            self.error(
                workflow,
                f"steps.{step.id}: verify.gate names heuristic {gate}; a "
                "heuristic advises a choice and can never satisfy a binding check",
                "heuristic.used-as-authority",
            )
            return ""
        states = graph.gates.get(step.id, {}).get(gate)
        if states is None:
            self.error(
                workflow,
                f"steps.{step.id}: verify.gate names {gate}, which is not a gate "
                "every path to this node passes through, so the check has "
                "nothing to read",
                "workflow.missing-gate",
            )
            return ""
        rendered = ", ".join(f"`{name}`" for name in sorted(states))
        return f"`gate.{gate}` is {rendered}."

    def _check_activation(
        self,
        workflow: Workflow,
        provision: Provision,
        environment: TypeEnvironment,
        construct: str,
        kind: str,
    ) -> None:
        for label, condition in (
            ("when", provision.when),
            ("unless", provision.unless),
        ):
            if condition is None:
                continue
            for problem in check_expression(condition, environment):
                self.error(
                    workflow,
                    f"{kind} {construct} {label}: {problem.message}",
                    problem.code,
                )

    def _check_state_updates(
        self,
        workflow: Workflow,
        frame: Frame,
        hook: Hook,
        environment: TypeEnvironment,
    ) -> None:
        declared = frame.state_types()
        for name, binding in hook.updates:
            expected = declared.get(name)
            if expected is None:
                self.error(
                    workflow,
                    f"protocol {frame.protocol.id}, hook {hook.id}, sets "
                    f"state.{name}, which the protocol does not declare",
                    "protocol.invalid-state",
                )
                continue
            for problem in check_binding(binding, expected, environment):
                self.error(
                    workflow,
                    f"protocol {frame.protocol.id}, hook {hook.id}, set {name}: "
                    f"{problem.message}",
                    problem.code,
                )
        for name in hook.clears:
            expected = declared.get(name)
            if expected is None:
                self.error(
                    workflow,
                    f"protocol {frame.protocol.id}, hook {hook.id}, clears "
                    f"state.{name}, which the protocol does not declare",
                    "protocol.invalid-state",
                )
            elif expected.kind != "optional":
                self.error(
                    workflow,
                    f"protocol {frame.protocol.id}, hook {hook.id}, clears "
                    f"state.{name}, which is a {expected.render()} and must "
                    "always hold a value",
                    "protocol.invalid-state",
                )

    def _invariants(
        self, scopes: Scopes, facts: NodeFacts
    ) -> tuple[Invariant, ...]:
        """The `during` provisions and rules the node's own command is bound by.

        A `during` item renders on the command it constrains, and only an
        action, a call, a pattern procedure item, and a return carry one: a
        decision, a gate, and a branch state a choice rather than an action, so
        there is no command for an invariant to sit beside. The selector is
        matched here whatever the form, so a `during` item that selects only
        those three is recorded as matched and refused rather than looking like
        a selector that matched nothing. Reporting the difference is what tells
        the author the phase is wrong rather than the tag.
        """
        takes_invariant = facts.form in ("action", "call", "return", "pattern")
        found: list[Invariant] = []
        for _, identifier in scopes.policies:
            policy = self.sources.policies.get(identifier)
            if policy is None:
                continue
            for provision in policy.provisions:
                if provision.phase != "during":
                    continue
                if not provision.selector.matches(facts):
                    continue
                key = (policy.id, provision.id)
                self.result.matched_provisions.add(key)
                if not takes_invariant:
                    self.result.misphased_provisions.setdefault(key, facts.form)
                    continue
                self.result.lowered_provisions.add(key)
                found.append(
                    Invariant(
                        command=provision.command,
                        kind="policy",
                        construct=policy.id,
                        local=provision.id,
                        prohibits=provision.prohibits,
                    )
                )
        for _, identifier in scopes.rules:
            rule = self.sources.rules.get(identifier)
            if rule is None:
                continue
            provision = rule.provision
            if provision.phase != "during" or not provision.selector.matches(facts):
                continue
            self.result.matched_rules.add(rule.id)
            if not takes_invariant:
                self.result.misphased_rules.setdefault(rule.id, facts.form)
                continue
            self.result.lowered_rules.add(rule.id)
            found.append(
                Invariant(
                    command=provision.command,
                    kind="rule",
                    construct=rule.id,
                    local="",
                    prohibits=provision.prohibits,
                )
            )
        return tuple(found)

    def _named_heuristics(self, step: Step) -> tuple[str, ...]:
        return tuple(
            identifier
            for identifier in step.heuristics
            if identifier in self.sources.heuristics
        )

    def _advice(self, step: Step) -> tuple[str, ...]:
        lines: list[str] = []
        for identifier in step.heuristics:
            heuristic = self.sources.heuristics.get(identifier)
            if heuristic is None:
                continue
            self.result.used_heuristics.add(identifier)
            lines.extend(_advice_line(advice) for advice in heuristic.advice)
        return tuple(lines)

    def _context(self, scopes: Scopes) -> tuple[ContextNote, ...]:
        """The guidance one node carries, which is what its own step applied.

        Guidance bound for the run renders once at the top of the document, and
        guidance bound for a workflow once in that workflow's own header. Only a
        step's own application belongs on a node: repeating a run-level synopsis
        on every node of every workflow would bury the commands beside it under
        the same advice said forty times.
        """
        notes: list[ContextNote] = []
        for scope, use in scopes.guidance:
            unit = self.sources.guidance.get(use.id)
            if unit is None:
                continue
            self.result.used_guidance.add(use.id)
            if scope != "step":
                continue
            notes.append(self.context_note(unit, use.inline))
        return tuple(notes)

    def context_note(self, unit, inline: bool) -> ContextNote:
        return ContextNote(
            id=unit.id,
            summary=unit.summary,
            points=unit.points if inline else (),
        )


# --------------------------------------------------------------------------
# Chain wiring and small renderings
# --------------------------------------------------------------------------


def _wire(nodes: list[Node], exit_target: str) -> None:
    """Point each generated check at the next node, and the last at exit_target."""
    for index, node in enumerate(nodes):
        following = nodes[index + 1].label if index + 1 < len(nodes) else exit_target
        node.transitions = tuple(
            transition
            if transition.blocked or transition.target
            else Transition(transition.label, following)
            for transition in node.transitions
        )


def _compose_suffix(prefix: str, edge: str, body: str) -> str:
    parts = [part for part in (prefix, f"on-{edge}" if edge else "", body) if part]
    return "-".join(parts)


def _edge_key(transition: Transition) -> str:
    """A stable, label-safe name for one outgoing edge.

    Every key is a source id or a fixed word, never a position, because the key
    is part of a node label and a label built from source ids is what makes a
    rebuild byte-identical. A decision and a gate key on the option id, a call
    on the outcome it returns, and an action on completion.

    A branch case is the one edge the source gives no name: `when` is an
    expression rather than an id, and two cases would otherwise key alike. Its
    destination step is the only source id the case declares, so that is the
    key.
    """
    label = transition.label
    if label == "On completion":
        return "completion"
    if label.startswith("Returns `"):
        return label.removeprefix("Returns `").split("`", 1)[0]
    if label.startswith("`"):
        return label[1:].split("`", 1)[0]
    if label == "Otherwise" or label.startswith("When `"):
        return transition.target.removeprefix(STEP_PREFIX) or "edge"
    return "edge"


def _branch_command(step: Step) -> str:
    return (
        "Take the declared route whose condition holds for the values available "
        "here."
    )


def _return_command(workflow: Workflow, step: Step, outcome: Outcome | None) -> str:
    if outcome is None:
        return f"Return the outcome `{step.outcome}`."
    if outcome.record:
        return (
            f"Return the outcome `{outcome.id}` of workflow `{workflow.id}`, "
            "supplying every value below."
        )
    return f"Return the outcome `{outcome.id}` of workflow `{workflow.id}`."


def _activation_line(provision: Provision) -> str:
    parts: list[str] = []
    if provision.when is not None:
        parts.append(f"Active when `{provision.when.render()}`.")
    if provision.unless is not None:
        parts.append(f"Not active when `{provision.unless.render()}`.")
    return " ".join(parts)


def _hook_state_line(frame: Frame, hook: Hook) -> str:
    states = ", ".join(f"`{name}`" for name in hook.from_states)
    line = f"Runs from {states}."
    live = [item.name for item in frame.protocol.data]
    if live:
        line += " Live data: " + ", ".join(f"`state.{name}`" for name in live) + "."
    return line


def _state_update_line(hook: Hook) -> str:
    parts = [
        f"set `state.{name}` from {binding.render()}" for name, binding in hook.updates
    ]
    parts.extend(f"clear `state.{name}`" for name in hook.clears)
    if hook.to:
        parts.append(f"move to `{hook.to}`")
    return "; ".join(parts)


def _verify_only_command(hook: Hook) -> str:
    if hook.verify is not None and hook.verify.kind == "confirm":
        return hook.verify.confirm
    return "Establish that this frame's condition still holds here."


def _advice_line(advice: Advice) -> str:
    line = advice.prefer
    if advice.when is not None:
        line = f"When `{advice.when.render()}`: {line}"
    if advice.because:
        line += f" — {advice.because}"
    if advice.caution:
        line += f" Caution: {advice.caution}"
    return line


def _resolve_transitions(result: LoweredSkill) -> None:
    """Turn every step-marked destination into the node label it stands for.

    A source step names a step; the lowered graph enters that step at whichever
    generated node comes first in its chain, which is a check node wherever
    something is enforced before it. Resolving here, once every node exists,
    also lets each transition carry the destination's own command, so an agent
    reading a transition already knows what it is being sent to do.
    """
    for lowered in result.workflows:
        first: dict[str, str] = {}
        for node in lowered.nodes:
            first.setdefault(node.step, node.label)
        commands = {node.label: node.command for node in lowered.nodes}
        for node in lowered.nodes:
            resolved: list[Transition] = []
            for transition in node.transitions:
                target = transition.target
                if target.startswith(STEP_PREFIX):
                    target = first.get(target.removeprefix(STEP_PREFIX), "")
                resolved.append(
                    Transition(
                        transition.label,
                        target,
                        commands.get(target, ""),
                        blocked=transition.blocked,
                    )
                )
            node.transitions = tuple(resolved)
