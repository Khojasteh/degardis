# Concepts

Degardis separates an editable skill source from the bundle it generates:

```text
skill source -> check -> lower -> render and copy -> folder or ZIP
```

Checking covers the source's declarations and the relations between them. Lowering
turns every binding declaration into the workflow location where it is enforced.
Rendering writes a compact `SKILL.md`, required `execution/` modules, plus supplementary explanation
pages, the interface metadata, and the files the manifest selects for copying.
The source remains the authoritative version.

## Skill

A skill is Degardis's top-level unit. It is independently buildable,
installable, and usable:

```text
skill-name/
  skill.yaml
  policies/
  rules/
  patterns/
  heuristics/
  guidance/
  protocols/
  records/
  workflows/
  profiles/
  references/
  scripts/
  assets/
```

The manifest supplies the source-format version, the skill name and version, a
description that helps an agent host decide when the skill applies, the primary
workflow, the constructs that bind for the whole run, the patterns that select
every file the skill ships, and agent-facing interface metadata.

Those directory names are a convention. A bundle carries only what `content`
selects, and Degardis infers no construct kind from a directory name: the
manifest key that selected a file decides which schema the file must satisfy. A
directory Degardis is not told about is not part of the skill.

Each selected YAML file defines one construct, and its lowercase-hyphenated file
stem is that construct's id. Nothing declares an id in its content, so moving a
file preserves its identity and renaming it changes it.

The format version selects the compiler contract. The skill version identifies
the authored content; it is not dependency-resolution metadata.

Skills have no build-time dependencies. Selecting one skill selects exactly that
skill, and a workflow cannot call into another skill, because the other skill may
not be installed. Degardis controls the bundle it emits; the agent host decides
how to use an installed skill at runtime.

## The portable execution contract

The generated bundle has two execution layers. `SKILL.md` is a compact control
plane that defines the execution contract and the initial required load. Reachable
workflow bodies live in compiler-generated files under `execution/`.

Required execution crosses a file boundary only where the compiler put a
boundary, and every crossing says exactly which file to read and what to do on
arrival. An agent never decides from a filename whether a file matters, and a
file it cannot read stops the run rather than being worked around.

Module boundaries are chosen for repeated execution. The compiler compares
partitions and valid node orders to reduce the most text a path from the primary
entry must load. Separating mutually exclusive branches can save reading even
when it creates more files. Ties prefer fewer required loads, then fewer total
execution bytes. Every required node and transition stays in place in the
execution graph; only its document location can change.

The search is deterministic and bounded, so it does not promise a global optimum.
It retains an improvement only after measuring the complete rendered layout,
including headers and boundary instructions. It assumes no branch frequencies
or host caching: each workflow invocation pays for its loads, and a call follows
only the continuation matching its returned outcome. `inspect --only attention`
reports worst-path execution bytes and load counts separately. These are
structural upper bounds, not token counts or predictions of elapsed time.

References and profiles are outside that execution contract. They are auxiliary only:
removing them cannot change requirements, valid transitions, failure conditions, or
valid outputs. Profiles may improve efficiency or tailoring where their descriptions
match the work the agent already has in front of it, and more than one can match.

Degardis does not claim that Markdown forces compliance. It guarantees structural
reachability, explicit load boundaries, and that required behavior is not hidden in an
auxiliary file.

## The nine constructs

Format 2 uses distinct constructs because they have distinct execution meanings.
A single generic list would leave every difference to prose:

| Construct | What it is | Binding |
| --- | --- | --- |
| Workflow | Ordered control flow with declared inputs, values, calls, and outcomes | yes |
| Policy | A standing authoritative boundary, carrying related provisions | every active provision |
| Rule | One conditional relation: when a condition holds, require or prohibit one behavior | when triggered |
| Protocol | A stateful lifecycle around a run, a workflow invocation, or one step | while the frame is active |
| Pattern | A reusable way to perform a bounded procedure | only where a step selects it |
| Heuristic | A defeasible aid for choosing among valid options | never |
| Guidance | Supplementary context or advice | never |
| Profile | Independently discoverable auxiliary guidance | never |
| Record | A typed shape for a retained value | structural |

Classify material by how it binds rather than by what it has been called. A
binding principle is a policy; a conditional constraint is a rule; a defeasible
principle is a heuristic; an explanatory principle is guidance.

Precedence between them is fixed and no source can reorder it. The workflow graph
and its outcome contracts determine what can execute. Policies constrain that
execution. Rules add narrower conditional constraints. Protocols add lifecycle
checks and state transitions. A selected pattern supplies a method inside what is
already permitted. Heuristics advise. Guidance informs.

So an exception to a policy or a rule has to live in that construct's own
condition or in a narrower selector. A heuristic, a guidance unit, or a profile
cannot waive anything, and a rule cannot authorize what a policy prohibits.

## Obligation, and where it is enforced

An obligation is not something a source declares. It is one binding runtime
instance the compiler derives, from exactly one of: a workflow input, gate,
effect, or outcome contract; a matching policy provision; a triggered rule; or an
active protocol hook or accepting-state check.

A pattern, a heuristic, a guidance unit, and a profile create no obligation by
being available. That is what makes them safe to ship in quantity: a large
optional library sits beside a small executable core rather than inside it.

Selection is declared, not inferred. A policy provision, a rule, and a protocol
hook each carry a selector over the tags a step declares — its `subjects`, its
`effects`, its form, the workflow it calls, the outcome it returns. Nothing
matches a title, a description, a command, or any natural-language similarity, so
what a provision reaches cannot drift as prose is reworded, and you can read from
the source which steps you have selected.

A phase says where the check sits: ahead of the node it constrains, on it as an
invariant, on each edge leaving it, or ahead of a return.

## Lowering

Lowering is what turns those declarations into a document an agent can execute
without holding anything in mind. Each generated node carries exactly what
applies at that boundary: the command, the active invariants, the values
available, the verification, the state update, and the transitions. An agent is
never asked to work out which requirements apply, or to carry a ledger of open
obligations from one step to the next.

Every binding check has an explicit failure disposition. Unless the workflow
declares a recovery branch ahead of it, a check that cannot be satisfied stops
the run and reports what failed, rather than letting it continue past a
requirement. Advisory items never cause that.

Because of that, a requirement that reached no node is a reported failure rather
than a silent gap: a requirement no node states is a requirement no agent can
act on.

## Profiles

Profiles are optional auxiliary guidance. The core skill is authored without
profiles in mind: no workflow, policy, rule, protocol, verification, failure
condition, or required output may depend on a profile. Deleting the complete
`profiles/` directory therefore changes no valid execution.

The compiler builds one index, `profiles/index.md`, listing every profile the
bundle ships. Each row links a profile's title to its page and then gives the
profile's own `description` where it declares one, so an agent can tell the
candidates apart before opening any of them. The root does not enumerate profile titles or
conditions; it says only that the index may be there. A miss, a false positive,
an unavailable profile, or a decision not to consult profiles at all is never an
execution failure.

Profiles remain an open set. Degardis defines no domains, categories, or any
other taxonomy, and reads no meaning into a description: each profile describes
the recurring situation it applies to, in its own words.

## Scripts, assets, and references

Scripts are executable helpers. Assets are supporting files such as templates,
data, or media. References are Markdown pages used for non-binding supporting
material. Selected files are copied into the bundle at the same relative path.

The compiler generates an auxiliary reference page for a reached pattern,
heuristic, or guidance unit that carries non-binding material of its own — the
`points` it states or the `references` it names. Policies and rules earn no such
page: everything they say is binding, and binding text is lowered into the
execution nodes that enforce it. Required behavior never lives under
`references/`; required cross-file execution uses explicit `execution/*.md`
module loads.

## Bundle

Degardis produces one self-contained, agent-agnostic output per skill: a folder
by default, or a `.zip` archive with `--zip`.

Every build requires an output root. `SKILL.md` sits at the output's own root;
there is no per-agent layout or wrapper folder. With `--output .artifacts`,
installation is a separate copy or symlink step. When `--output` names an agent's
project or personal skill directory, an uncompressed build writes each skill
directly into its installed location. A ZIP file is a distributable artifact, not
a filesystem installation.

A build replaces the matching `<skill-name>/` and `<skill-name>.zip` for each
selected skill, and leaves everything else in the output root as it was. The same
source builds the same bytes wherever it is built. See
[Artifact format](artifact-format.md) for what a bundle contains and how
replacement behaves when a build fails.

## Collections

A directory that contains skills is an optional, human-facing collection.
Degardis discovers every descendant directory that contains a `skill.yaml`, so
you can use intermediate directories to organize your skills.

Once discovery finds a skill directory, it does not search inside it. The
collection itself has no manifest, metadata, routing rules, or artifact.
Degardis commands read source and never generated output, so a directory holding
a root `SKILL.md` and no `skill.yaml` is refused as a built bundle rather than
searched.
