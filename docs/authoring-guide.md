# Authoring skills

This guide takes you from an empty directory to a validated, inspectable
bundle. It starts with a minimal `my-skill` source, then adds each construct
using the repository's public
[`structured-summary`](../examples/structured-summary/) example. For exact field
constraints, see the [reference](reference.md).

## 1. Start with one outcome

Give your skill one outcome it can complete without another installed skill.

`structured-summary` owns turning supplied material into a summary for a defined
reader and purpose. The material can be about any subject.

Use a lowercase, hyphenated name. The directory name and the manifest `name`
must match. Write the description as an ordinary request, so an agent host can
recognize when the skill applies:

```yaml
name: structured-summary
description: Turn supplied material into a clear, audience-appropriate summary.
```

Keep execution instructions out of the description. They belong in the workflow
and in the constructs that bind it.

## 2. Create the smallest source that runs

Start with two files:

```text
my-skill/
  skill.yaml
  workflows/
    run.yaml
```

Create `my-skill/skill.yaml`:

```yaml
name: my-skill
format_version: 2
version: 0.1.0
description: Turn supplied notes into a concise action list.
primary_workflow: run
content:
  workflows:
  - workflows/*.yaml
interface:
  display_name: My Skill
  short_description: Turn notes into an action list
  default_prompt: Use {name} to turn these notes into an action list.
```

Create `my-skill/workflows/run.yaml`:

```yaml
title: Turn notes into an action list
description: Read the supplied notes and report the actions they commit someone to.
inputs:
  notes:
    type: string
outcomes:
  listed: {}
entry: read-notes
steps:
  read-notes:
    action: Identify every task, owner, deadline, and unresolved decision the
      notes state.
    uses: [input.notes]
    produces:
      actions:
        type: {list: string}
    next: report

  report:
    action: Write the actions as a checklist, and invent no detail the notes do
      not state.
    next: done

  done:
    return:
      outcome: listed
```

From the directory that contains `my-skill/`, verify the source and build its
first artifact:

```console
degardis validate my-skill
degardis build my-skill --output .artifacts
```

Success creates two generated Markdown files. `.artifacts/my-skill/SKILL.md` is
the control plane; it loads `execution/run-01.md`, which carries one node per
step, each headed by the command that step performs. Open both, in that order, to
see what an agent reads. Keep editing the YAML source, then validate and rebuild.
Generated files are replaceable output.

That is the whole of what is required: a manifest, `content.workflows`, and one
workflow whose every path terminates. Add a construct when it earns its place.

## 3. Write `skill.yaml`

The example manifest begins:

```yaml
name: structured-summary
format_version: 2
version: 1.0.0
license: MIT
copyright: Copyright (c) 2026 Example Organization
description: Turn supplied material into a clear, audience-appropriate summary.
primary_workflow: compose
guidance:
- clear-reporting
content:
  policies:
  - policies/*.yaml
  rules:
  - rules/*.yaml
  patterns:
  - patterns/*.yaml
  heuristics:
  - heuristics/*.yaml
  guidance:
  - guidance/*.yaml
  protocols:
  - protocols/*.yaml
  records:
  - records/*.yaml
  workflows:
  - workflows/*.yaml
  profiles:
  - profiles/*.yaml
  references:
  - references/**/*.md
  scripts:
  - scripts/*.py
  assets:
  - assets/*.md
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  brand_color: '#5B4B8A'
  default_prompt: Use {name} to summarize this material.
```

The two version fields mean different things. `format_version` selects the
Degardis source contract, and is `2`. `version` identifies your authored skill.

`content` says what the skill ships; the top-level `policies`, `rules`,
`protocols`, and `guidance` keys say what binds for the whole run. The example
ships one policy but binds it on the workflow rather than the run, and binds one
guidance unit for the run — which is why `content.policies` is present and a
top-level `policies` is not.

Declare a content key only for files the skill really ships. A key you declare
must select at least one file, and every pattern in it must match something, or
validation fails. This is deliberate: a misspelled pattern is otherwise
invisible, because the bundle it produces looks complete.

The three required interface fields serve different readers:

- `display_name` labels the skill in an agent interface, and is the heading of
  the generated `SKILL.md`. It is the only human-readable name the manifest
  declares.
- `short_description` is the interface summary; over 60 characters warns, because
  a host listing many skills shows about that much.
- `default_prompt` is a suggested invocation. Because hosts differ in how a skill
  name is typed, write the exact `{name}` placeholder and let each target render
  it. Spelling one host's syntax, such as `$my-skill`, is an error; naming no
  skill at all is a warning.

The top-level `description` is different again: an agent host uses it to decide
when the skill applies. Keep it specific even where the interface summary is
shorter.

## 4. Express the procedure as a typed workflow

A workflow is a graph, not a list of prose steps. It declares what it is given,
what it can return, and one step per boundary where something happens.

```yaml
inputs:
  material:
    type: string
  reader:
    type: string
outcomes:
  delivered:
    record: summary-result
  no-summary: {}
entry: establish-purpose
```

Every reachable path has to reach a `return`, and every return names a declared
outcome. `blocked` is declared for you: it is the outcome every binding check
returns when it cannot be satisfied, and your source may not declare or return
it.

Each step names exactly one form:

| Form | Use it when |
| --- | --- |
| `action` | the agent does one thing and may produce a value |
| `decide` | the agent chooses among named alternatives |
| `gate` | the agent reaches one of an exhaustive set of states |
| `branch` | a declared expression decides the route, with no judgment |
| `use` | another workflow in this skill does the next part |
| `pattern` | a reusable procedure does the next part |
| `return` | the workflow ends with a declared outcome |

Values flow through declared names, not through the agent's memory. An `action`
declares what it `uses` and what it `produces`; a later step reads the result as
`result.<name>`:

```yaml
inspect-material:
  action: Inspect the supplied material for its subjects, its main claims, and
    the gaps that limit a faithful summary.
  uses: [input.material]
  subjects: [material.inspect]
  produces:
    inspection:
      record: material-inspection
  next: check-readiness
```

Degardis checks that flow: a value read before it is definitely assigned is an
error, an optional value read without an `exists` guard is an error, and a
mistyped binding is an error. That is what makes `result.inspection.gaps` safe to
name in a later step and in a rule's condition.

A `decide` and a `gate` both retain what was chosen — as `decision.<step-id>` and
`gate.<step-id>` — so a later branch or a rule's condition can read it. Each
needs at least two alternatives, because a closed judgment with one answer
decides nothing:

```yaml
check-readiness:
  gate: Decide whether the inspected material supports a faithful summary.
  heuristics: [smallest-sufficient-detail]
  states:
    ready:
      command: Compose the summary from the inspected material.
      next: choose-depth
    insufficient:
      command: Report what is missing instead of summarizing.
      next: describe-gaps
```

Every command you write becomes the heading of a generated node, so write it as
an instruction that stands alone. A heading that reads as a topic rather than an
action is reported.

Split a second workflow out with `use` when a region of the procedure is
independently describable, and map every outcome it declares:

```yaml
describe-gaps:
  use: report-gaps
  with:
    gaps: {from: result.inspection.gaps}
  subjects: [gap.report]
  on:
    reported: no-summary
```

The called workflow gets its own module under `execution/`, and the call renders
as a mandatory load of that module at the callee's exact entry node: if the
module cannot be read, the run returns `blocked` rather than guessing at the
callee from its title. A workflow nothing calls warns, and a cycle among calls
is an error.

## 5. Choose the construct by how it binds

Format 2 has distinct constructs because they have distinct execution meanings.
Classify material by how it binds, not by what it has always been called:

| Material | Construct | Binding |
| --- | --- | --- |
| a standing authoritative boundary, with several related provisions | policy | every active provision binds |
| one conditional relation: when X holds, require or prohibit Y | rule | binds when triggered |
| a requirement with lifecycle state carried across steps | protocol | binds while the frame is active |
| a reusable way to perform a bounded procedure | pattern | only where a step selects it |
| a preference among valid options, defeasible by context | heuristic | never binds |
| explanatory or quality-improving context | guidance | never binds |
| situational supplementary material selected at run time | profile | never binds |

A binding principle is a policy. A conditional constraint is a rule. A defeasible
principle is a heuristic. An explanatory principle is guidance. There is no
separate schema for a principle or a constraint.

The precedence is fixed and cannot be reordered by a source. The workflow graph
and its outcome contracts determine what can execute; policies constrain that;
rules add narrower conditional constraints; protocols add lifecycle checks;
selected patterns supply a method inside what is permitted; heuristics advise;
guidance informs. An exception to a policy or a rule belongs in that construct's
own `unless` or in a narrower `match` — never in a later advisory item.

## 6. Bind policies and rules with selectors and phases

A policy or a rule does not name the steps it applies to. It declares a
selector over the tags a step carries, and a phase saying where the check sits.

Tag the steps first. `subjects` and `effects` are opaque labels; Degardis never
reads meaning into their words, which is what keeps a provision's reach stable
as prose is reworded:

```yaml
inspect-material:
  subjects: [material.inspect]
write-summary:
  subjects: [summary.write]
  effects: [workspace.write]
```

Then write the provision against those tags:

```yaml
title: Faithfulness to the supplied material
summary: Keep every claim the summary makes inside what the material supports.
provisions:
  establish-support:
    phase: before
    match:
      subjects: [summary.write]
    require: Establish, for each claim you are about to write, the part of the
      material that supports it.
    verify:
      gate: check-readiness
  no-invented-claim:
    phase: during
    match:
      subjects: [summary.write]
    prohibit: State a claim the supplied material does not support.
  report-limitations:
    phase: before-return
    match:
      forms: [return]
    require: Report the limitations that affect how this result may be used.
```

The phase decides what the reader sees. `before`, `after`, and `before-return`
become generated check nodes with a success transition and a `blocked`
transition. `during` becomes an invariant rendered on the node itself — a
`Required:` or `Prohibited:` line beside the command it constrains. Choose
`during` where the requirement shapes how the action is performed, and `before`
where something must be established first.

Only a step that states an action carries an invariant: an `action`, a `use`, a
`pattern`, and a `return`. A `decide`, a `gate`, and a `branch` state a choice,
so there is no command for a `Required:` line to sit beside. A `during`
provision or rule whose selector reaches only those three is enforced nowhere,
and validation reports it as an error naming the phase. Use `before` to check
something ahead of a choice.

Write a `forms` selector in node kinds rather than step forms: a `use` step is
selected as `call` and a `decide` step as `decision`. Naming the step form is an
error, and the message lists the seven node kinds.

Two provisions may select the same steps at the same phase, one requiring and
one prohibiting. That is how a boundary is written — establish the scope of a
write, then stay inside it — and it compiles clean. The only conflict validation
reports is one command both required and prohibited at one step and one phase
(`workflow.conflicting-obligation`), where no reading of the node satisfies
both. Whether two differently worded commands disagree is yours to see:
Degardis does not read the prose, and an `effects` selector is compared exactly
like a `subjects` one, so there is no separate effect-level conflict.

**A selector that matches nothing is a warning, and the warning is the useful
part.** Add a policy whose `match` names a subject no step declares and
validation says so:

```text
Warning: policies/notes-fidelity.yaml:
         provision no-invented-action is bound and its selector (subject checklist.write)
         matches no reachable during node, so nothing enforces it
         (policy.unmatched-provision)
```

Tag the step, and the provision appears in the generated node:

```markdown
**Subjects:** `checklist.write`
**Prohibited:** List an action the notes do not commit anyone to. (policy `notes-fidelity`, provision `no-invented-action`)
```

Bind each construct at the scope that holds it — the manifest for the whole run,
a workflow for that workflow, a step for that step. Binding one construct twice
at nested scopes is an error, because the narrower binding says nothing the wider
one has not already said.

Use a rule rather than a policy provision when the material is one conditional
relation. A rule is atomic: one file, one relation, one id, one diagnostic
identity. Its condition is a declared expression, not prose:

```yaml
title: Give a multi-subject summary a navigable structure
summary: Material covering more than one subject needs headings a reader can scan.
phase: before
match:
  subjects: [summary.write]
when: length(result.inspection.subjects) > 1
require: Group the summary under one heading per subject, and name each heading
  after the subject it covers.
verify:
  confirm: Each heading names one subject the material covers, and no heading
    covers two.
```

Write `when` over values the workflow actually declares. That is the difference
between a condition an agent can settle at the node and a qualifier it would have
to reconstruct: `length(result.inspection.subjects) > 1` reads a value an earlier
step produced. A qualifier that cannot be expressed over declared values is part
of the requirement, and belongs in the `require` sentence itself.

`verify` says how the check is discharged, and takes one of three forms: an
`expression` over declared values, a `gate` whose state the check reads, or a
`confirm` sentence the agent confirms. A `gate` has to dominate the node it
verifies — every path to the check must pass through that gate — or the
verification would name a state that may not exist.

## 7. Use a protocol only for state that crosses steps

A protocol is for an obligation that is opened at one step and discharged at
another. If the requirement is satisfied where it is stated, it is a policy
provision or a rule, and a protocol would only add states nothing reads.

The example inspects material at one step and writes from it several steps
later, so it declares where that evidence lives:

```yaml
title: Evidence trail
purpose: Keep the inspected evidence available until the result has used it.
states: [empty, held, spent]
initial: empty
accepting: [empty, spent]
data:
  evidence:
    type: {optional: {record: material-inspection}}
    initial: {literal: null}
hooks:
  hold-evidence:
    phase: after
    match:
      subjects: [material.inspect]
    from: [empty]
    command: Keep the inspected subjects, claims, and gaps available for
      whatever uses them next.
    set:
      evidence: {from: result.inspection}
    to: held
  spend-on-review:
    phase: before
    match:
      subjects: [summary.review]
    from: [held]
    command: Check the draft against the evidence you kept.
    clear: [evidence]
    to: spent
```

`accepting` is the part that does work. Degardis inserts a gate before the frame
closes, so a run that reached `held` and never spent the evidence cannot return
an outcome — it blocks and says which state it was in. Declare a state as
accepting only where closing from it is genuinely finished.

Every hook has to be reachable: a `from` state that cannot hold where the hook is
lowered is an error, a state no hook can reach is an error, and a frame from
which no accepting state is reachable is an error. Those checks are why a
protocol replaces a prose ledger — the states are proven to line up with the
graph rather than left to the agent to track.

Choose the frame's scope by what the state is about. The manifest opens one frame
for the run, a workflow opens one per invocation, and a step opens one for that
reached step.

## 8. Add a pattern, a heuristic, or guidance

**A pattern is a reusable method a step selects.** It is not available-by-default
and is never matched by guessing:

```yaml
title: Outline, then draft
summary: Order the selected content before writing it, so the draft follows a
  shape the reader can scan.
inputs:
  inspection:
    type: {record: material-inspection}
  depth:
    type: {enum: [brief, detailed]}
procedure:
  select-content:
    command: Choose the claims and qualifications the reader's purpose needs.
    uses: [input.inspection]
  order-content:
    command: Order the selected content so context precedes the conclusions
      drawn from it.
  draft:
    command: Write the ordered content plainly, in the terms the intended reader
      already uses.
    subjects: [summary.write]
```

```yaml
write-summary:
  pattern: outline-then-draft
  with:
    inspection: {from: result.inspection}
    depth: {from: decision.choose-depth}
  rules:
  - structure-subjects
  next: review-summary
```

Each procedure item becomes one generated node in the caller, so the reader gets
the procedure inline and nothing links to a pattern page. Tag procedure items
with `subjects` where a policy or a rule should reach them — that is how
`summary.write` on the `draft` item pulls the policy's provisions and the step's
rule onto the right node. A procedure item cannot branch, call, return, declare
effects, or produce workflow values; a workflow is the construct for that.

**A heuristic advises a choice and can never become authority.** Only a `decide`
or a `gate` may name one, and its advice renders on that node under `Consider`:

```yaml
title: Prefer the smallest sufficient detail
question: How much detail should this summary carry?
advice:
  reader-decision:
    prefer: Prefer the detail that changes what the reader decides.
    because: Detail a reader cannot act on costs attention and adds nothing.
  qualification-first:
    when: length(result.inspection.gaps) > 0
    prefer: Prefer stating a qualification over dropping it to save space.
    caution: A qualification restated in every section reads as hedging.
```

Naming a heuristic in a `verify`, on an action, or anywhere else is refused, and
so is using one to discharge a binding check. If the material must hold, it is a
policy provision or a rule, not advice.

**Guidance is context that never binds.** Its `summary` is one sentence rendered
wherever it is applied:

```yaml
title: Clear reporting
summary: Lead with the result, and state the limitations that affect how it may
  be used.
points:
- Distinguish what the material states from what you inferred from it.
- Name a subject you could not summarize instead of leaving it out silently.
```

Apply it at the scope where it helps — the manifest for the whole run, a
workflow, or a step. Ask for `detail: inline` where the points are worth carrying
on the node itself:

```yaml
guidance:
- guidance: clear-reporting
  detail: inline
```

Never put a required action in guidance `points` or in a reference file. Guidance
is non-binding wherever it renders. Author-only explanation does not need a
source-language field: keep rationale, examples, and maintenance notes as YAML
comments.

## 9. Add profiles as independent auxiliary guidance

Author the core skill without profiles in mind. A workflow never selects, reads,
or waits for a profile. Profiles only make already-valid execution a little more
efficient, idiomatic, or context-aware. Anything whose absence could make the
result invalid belongs in the core workflow, a policy, a rule, or a protocol.

A profile says what it is for and what it contributes:

```yaml
title: Concise result
description: Apply where the reader needs the shortest summary that still carries
  the decision.
points:
- Keep only the detail that changes the reader's decision.
- Lead with the result, and put the qualifications that bound it beside it.
```

Only `points` is required. Write the `description` for an agent deciding whether
to open the page: name the situation the profile applies to, not the advice it
carries. Nothing in the compiler reads meaning into it, so it is prose rather
than a state predicate or a taxonomy.

The compiler generates a constant-size root hint plus `profiles/index.md`, which
lists every profile with its description and a link to its page. A profile that
declares no description contributes its title alone, which leaves an agent
guessing from a name. Retrieval remains best-effort either way: a miss or a false
positive cannot affect validity.

Where a profile needs structured Markdown, list files under `guides`; they are
appended to the generated advisory page. A guide path is relative to the profile
file, so the example's `detailed` profile names `guides/detailed.md` for
`profiles/guides/detailed.md`. Keep guide paths inside the skill, use `.md`, and
start below level one because the generated page supplies its title.

Always keep `content.profiles` scoped to profile YAML files rather than sweeping
up guide Markdown. Profiles cannot declare policies, rules, protocols, or
workflows, and no workflow may reference a profile. Deleting every profile and
profile index from the compiled artifact must leave the valid execution set
unchanged.

## 10. Declare records for values with more than one part

A record gives a produced or returned value a typed shape, so the steps that read
it can name its fields:

```yaml
title: Material inspection
fields:
  subjects:
    type: {list: string}
    description: The distinct subjects the material covers.
  claims:
    type: {list: string}
    description: The main claims the material makes.
  gaps:
    type: {list: string}
    description: Missing context or contradictions that limit a faithful summary.
```

Record fields render inline where a value is produced, supplied, or returned, so
no record page is generated and the agent never opens one. Declare a record where
a later step, a rule's condition, or an outcome needs one of the parts by name —
`result.inspection.gaps` is only readable because `material-inspection` declares
`gaps`. A single-part value needs no record; declare its type directly.

## 11. Use scripts, assets, and references deliberately

Scripts are executable helpers. Assets are inputs an agent reads, copies, or
fills in. References are Markdown pages that explain, and can never be required.

The example ships:

- `scripts/list_headings.py`, a deterministic helper that exposes the structure
  of Markdown material;
- `assets/template.md`, a starting structure for the summary;
- `assets/icon.svg`, a source image for the interface icon;
- `references/**/*.md`, examples for the pattern, the heuristic, and the guidance
  unit.

When a script is required for correctness, declare it as the step's typed
`resource` operation. The generated execution node names the exact script and
fails closed if the operation is unavailable or fails. Test every script with
representative input.

References are non-binding support. Patterns, heuristics, and guidance may name
reference material explicitly; policy/rule rationale, examples, tradeoffs, notes,
and free-form `details` are not source fields. Keep author-only explanation in
YAML comments instead of generating pages an agent has no reason to read.

Content globs must stay inside the skill directory. Icon paths are the
exception: a relative icon path may resolve outside the skill so several skills
can share a source image, and the bundle stays self-contained because Degardis
rasterizes and copies the result.

You can keep drafts and working notes next to the files you ship. Start a pattern
with `!` to leave them out, instead of narrowing the include pattern until it
happens to fit:

```yaml
content:
  assets:
  - assets/**/*
  - "!assets/drafts/**/*"
```

Degardis reads the patterns from top to bottom, so a pattern below an exclusion
can bring a file back. Always put quotes around a pattern that starts with `!`,
or YAML treats it as a tag.

Write every pattern with `/` between its parts, and match the upper and lower
case of your directory and file names exactly. `!Assets/drafts/**/*` excludes
nothing from a directory named `assets`, even on Windows and macOS, where the
computer itself ignores case. Degardis reports a pattern that matches nothing, so
such a mistake fails validation instead of shipping different files on different
computers.

Some files need no exclusion. Degardis never ships Python bytecode or the files
your operating system creates for itself, and it leaves out anything the
filesystem marks hidden and anything inside a directory whose name starts with a
dot — though not a file whose own name starts with one.

See [Content configuration](reference.md#content-configuration) for the full
pattern rules.

## 12. Quote a YAML value that means the text

Format 2 accepts a deliberately small YAML profile, and the loader refuses
anything that makes the value it reads differ from the text on your page: a
duplicate key, an anchor, an alias, a merge key, a tag, a bare date, a
non-finite number, a non-string field name.

Three values load exactly as YAML says and still surprise their author, so they
warn:

```yaml
summary: "no"        # unquoted, this is the boolean false
version: "1.10"      # unquoted, this is the number 1.1
window: "1:30"       # unquoted, this is 90 seconds
```

A field name is read as text either way, so `on:` in a `use` step is the field,
not a boolean.

## 13. Validate, build, and inspect

Validate your source without writing output:

```console
degardis validate my-skill
```

One run reports every finding it can reach, and every finding names the check
behind it. When a message alone does not say why the problem matters, ask:

```console
degardis explain policy.unmatched-provision rule.unlowered
```

Review metadata and available profiles:

```console
degardis list my-skill
```

Then check what the source compiled to, rather than what it declared:

```console
degardis inspect my-skill --only lowering
degardis inspect my-skill --only execution
degardis inspect my-skill --only attention
```

- `lowering` names each binding construct and the generated node it reached.
  `not-lowered` on any row means a requirement your source declares reached no
  step.
- `execution` lists every node with its transitions, which is the graph an agent
  will actually walk.
- `attention` sizes what an agent has to load: the control plane, the execution
  modules, and the supplementary material beside them.

`degardis inspect my-skill --all` answers all of this in one command, and
`--body-text` appends the generated `SKILL.md` so you can read it without
building. Add `--fail-on-warning` where a finished skill must carry no warning.

Then build:

```console
degardis build my-skill --output .artifacts
```

Read the generated `SKILL.md` and every module under `execution/` at least once
for a skill you intend to ship. What you are checking is what no check can: that
each command reads as an instruction at the point it appears, that the
requirements landed at the boundaries you meant, and that each module makes sense
read top to bottom by an agent that has never seen your source and holds nothing
but the module it was told to load.

Run the bundled scripts with representative input as a separate check. Degardis
verifies source structure and generated references, and never executes a script.
Also exercise ZIP output when it is a distribution format:

```console
degardis build my-skill --zip --output .artifacts
```

## Final checklist

- The directory and manifest names match, and `format_version` is `2`.
- The description states one recognizable outcome.
- Every reachable path through every workflow ends at a declared outcome.
- Every value a step reads is declared and produced before it.
- Each construct is the kind that matches how it binds: a policy for a standing
  boundary, a rule for one conditional relation, a protocol for state that
  crosses steps, a pattern for a reusable method, a heuristic for a preference,
  guidance for context.
- Each construct is bound at the scope that holds it, and no construct is bound
  twice.
- Every command reads as an instruction that stands alone where it renders.
- Every rule and provision matched a reachable node — no
  `policy.unmatched-provision` or `rule.unmatched` warning remains
  undispositioned.
- Every protocol frame can close in an accepting state on every path.
- No requirement lives in a heuristic, in guidance, in a profile, or in a
  reference page.
- Deleting `references/` and `profiles/` from the built bundle leaves it
  executable; `SKILL.md` and `execution/` are the whole of required execution.
- Scripts are necessary and tested; assets are genuine inputs.
- `degardis validate` succeeds, and `degardis inspect --only lowering` shows
  every binding construct lowered.
- Folder and ZIP artifacts contain only expected files.
