# Reference

Use this page to look up Degardis's CLI, discovery rules, source schemas, and
Python API. For a first build, follow [Getting started](getting-started.md); for
a guided source example, use [Authoring skills](authoring-guide.md).

## CLI

Use these commands to inspect skill sources and produce installable bundles.
Invoke them as `degardis COMMAND`; `python -m degardis` works the same way when
the entry point is not on `PATH`.

| When you need to | Use |
| --- | --- |
| See what skills a path selects and their metadata | [`list`](#degardis-list-path-path-) |
| Know whether sources compile | [`validate`](#degardis-validate-path-path-) |
| Write the installable folder or ZIP | [`build`](#degardis-build-path-path----output-path) |
| Review what a skill compiles to, in compact form | [`inspect`](#degardis-inspect-path-path-) |
| Learn what a diagnostic code means | [`explain`](#degardis-explain-code-code-) |

Only `build` writes files. The rest read source and print a report. None of them
executes a skill's bundled scripts. Shared path rules and exit status follow;
each command section then covers that command's options and behavior.

### Paths

`list`, `validate`, `inspect`, and `build` each take one or more paths. Each path
may name a skill directory or a collection directory; see
[Discovery](#discovery). These paths expand `~` and environment variables, and a
relative path is resolved from the current working directory.

`explain` is the exception. It takes check codes instead of paths and reads no
source at all.

### Exit status

Reports and build paths go to standard output. `[ERROR]` messages go to standard
error. An `[ERROR]` line names the check behind the failure in parentheses, the
way a validation report line does, so the same
[`degardis explain`](#degardis-explain-code-code-) call follows from a command
that stopped as from a report.

| Status | Meaning |
| --- | --- |
| 0 | The command completed. |
| 1 | Invalid source, selection, path, or filesystem operation. Degardis reports the problem without a Python traceback. Under `--fail-on-warning`, a warning is reported as an error and counts here. |
| 2 | Invalid command syntax. The command prints its usage. |

`validate`, `build`, and `inspect` accept `--fail-on-warning`. It changes no
check: every finding the checks reported as a warning is reported as an error
instead, so a source whose only findings are warnings fails the run. See
[Failing on warnings](#failing-on-warnings).

### `degardis list PATH [PATH ...]`

Surveys what is on disk. Creates nothing.

Lists each selected skill's title, manifest name, version, description, primary
workflow, a count per selected content key, available profiles, whether it ships
scripts, license, copyright, and absolute source path. Missing optional metadata
reads `Not specified`; a skill with no profiles reads `None`.

```text
Skills (1)

Structured Summary (structured-summary)  v1.0.0
  Description Turn supplied material into a clear, audience-appropriate summary.
  Workflow    compose
  Constructs  1 policies, 1 rules, 1 patterns, 1 heuristics, 1 guidance, 1 protocols, 2 records, 2
              workflows, 2 profiles, 3 references, 1 scripts, 1 assets
  Profiles    concise, detailed
  Scripts     Yes
  License     MIT
  Copyright   Copyright (c) 2026 Example Organization
  Source      /path/to/examples/structured-summary
```

Status is always 0 when the paths select at least one readable skill.

### `degardis validate PATH [PATH ...]`

Reports whether selected skills compile. Creates nothing.

One run reports every finding it can reach, inside a file and across files, so
you can repair a whole skill from a single report. The checks cover:

- the manifest, its `interface` metadata, and the files its `content` patterns
  select;
- each construct's own schema, decided by the manifest key that selected the
  file;
- every static selector, and every DExpr expression's syntax and types;
- each workflow's graph — forms, edges, reachability, termination, exhaustive
  outcomes — and its value flow;
- policy and rule activation, and whether each bound item reached a generated
  node;
- protocol state reachability, and whether each frame can close in an accepting
  state;
- pattern expansion, heuristic and guidance placement, and profile independence;
- the generated document's node labels, every transition within a module and
  across modules, and its outbound references.

A pass means the sources compile to a complete execution graph in which every
transition names a generated node — one in the same module, or one reached
through an explicit load of the module that holds it. It does not mean the skill
guides an agent well. The compiler validates declarations and relations it can
observe, and never the meaning of prose, so a skill can pass with every check
clean and still instruct an agent badly. The
[final checklist](authoring-guide.md#final-checklist) in the authoring guide
lists the judgments that remain yours.

A problem that still builds is reported as a warning — an over-long description,
a bound item that matched no reachable node, an unreached workflow, a generated
file above its attention budget, a YAML scalar that loads as something other than
its text. Everything else is an error. Pass any reported code to
[`degardis explain`](#degardis-explain-code-code-) for what it means.

The report marks each skill as a pass or a failure and lists its messages below
it. Each message ends with the check that reported it, in parentheses:

```text
Validation

[PASS] Structured Summary (structured-summary)

Summary: 1 passed, 0 failed, 0 errors, 0 warnings, 1 total.
A pass means these sources compile to a complete execution graph, not that the skill guides an agent well.
```

Paths in the report are absolute. A message carries a line number as well when
the check knows one. Pass any code to
[`degardis explain`](#degardis-explain-code-code-) for why that check matters.

Options:

- `--fail-on-warning`: report every warning as an error, so a source whose only
  findings are warnings fails. See [Failing on warnings](#failing-on-warnings).

Status is 0 when every skill passes, and 1 when any skill fails.

#### Failing on warnings

A final gate often requires zero undispositioned warnings. `--fail-on-warning`
expresses that, the way a compiler's "treat warnings as errors" option does: the
checks are unchanged, and every finding they reported as a warning is reported as
an error instead. The skill that carries it reads `[FAIL]`, the finding is listed
among that skill's errors, the summary counts it as an error, and the run exits 1.

```console
degardis validate path/to/skill --fail-on-warning
```

The report's closing line states how many findings the promotion moved, which is
the difference between the two standards. The sources are as buildable as they
were; they are not acceptable under the standard you asked for. A
`validate --fail-on-warning` failure therefore does not mean
[`build`](#degardis-build-path-path----output-path) would fail — unless you pass
the same option to it, where a promoted warning stops the build before anything
is written.

The option is available on `validate`, `build`, and `inspect`, so one standard
applies wherever the checks run.

### `degardis build PATH [PATH ...] --output PATH`

Produces the installable bundle. Writes the generated folder or archive.

Builds one uncompressed skill folder per selected skill by default, or one
`.zip` archive per skill with `--zip`. See
[Artifact format](artifact-format.md) for what the bundle contains.

Options:

- `--output PATH`: required output root.
- `--zip`: write a `.zip` archive per skill instead of an uncompressed folder.
- `--fail-on-warning`: report every warning as an error. Because a build stops on
  any error, a source whose only findings are warnings then produces no bundle:
  nothing is written, no existing bundle is replaced, and the status is 1. See
  [Failing on warnings](#failing-on-warnings).

> [!WARNING]
> Building into an agent's skill directory replaces that skill's existing
> `<skill-name>/` folder and `<skill-name>.zip` there. Build into a throwaway
> directory such as `.artifacts` while you are still editing the source, and see
> [Replace an artifact](artifact-format.md#replace-an-artifact) before you point
> `--output` at a live location.

Every selected source is checked before anything is written, so a run that
reports a failure has changed nothing on the way to it. Replacement is then
atomic per skill, not for the whole command: a skill replaced successfully stays
updated when a later skill fails, the failing skill is restored, and everything
else in the output root is preserved. See
[Replace an artifact](artifact-format.md#replace-an-artifact).

Degardis rejects an output directory that is the same as, contains, or is
contained by a selected skill source directory (`output.source-overlap`). A
relative output path is resolved from the current working directory.

On success the command reports each skill with the absolute path of its
generated folder or archive, then closes with a summary:

```text
Build

[BUILT] Structured Summary (structured-summary)
  Artifact    /path/to/.artifacts/structured-summary

Summary: 1 skill built as folder, 0 warnings.
```

Generated text is written with `\n` line endings on every platform, and an
archive records a fixed entry timestamp, so the same source produces the same
bundle bytes wherever it is built. To read the generated `SKILL.md` without
writing a bundle, use
[`degardis inspect --body-text`](#degardis-inspect-path-path-).

### `degardis inspect PATH [PATH ...]`

Reports what a skill compiles to and what each binding construct was lowered
into, with every error and warning aggregated in one run. Creates nothing.

This command is written for AI agents. Its output is line-oriented and shaped
for low token cost rather than for reading, and `degardis inspect -h` is its
complete account: the dimensions, the row legend, the source-format vocabulary,
how to gate on the result, and the sibling commands to run next. Prefer `list`
for a readable metadata summary and `validate` for a pass-or-fail gate.

`inspect`, `validate`, and `build` run the same checks over the same
compilation and set the same exit status. `--only` and `--all` choose what is
printed, never what is checked.

Options:

- `--only DIMENSION[,DIMENSION...]`: report the named dimensions instead of the
  default set. Repeat the option or comma-separate names to combine them.
- `--all`: report every dimension.
- `--body-text`: append the generated `SKILL.md` after the report and its closing
  summary, frontmatter included, preserving its lines with two spaces of
  indentation. Each skill's text follows a `=== <name>` divider, so a multi-skill
  selection stays unambiguous; a source that cannot be compiled reads
  `=== <name> unavailable`.
- `--fail-on-warning`: report every warning as an error. See
  [Failing on warnings](#failing-on-warnings).

Dimensions, in the order they are rendered. Every skill block opens with `skill`,
whatever the selection, so multi-skill output stays unambiguous:

| Dimension | Default | Reports |
| --- | --- | --- |
| `skill` | yes | name, version, title, root, description length, primary workflow, and selected construct counts |
| `identity` | | the full description, license, copyright, and source digest |
| `sources` | | every selected source file, its construct kind, id, and size |
| `workflows` | yes | each reachable workflow, the call that reaches it, its source steps, its lowered nodes, and its entry command |
| `execution` | | every lowered node, its kind, its source, and its transitions |
| `lowering` | | what happened to each bound binding item: the nodes it was lowered into, or that it matched nothing |
| `policies` | | each policy provision, its phase, and the nodes it constrains |
| `rules` | | each rule, its phase, and the nodes where it triggers |
| `protocols` | | each protocol frame, hook, and generated node |
| `patterns` | | each pattern application and the procedure nodes it expanded to |
| `heuristics` | | each heuristic and the decision or gate nodes it advises |
| `guidance` | | each guidance unit and the nodes its synopsis renders on |
| `profiles` | | each profile, its description, and its supplementary contributions |
| `attention` | yes | root control-plane bytes, execution-module bytes/count/max, worst-path execution bytes and loads, supplementary reference bytes, and outbound link counts |
| `outputs` | | every file a build would write, with size and mode |
| `diagnostics` | yes | aggregated errors and warnings |

Row shapes an agent parses:

- a `workflows` row is `ID STATUS [from CALLER] N steps N nodes PATH BYTES`,
  where `STATUS` is `primary`, `reached`, or `unreached`, followed by an
  indented `entry LABEL - COMMAND` and the workflow's declared outcomes and
  inputs;
- an `execution` row is `LABEL KIND [EDGE->TARGET, ...]` and then the node's own
  command. A target of `blocked` is the compiler-owned outcome every binding
  check returns on failure;
- a `lowering` row is `KIND ID lowered|not-lowered NODES`. `not-lowered` means a
  bound binding item reached no generated node, which is an error: a requirement
  no node states is a requirement no agent can act on;
- the `attention` row `path worst BYTESB | loads COUNT` gives independent
  worst-case execution bytes and module loads from the primary entry, including
  repeated calls and their matching outcomes. It excludes `SKILL.md`, optional
  material, and resource contents, and assumes no branch frequencies or host
  caching;
- the `attention` rows after it are one `link TARGET at NODE` per supplementary
  outbound link, naming the bundle-relative page and the generated node or page
  that points at it;
- an `outputs` row is `PATH BYTES MODE`. A rasterized icon carries the size
  the build will write, because checking an icon source is done by converting
  it;
- a `diagnostics` row is `SEVERITY CODE LOCATION MESSAGE`, where `LOCATION` is a
  path relative to the skill root with a line number where the check knows one,
  or `-` where the finding concerns the skill as a whole.

Sizes are the bytes of the *generated* Markdown, which is what an agent loads.
Identifiers are reported exactly as the source declares them.

Status is 0 when no skill reports an error and 1 otherwise, whichever dimensions
were selected, so `degardis inspect PATH --only diagnostics` is enough to gate a
change.

### `degardis explain CODE [CODE ...]`

Explains diagnostic check codes. Reads no skill source and creates nothing.

Explains each code given: what triggers the check, why it matters, and a failing
and a passing example of the source it concerns.

```console
degardis explain source.rejected-yaml
degardis explain rule.unmatched render.load-bearing-reference
```

Give as many codes as you like. A report usually names several, and one run
explains all of them, so an agent repairing a skill needs one call rather than
one per code. Codes are explained in the order given, separated by a blank line,
and each block opens with its code on a line of its own. A code repeated in the
same run is explained once.

Every code any check can report has an explanation. An unrecognized code exits
with status 1 and lists every code this version knows, grouped by namespace, so
you need no separate index to find the codes. When a run mixes known and unknown
codes, the known ones are still explained on standard output and the unknown ones
are named together on standard error.

#### How a code is spelled

Every code reads as `<namespace>.<check>`. The namespace is the construct or
stage the check concerns: `source`, `yaml`, `manifest`, `interface`, `content`,
`icon`, `policy`, `rule`, `protocol`, `pattern`, `heuristic`, `guidance`,
`profile`, `record`, `workflow`, `value`, `expr`, `resource`, `render`, or
`output`.

The check is written as hyphenated words, with one exception: where it names a
field of the source, it spells that field exactly as the key does. The check for
a missing `short_description` is therefore
`interface.missing-short_description`, keeping the underscore of the key. If you
know the key, you can write the code without looking it up.

Three checks separate the three ways a field can be wrong, so the code you get
tells you which repair you need without reading the message:

| Code | The field is |
| --- | --- |
| `<namespace>.missing-<key>` | required and absent |
| `<namespace>.unknown-field` | not one the schema declares |
| `<namespace>.invalid-shape` | present, and holding a value that cannot be read |

So a workflow with no `description` reports
`workflow.missing-description`, one that declares `profiles` reports
`workflow.unknown-field`, and one whose `outcomes` is `{}` reports
`workflow.invalid-shape`. The same three apply to every construct, to the
manifest, and to `interface`.

A field nested inside a provision, a hook, a step, a procedure item, or an
advice item is the exception: its absence reports the enclosing item's check —
`policy.invalid-provision`, `protocol.invalid-hook`, `workflow.invalid-step`,
`pattern.invalid-procedure`, `heuristic.invalid-shape` — because there the item
is the unit you repair rather than the file.

## Discovery

A path that contains `skill.yaml` selects that skill. Any other path is treated
as a collection: Degardis searches it recursively and selects every descendant
directory that contains `skill.yaml`. Once discovery finds a skill directory, it
does not search inside that skill for more skills.

Degardis ignores a duplicate path, but rejects the same skill name found at two
different paths. A missing path, a path that is not a directory, and a directory
with no skills below it are each an error.

Degardis commands read source, never generated output. A directory that holds a
root `SKILL.md` and no `skill.yaml` is a built bundle. Degardis refuses such a
directory (`source.generated-bundle`), a collection that contains one, and a
`.zip` archive (`source.archive-input`), and the error says which one it found.

This check matters because a bundle may ship a Markdown template as an asset.
Without the check, discovery would continue into the bundle, treat that template
as a skill, and report a pass for a skill you never named.

## Source layout and identity

Each selected YAML file defines exactly one top-level construct, and its
lowercase-hyphenated file stem is that construct's id. Top-level constructs
declare no `id` field.

```text
policies/source-fidelity.yaml   -> policy source-fidelity
rules/structure-subjects.yaml   -> rule structure-subjects
patterns/outline-then-draft.yaml-> pattern outline-then-draft
protocols/evidence-trail.yaml   -> protocol evidence-trail
workflows/compose.yaml          -> workflow compose
records/summary-result.yaml     -> record summary-result
profiles/concise.yaml           -> profile concise
```

Moving a file without changing its stem preserves its id. Renaming the file
changes its id. Ids are unique within a construct kind, including across nested
directories (`source.duplicate-id`). Every id, and every local id nested inside
a construct, matches `[a-z0-9]+(?:-[a-z0-9]+)*`.

The recommended tree uses one directory per kind:

```text
skill-name/
  skill.yaml
  policies/**/*.yaml
  rules/**/*.yaml
  patterns/**/*.yaml
  heuristics/**/*.yaml
  guidance/**/*.yaml
  protocols/**/*.yaml
  records/**/*.yaml
  workflows/**/*.yaml
  profiles/*.yaml
  references/**/*.md
  scripts/**/*
  assets/**/*
```

Those directory names are conventional. Degardis never infers a construct kind
from a directory name: the `content` key that selected a file decides which
schema the file must satisfy, so a policy selected by `content.rules` is read as
a rule and reported against the rule schema.

## `skill.yaml`

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Lowercase letters, digits, and single hyphens; must match the directory name |
| `format_version` | yes | Integer source-format version; must be `2` |
| `version` | yes | Non-empty skill release version; not dependency-resolution metadata |
| `description` | yes | Runtime selection description; over 1024 characters warns |
| `primary_workflow` | yes | File stem of a selected workflow |
| `license` | no | Non-empty license name or bundled license reference |
| `copyright` | no | Non-empty copyright notice |
| `policies` | no | Ids of the policies bound for the complete run |
| `rules` | no | Ids of the rules available for matching throughout the run |
| `protocols` | no | Ids of the protocols whose frame is the complete run |
| `guidance` | no | Ids of the guidance units whose synopsis is shown for the run |
| `content` | yes | Patterns selecting the source and copied files the skill ships |
| `interface` | yes | Portable display metadata |

Unlisted manifest fields are errors (`manifest.unknown-field`). Leaving a
required one out reports a check that names the key, such as
`manifest.missing-primary_workflow`. All YAML mappings in a source use string
field names.

`format_version` must be `2`. Every command that reads a source refuses an
earlier or later format, and no command converts one.

The four binding keys sit beside their `content` counterparts exactly as
`primary_workflow` sits beside `content.workflows`: the nested key says what the
skill ships, the top-level key says what governs the run.

```yaml
policies:
- source-fidelity
protocols:
- evidence-trail
guidance:
- clear-reporting
```

Each entry names a selected construct of that kind, once
(`source.unknown-reference`, `manifest.duplicate-binding`). Identifiers only: a
run-level binding applies to the whole run, so there is nowhere in it for a
condition. A policy provision or rule that should apply only sometimes carries
its own `when` or `unless`, or a narrower `match`.

The manifest binds no pattern and no heuristic. A pattern is selected at a
workflow step and a heuristic at a decision or gate, because neither is binding
by being available.

### Content configuration

`content` says which files the skill ships. Nine keys select source Degardis
parses, and three select files a build copies unchanged:

| Key | Selects |
| --- | --- |
| `policies` | policy sources, in YAML |
| `rules` | rule sources, in YAML |
| `patterns` | pattern sources, in YAML |
| `heuristics` | heuristic sources, in YAML |
| `guidance` | guidance sources, in YAML |
| `protocols` | protocol sources, in YAML |
| `records` | record sources, in YAML |
| `workflows` | workflow sources, in YAML |
| `profiles` | profile sources, in YAML |
| `references` | Markdown pages, copied into the bundle unchanged |
| `scripts` | executable helpers, copied into the bundle unchanged |
| `assets` | supporting files, copied into the bundle unchanged |

Each key takes a list of glob patterns, and each pattern must be a non-empty
string. Any other `content` key is an error.

No key has a default. A key you leave out means the skill ships no content of
that kind, and Degardis looks for none. Nothing is included because it sits in a
directory with a familiar name; the manifest alone decides.

Every skill therefore needs at least `workflows`. Without it there is no
execution to render, so nothing for `SKILL.md` to contain.

Two mistakes leave content out of the bundle without the bundle showing it, so
Degardis reports both as errors:

- a pattern that matches nothing in the skill directory, an exclusion included
  (`content.unmatched-pattern`);
- a key you declared that selects no file in the end, for example because an
  exclusion removed everything it selected (`content.empty-selection`).

A pattern cannot point outside the skill directory (`content.outside-skill`).
Degardis copies each selected reference, script, and asset to the same relative
path in the output. In ZIP output, scripts are marked executable.

A construct key must select `.yaml` files, and `references` must select `.md`
files; anything else is `source.unsupported`. That is what catches a
`content.profiles` pattern written as `profiles/**/*`, which would sweep in the
Markdown a profile names under `guides`: those are not profile sources, so write
`profiles/*.yaml`.

#### How patterns are matched

Patterns use `/` as their only separator, on every platform. Names are compared
exactly, upper and lower case included, even on Windows and macOS, where the
filesystem itself ignores case. If the directory is named `rules`, the pattern
`Rules/*.yaml` matches nothing and is reported as `content.unmatched-pattern`.
The same source therefore selects the same files on every computer.

Within one name, `*` matches any run of characters, `?` matches one, and
`[abc]` matches one of the characters listed. As a whole segment, `**` matches
any number of directories, including none, so `assets/**/*` selects everything
under `assets/` at any depth. `**` does not descend into a symbolic link, so a
link pointing back at one of its own parent directories cannot make matching run
forever.

Start a pattern with `!` to exclude the files it matches. Degardis reads a list
from top to bottom. An exclusion drops the files that the patterns above it
selected, and a pattern below the exclusion can select a file again:

```yaml
content:
  assets:
  - assets/**/*
  - "!assets/drafts/**/*"
  - assets/drafts/keep.md
```

Always put quotes around a pattern that starts with `!`. Without them, YAML
treats it as a tag, and the manifest does not load.

An exclusion that matches a directory drops every selected file inside it. This
is why `!assets/drafts` and `!assets/drafts/**` do the same thing. An exclusion
matches from the skill directory downwards, like every other pattern, so to
exclude a file at any depth write `!assets/**/*.tmp`, not `!*.tmp`.

Degardis excludes two kinds of path on its own: anything the filesystem marks
hidden or system, and anything inside a directory whose name starts with a dot. A
dot on a file's own name does not count, so `assets/**/*` still selects
`assets/.gitignore`.

To include something Degardis excluded this way, name that file or directory in
the pattern instead of matching it with a wildcard:

```yaml
content:
  assets:
  - assets/**/*      # by design, skips assets/.notes/
  - assets/.notes/*  # selects it again
```

No pattern selects these files, and naming them explicitly does not change that:

- Python bytecode, which Python generates from the skill's own scripts.
- The files an operating system creates for itself, such as `.DS_Store`,
  AppleDouble sidecars, `Thumbs.db`, or `desktop.ini`.

### Interface configuration

The required manifest `interface` mapping accepts:

| Field | Required | Meaning |
| --- | --- | --- |
| `display_name` | yes | Non-empty name displayed by the agent host, and the `SKILL.md` heading |
| `short_description` | yes | Interface summary; over 60 characters warns |
| `default_prompt` | yes | Suggested invocation containing the exact `{name}` placeholder |
| `icon` | no | Source image, rasterized into both icon roles |
| `brand_color` | no | Six-digit hex colour, such as `'#5B4B8A'` |

Unlisted `interface` fields are errors (`interface.unknown-field`).

`display_name` is the one human-readable name a skill declares. The generated
`SKILL.md` heading and the `list`, `validate`, `build`, and `inspect` reports all
read it.

The top-level `description` is different: an agent host uses it to decide when
the skill applies. Keep it specific even where the interface summary is shorter.

`default_prompt` is the only place a skill's own name appears in the source.
Because different hosts use different syntax to name a skill, the prompt names it
as the exact `{name}` placeholder and each target renders that placeholder in its
own syntax. The two ways of getting this wrong are treated differently:

| Prompt | Result | Check |
| --- | --- | --- |
| Contains `{name}` | Accepted | — |
| Names no skill at all | Warning; the skill still validates and builds | `interface.default_prompt-token` |
| Spells one host's syntax, such as `$my-skill` or `/my-skill` | Error | `interface.default_prompt-literal-token` |

Spelled host syntax is an error because it is emitted verbatim to every target,
so it is wrong on every host that types a skill name differently.

`icon` is a path relative to the skill directory, and may resolve outside it so
several skills can reuse one source image. A build rasterizes it into
`assets/icon-small.png` and `assets/icon-large.png` and points the generated
interface metadata at those PNGs rather than at the authored source path.

SVG and Pillow-supported raster inputs are accepted. Non-ICO images retain their
source dimensions; an ICO input uses its smallest frame for the small role and
its largest for the large role. An icon source may be at most 10 MiB and
67,108,864 pixels (64 × 1024²). Invalid images, SVG `<script>` or
`<foreignObject>` elements, external SVG references, and external CSS URLs are
rejected, each under its own code: `icon.invalid-path`, `icon.not-found`,
`icon.unsupported`, `icon.too-large`, and `icon.unsafe`.

## Common primitives

### YAML data model

Format 2 accepts mappings, lists, strings, integers, finite numbers, booleans,
and null. Source is UTF-8, and generated text uses `\n` line endings.

The loader refuses everything else, because each of these makes the value the
compiler reads differ from the text on the page: a duplicate key, an anchor, an
alias, a merge key, a custom tag, an implicit timestamp, a non-finite number, and
a non-string mapping key. A refused construct is `source.rejected-yaml`, and a
file that does not parse at all, or parses as something other than a mapping, is
`source.invalid-yaml` with the line to repair.

Three values load exactly as YAML says and still surprise their author, so they
warn rather than fail:

| Check | Value | What YAML makes of it |
| --- | --- | --- |
| `yaml.ambiguous-scalar` | `on`, `off`, `yes`, `no`, `y`, `n` | a boolean, not the word |
| `yaml.numeric-scalar` | `1.10`, `0755` | a number, losing the written form |
| `yaml.sexagesimal-scalar` | `1:30` | a number of seconds |

Quote the value where you meant the text. A field name is read as text either
way, so `on:` is the step field and not the boolean.

### Complete commands

Every binding provision, rule, protocol hook, pattern procedure item, workflow
action, decision, gate, choice, state, call, and return states a command. A
command is a non-empty sentence that can stand alone at the point where it is
rendered, because it becomes the heading of a generated execution node and an
agent that skims headings has to read what to do rather than infer it from a
topic.

Degardis cannot judge whether prose is genuinely complete. It requires the
command to be present, reports a heading that reads as a topic rather than an
action (`render.incomplete-command`), and reports one that does not close as a
sentence.

Behavior-affecting text belongs in a field with explicit compiler semantics.
Author-only documentation, such as rationale and examples, belongs to YAML comments. The compiler intentionally does not preserve comments, so they cannot affect the skill's behavior.

### Selectors

A policy provision, a rule, and a protocol hook each declare which nodes they
apply to, over declared metadata only:

```yaml
match:
  forms: [action, call]
  subjects: [summary.write, publication.*]
  effects: [workspace.write]
  calls: [report-gaps]
  outcomes: [delivered]
```

| Key | Matches |
| --- | --- |
| `forms` | node kinds: `action`, `branch`, `decision`, `gate`, `call`, `pattern`, `return` |
| `subjects` | a node's `subjects` tags |
| `effects` | a node's `effects` tags |
| `calls` | a call node by the workflow it calls |
| `outcomes` | a return node by the outcome it returns |
| `all` | `{all: true}`, every node in the binding scope |

Within one key, entries are alternatives. Populated keys combine with AND.
Subjects and effects are opaque dotted tags matching
`[a-z0-9]+(?:[-.][a-z0-9]+)*`, or a prefix selector ending in `.*`. Nothing
interprets their words.

Binding selection never reads a title, a description, a command, a filename outside
an explicit id reference, or natural-language similarity. So what a
provision constrains cannot drift as prose is reworded, and you can see from the
source which nodes you have selected.

### Phases

A phase says where a check sits relative to the node it constrains.

| Phase | Used by | Position |
| --- | --- | --- |
| `before` | policies, rules, protocol hooks | a generated node ahead of the constrained node |
| `during` | policies, rules | an invariant rendered on the constrained node itself, which only an `action`, `call`, `pattern`, or `return` node carries |
| `after` | policies, rules, protocol hooks | a generated node on each edge leaving the constrained node |
| `before-return` | policies, rules | a generated node ahead of a return |
| `enter` | protocol hooks | a generated node ahead of the frame's first node |
| `exit` | protocol hooks | a generated node ahead of the frame's close |

`after` is generated once per outgoing edge, because a decision, a gate, a
branch, and a call each leave by more than one. The edge is named in the node's
label by a source id: a decision or gate by the option, a call by the outcome it
returns, an action by completion, and a branch case by its destination step,
since `when` is an expression rather than an id. Two cases routing to one step
share one check, which precedes that step either way. A return has no `after`: what it
precedes is leaving the workflow, which is what `before-return` names, so an
`after` provision matching a return reaches no node and warns.

A `during` invariant renders beside the command it constrains, and a `decision`,
`gate`, or `branch` node states a choice rather than an action, so none of them
carries one. A `during` provision or rule whose selector matches only those is
active and enforced nowhere, which is an error
(`policy.unlowered-provision`, `rule.unlowered`) naming the phase and the form
that refused it. Select `action`, `call`, `pattern`, or `return` instead, or move
the requirement to `before` to check it ahead of the choice.

`match.forms` names node kinds, not step forms, so a `use` step is selected as
`call` and a `decide` step as `decision`. A selector naming a step form is
reported (`policy.invalid-provision`, `rule.invalid-shape`) and the message lists
the node kinds.

### DExpr

DExpr is the side-effect-free expression language a branch case, an activation
condition, and an expression verification are written in.

```ebnf
expression      = or-expression ;
or-expression   = and-expression, { "or", and-expression } ;
and-expression  = unary-expression, { "and", unary-expression } ;
unary-expression= [ "not" ], comparison ;
comparison      = primary, [ ( "==" | "!=" | "<" | "<=" | ">" | ">="
                             | "in" | "not in" ), primary ] ;
primary         = literal | reference | list | function
                | "(", expression, ")" ;
function        = ( "exists" | "length" | "contains" ),
                  "(", [ expression, { ",", expression } ], ")" ;
reference       = namespace, ".", identifier,
                  { ".", identifier | "[", integer, "]" } ;
namespace       = "input" | "result" | "decision" | "gate" | "call" | "state" ;
list            = "[", [ expression, { ",", expression } ], "]" ;
literal         = string | integer | decimal | "true" | "false" | "null" ;
identifier      = lowercase-hyphenated-id ;
```

The six namespaces name what a node may read:

| Namespace | Holds |
| --- | --- |
| `input` | the workflow's declared inputs |
| `result` | values produced by earlier steps |
| `decision` | the choice a `decide` step selected, as `decision.<step-id>` |
| `gate` | the state a `gate` step reached, as `gate.<step-id>` |
| `call` | a `use` step's receipt, as `call.<step-id>` |
| `state` | the current protocol frame's own declared data |

An expression cannot invoke a tool, a script, a clock, randomness, a network, or
a host API. Degardis type-checks each expression at its evaluation boundary and
reports `expr.invalid-syntax`, `expr.unknown-value`, `expr.undefined-value`, or
`expr.type-mismatch`.

A possibly absent value must be guarded by `exists` in the same short-circuit
expression, or the read is `expr.unguarded-optional`:

```yaml
when: exists(result.inspection) and length(result.inspection.gaps) > 0
```

### Types and bindings

A value type is a scalar name, or a mapping naming exactly one constructor:

```yaml
type: string
type: integer
type: number
type: boolean
type: {enum: [brief, detailed]}
type: {list: string}
type: {record: material-inspection}
type: {optional: string}
```

An `enum` names at least one lowercase-hyphenated value, and no value twice. A
list item type cannot be optional, and an optional type cannot wrap another
optional.

A workflow input, a produced value, a pattern input, a protocol data field, and a
record field all declare a value the same way: a mapping with `type`, or with
`record` as its short form, plus an optional `description`.

```yaml
inspection:
  record: material-inspection
purpose:
  type: string
  description: What the summary is for.
```

A supplied value is a tagged binding, so nothing has to guess whether a word is
a value name or a literal:

```yaml
inspection: {from: result.inspection}
depth: {from: decision.choose-depth}
count: {literal: 1}
```

`from` takes one value reference. `literal` takes a string, number, boolean, or
null — never a mapping or a list. A binding whose shape is wrong is
`value.invalid-binding`; one whose type does not match the declaration is
`value.mistyped-binding`; a missing or extra one is `value.missing-binding` or
`value.unknown-binding`.

### Verification

A policy provision, a rule, and a protocol hook may declare how the check is
verified. `verify` names exactly one of three forms:

```yaml
verify:
  expression: length(result.inspection.subjects) > 1
verify:
  gate: check-readiness
verify:
  confirm: Each heading names one subject the material covers.
```

- `expression` is a DExpr the agent evaluates against the values available at
  that node.
- `gate` names a gate step whose decision the check reads. That gate has to lie
  on every path to the node the check constrains, or the verification names a
  value that may not exist (`workflow.missing-gate`).
- `confirm` is a sentence the agent confirms.

A heuristic can never satisfy a verification. `verify: {heuristic: ...}` or
`verify: {prefer: ...}` is `heuristic.used-as-authority`, because advice can
improve a choice and can never discharge a binding check.

## Workflow schema

A workflow file accepts:

| Field | Required | Meaning |
| --- | --- | --- |
| `steps` | yes | Mapping of step id to one step |
| `entry` | yes | The step id execution starts at |
| `description` | yes | The workflow's purpose, stated in its generated module and call boundary |
| `outcomes` | yes | The outcomes a return may name |
| `title` | no | Heading for the workflow section; defaults to the title-cased file stem |
| `inputs` | no | Declared values the caller supplies |
| `policies` | no | Ids of policies bound throughout this workflow |
| `rules` | no | Ids of rules considered throughout this workflow |
| `protocols` | no | Ids of protocols whose frame is one invocation of this workflow |
| `guidance` | no | Ids of guidance units whose synopsis heads this workflow |

`description` is required because generated workflow modules and explicit call
boundaries state what the workflow does before execution enters it. `outcomes` is required because every reachable path ends at a
return and every return names a declared outcome, so a workflow with none has no
way to terminate.

Leaving a required field out reports a check that names the key —
`workflow.missing-description`, `workflow.missing-entry`,
`workflow.missing-outcomes`, `workflow.missing-steps`. An unlisted field is
`workflow.unknown-field`. A field that is present but unreadable is
`workflow.invalid-shape`.

An outcome declares an optional record and nothing else:

```yaml
outcomes:
  delivered:
    record: summary-result
  no-summary: {}
```

`blocked` is the compiler's own outcome. Every workflow declares it, every
binding check returns it on failure, and a source that declares, returns, or maps
it is `workflow.reserved-outcome`.

### Step forms

Each key under `steps` is a step id, and each step declares exactly one form
(`workflow.invalid-step`). These fields are common to every form:

| Field | Meaning |
| --- | --- |
| `policies` | Additional policies bound at this step |
| `rules` | Additional rules considered at this step |
| `protocols` | Protocols whose frame is this one reached step |
| `guidance` | Guidance units whose synopsis renders on this node |
| `subjects` | Opaque tags a selector matches |
| `effects` | Opaque technical effect tags a selector matches |
| `heuristics` | Advice to show — accepted by `decide` and `gate` only |

Naming `heuristics` on any other form is `heuristic.invalid-placement` rather
than an unknown field, because the mistake is about what a heuristic is for. No
workflow and no step may select a profile (`profile.workflow-dependency`).

**`action`** — do one thing. Accepts `action`, `uses`, `produces`, optional typed `resource`, and a required `next`.

```yaml
inspect-material:
  action: Inspect the supplied material for its subjects, its main claims, and
    the gaps that limit a faithful summary.
  uses: [input.material]
  resource:
    run: scripts/list_headings.py
  subjects: [material.inspect]
  produces:
    inspection:
      record: material-inspection
  next: check-readiness
```

**`branch`** — an ordered list of machine-decided cases. Each case declares
`when` and `next`; the last case is `otherwise` alone, so every path continues
somewhere. A branch produces no value and states no command of its own.

```yaml
route:
  branch:
  - when: input.wide == true
    next: apply-wide
  - otherwise: apply-narrow
```

**`decide`** — an agent chooses among named alternatives. Accepts `decide`, `choices`, and `heuristics`. At least two choices are required,
because a closed judgment with one answer decides nothing. Each choice declares
a `command` and a `next`. The selected choice is available as
`decision.<step-id>`.

```yaml
choose-depth:
  decide: Choose the depth this reader's purpose needs.
  heuristics: [smallest-sufficient-detail]
  choices:
    brief:
      command: Write the shortest summary that answers the reader's purpose.
      next: write-summary
    detailed:
      command: Write a summary that carries the supporting detail the purpose needs.
      next: write-summary
```

**`gate`** — a closed judgment with exhaustive states. Accepts `gate`, `states`, and `heuristics`, with the same two-state minimum and the
same `command` and `next` per state. The state reached is available as
`gate.<step-id>`, and is what `verify: {gate: ...}` reads.

**`use`** — call another workflow in the same skill. Accepts `use`, `with`, and
`on`. `with` supplies every input the callee declares. `on` maps every outcome the callee declares to a next step; an unmapped one is
`workflow.unhandled-outcome`. An outcome arm may be a mapping with `next` and `as`;
`as` captures a record-bearing return payload as `result.<id>` on that edge. Capturing
an outcome without a record is `value.invalid-capture`. The enum receipt remains
`call.<step-id>`.

```yaml
describe-gaps:
  use: report-gaps
  with:
    gaps: {from: result.inspection.gaps}
  on:
    reported:
      next: no-summary
      as: gap-report
```

A call names the callee's generated module and its exact entry node, and states
that node's command; loading is mandatory and fail-closed, and the agent must not
infer the callee body from a workflow title or file name. Cross-skill calls are
invalid, because the other skill may not be installed.

**`pattern`** — apply a reusable procedure. Accepts `pattern`, `with`, and a
required `next`. `with` supplies every input the pattern declares. The compiler
expands the pattern into caller-owned nodes, so the step itself renders no node
and nothing links to a pattern page.

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

**`return`** — end the workflow. `return` declares an `outcome` and an optional
`with` supplying the values that outcome's record names. A return has no
successor.

```yaml
deliver:
  return:
    outcome: delivered
    with:
      summary: {from: result.reviewed}
      limitations: {from: result.inspection.gaps}
```

### Graph rules

Degardis rejects a workflow whose graph cannot execute:

- an unknown entry, transition target, called workflow, outcome, value, gate,
  record, or construct reference (`workflow.invalid-edge`,
  `source.unknown-reference`);
- a step with no form or several (`workflow.invalid-step`);
- a non-return step with an incomplete set of successors;
- a step no path reaches (`workflow.unreachable`);
- a reachable path that does not terminate;
- a backward edge, and a cycle among `use` calls;
- an unhandled decision choice, gate state, or callee outcome
  (`workflow.unhandled-outcome`);
- a missing, extra, or mistyped binding (the `value.*` codes);
- a value read before it is definitely assigned (`expr.undefined-value`);
- an optional value read without an `exists` guard
  (`expr.unguarded-optional`);
- two scopes binding one construct twice (`workflow.duplicate-binding`);
- one command both required and prohibited at one step and phase
  (`workflow.conflicting-obligation`);
- a check verified by a gate that does not dominate it
  (`workflow.missing-gate`).

A workflow no call reaches from the primary workflow warns
(`workflow.unreached`). It still builds; nothing invokes it.

## Policy schema

A policy is a standing authoritative boundary. It carries related provisions because
those provisions share one authority and scope; every active provision is binding.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | yes | What the policy keeps within bounds |
| `provisions` | yes | Non-empty mapping of local id to provision |
| `title` | no | Human-readable label used in inspection |

Each provision accepts `phase`, `match`, exactly one of `require`/`prohibit`, optional
`when`, optional `unless`, and optional `verify`.

A provision is active when its selector matches, `when` is absent or true, and
`unless` is absent or false. Required policy behavior is lowered directly into the
execution graph. No policy explanation page is generated.

## Rule schema

A rule is one operational conditional relation: when its declared condition holds, it
requires or prohibits one behavior at one phase.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | yes | The relation the rule establishes |
| `phase` | yes | `before`, `during`, `after`, or `before-return` |
| `match` | yes | Static selector |
| `require` or `prohibit` | exactly one | Complete binding command |
| `title` | no | Human-readable label used in inspection |
| `when` | no | DExpr condition |
| `unless` | no | DExpr exception condition |
| `verify` | no | `expression`, `gate`, or `confirm` |

A matching rule lowers directly at the boundary it constrains and blocks when an
active requirement cannot be satisfied. No rule explanation page is generated.

## Protocol schema

A protocol is a stateful lifecycle around a run, workflow invocation, or reached step.
Use one when later work depends on something opened, retained, consumed, or closed
across boundaries.

Required fields are `purpose`, `states`, `initial`, `accepting`, and non-empty `hooks`.
Optional fields are `title` and `data`. Hooks declare their phase, state constraints,
complete command/verification, and updates. Protocol obligations are lowered into
required execution modules; no protocol rationale/example page exists.

## Pattern schema

A pattern is a reusable method selected explicitly by a workflow `pattern` step.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | yes | What the method accomplishes |
| `procedure` | yes | Non-empty ordered mapping of local id to procedure item |
| `title` | no | Human-readable label |
| `inputs` | no | Values supplied through `with` |
| `references` | no | Explicit auxiliary reading |

Each procedure item requires `command` and may declare `uses`, `subjects`, and
`effects`. Reads are validated against pattern inputs and translated through caller
bindings; effects belong only to the item declaring them. Each item expands to a
execution node. References are auxiliary and cannot carry required behavior.

## Heuristic schema

A heuristic is a defeasible aid for choosing among already-valid alternatives.
Ignoring one may reduce quality or efficiency but is not a binding violation.

| Field | Required | Meaning |
| --- | --- | --- |
| `question` | yes | Choice the heuristic helps make |
| `advice` | yes | Non-empty mapping of local id to advice item |
| `title` | no | Human-readable label |
| `references` | no | Explicit auxiliary reading |

Each advice item requires `prefer` and may contain `when`, `because`, and `caution`.
Applicable advice, reasons, and cautions render inline on `decide` or `gate` nodes.
References remain auxiliary.

## Guidance schema

Guidance is supplementary context or advice. It does not block, authorize, prohibit,
change protocol state, or select a transition.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | yes | Concise advice rendered at each application |
| `title` | no | Human-readable label |
| `points` | no | Additional advice rendered for `detail: inline` |
| `references` | no | Explicit auxiliary reading |

The skill, a workflow, and a step may apply guidance. `detail` is `synopsis` or
`inline`. Required behavior must not be placed in guidance or its references.

## Profile schema

A profile is optional auxiliary guidance discovered independently of workflows. The
core skill is authored without profiles in mind, and deleting all profiles cannot
change requirements, transitions, failure conditions, or valid outputs.

| Field | Required | Meaning |
| --- | --- | --- |
| `points` | yes | Non-empty list of auxiliary guidance strings |
| `title` | no | Page heading; omission warns and derives one from the id; titles must be unique |
| `description` | no | Non-empty string describing what the profile is for, shown in the generated index |
| `category` | no | Non-empty string used only to group entries in the generated index |
| `guides` | no | Markdown files appended to the profile page |

```yaml
title: Detailed result
description: Apply where the reader needs how the main ideas relate, not only what
  they are.
points:
- Explain how the main ideas relate rather than listing them in isolation.
- Include representative supporting detail while keeping the source's
  qualifications.
guides:
- guides/detailed.md
```

A profile that declares no description contributes its title alone to the index.
A present description that is empty, whitespace-only, null, or not a string
reports `profile.invalid-description`. Omit the field to show only the title.

When profiles declare more than one distinct category, the index groups them
under level-two headings using the category strings. Categories are case-sensitive,
trimmed of surrounding whitespace, and sorted lexicographically; profiles within
each category are sorted by id. Uncategorized profiles appear first, without a
subsection heading. With zero or one declared category, the index remains a flat
list sorted by id. Category affects only the index, not profile pages or execution.

A present category that is empty, whitespace-only, null, or not a string reports
`profile.invalid-category`. Omit the field to leave a profile uncategorized.
Fields outside this schema are ordinary unknown-field errors.

Profiles cannot declare policies, rules, protocols, or workflows
(`profile.binding-contribution`), and workflows cannot reference profiles
(`profile.workflow-dependency`). Missing profile files or missed retrieval never block.

A guide path is relative to the profile file's own directory, so the
`guides/detailed.md` above is `profiles/guides/detailed.md` when the profile is
`profiles/detailed.yaml`. Guides must stay inside the skill, exist, be Markdown, and
omit a level-one heading because the generated profile page supplies one. `inspect`
reports title, description, point count, and guide count.

## Record schema

A record is a typed mapping, used wherever a value is produced, supplied to a
call, or returned.

| Field | Required | Meaning |
| --- | --- | --- |
| `fields` | yes | Non-empty mapping of field name to declared value |
| `title` | no | Display name; defaults to the title-cased file stem |

```yaml
title: Material inspection
fields:
  subjects:
    type: {list: string}
    description: The distinct subjects the material covers.
  gaps:
    type: {list: string}
    description: Missing context or contradictions that limit a summary.
```

Record fields render inline where a value is produced, supplied, or returned, so
no record page is emitted and none is needed for execution.

## Generated output

For the bundle's layout, interface metadata, and rebuild behavior, see
[Artifact format](artifact-format.md). `SKILL.md` is a compact control plane. Reachable
workflow bodies are emitted into deterministic files under `execution/`.

A generated node is named `n-` and ten hexadecimal digits, derived from the
source identity it stands for. Every transition targets one: a node in the same
module by that name alone, and a node elsewhere as `<module>:n-<id>`, qualified
by the stem of the `execution/` file holding it and followed by that node's own
command. `SKILL.md` states once what a qualified name means and that a module
which cannot be read returns `blocked`. A documentation link cannot stand in for
a transition (`render.load-bearing-reference`).

Required files used by an action are typed operations, declared as the action's
`resource` and named one of `run`, `read`, `copy`, or `fill`
(`resource.invalid-operation`). The `run: scripts/list_headings.py` in the
[`action` step form](#step-forms) above is one.

`run` must point under `scripts/`; `copy` and `fill` under `assets/`; `read` under
`references/` or `assets/`. Paths must stay inside the bundle and must be selected by
the manifest (`resource.invalid-path`, `resource.not-selected`). Failure to access or
perform the resource operation returns `blocked`.

Reachable workflow bodies are partitioned across `execution/` modules by their
rendered size and execution-path reading cost. The compiler searches the source
topological order and up to two branch-first orders, retaining up to eight
incomparable partial partitions at each boundary. Complete candidates are ranked
by actual worst-path bytes, worst-path loads, and total execution bytes, in that
order. The source-order greedy partition remains a candidate. This bounded
search does not guarantee a global optimum. See
[the portable execution contract](concepts.md#the-portable-execution-contract).

Three sizes warn. A generated `SKILL.md` above 4 KiB is
`render.root-budget`. An execution module above 16 KiB is `render.module-budget`,
which the partition avoids wherever it can divide the module: what is left is a
workflow header, repeated in every module, that leaves no room for a node around
it. One node above 16 KiB on its own is `render.node-budget`, and the module
holding it reports as well. Conflicting generated node ids report
`render.node-label-collision`.

## Python API

```python
from pathlib import Path

from degardis.build import SkillCompiler, build_skills
from degardis.validate import validate

compiler = SkillCompiler(Path("examples/structured-summary"))
paths = compiler.build(Path(".artifacts"))

errors = validate(Path("examples/structured-summary"))

zipped = build_skills(
    Path("examples/structured-summary"),
    Path(".artifacts"),
    as_zip=True,
)
```

### `SkillCompiler(sources)`

Creates a reusable compiler for one source path or a list of source paths.
Sources follow the same explicit-skill and collection discovery rules as the
CLI. Discovery occurs when the compiler is created.

### `SkillCompiler.build(output, as_zip=False, *, fail_on_warning=False)`

Builds every selected skill and returns a `list[pathlib.Path]` containing one
output path per skill. `as_zip=True` returns paths to ZIP archives instead of
bundle directories. `fail_on_warning=True` applies the same standard as the CLI
option: every warning counts as an error, so a source whose only findings are
warnings raises `DegardisError` and nothing is written.

As with the CLI, replacement is atomic per skill rather than across the whole
call. A failed replacement restores that skill's previous folder and ZIP, but
skills completed earlier in the call remain updated. Everything else in `output`
is preserved. The method rejects output that overlaps a selected source. Python
API paths are `pathlib.Path` values and are not automatically expanded for `~` or
environment variables.

### `build_skills(sources, output_dir, as_zip=False, *, fail_on_warning=False)`

Convenience function with the same build behavior and return value as
`SkillCompiler.build`. Use `SkillCompiler` when building the same selected
sources more than once; use `build_skills` for a single build.

### `validate(sources)`

Validates one source path or a list of source paths without writing output.
Returns an empty `list[str]` when valid, or one or more human-readable error
messages when invalid:

```python
errors = validate(Path("examples/structured-summary"))
if errors:
    raise SystemExit("\n".join(errors))
```

Expected source, discovery, filesystem, and decoding failures are returned as
error strings. Unexpected exceptions from compiler logic propagate, so an
internal defect is not misreported as invalid authored source.

`SkillCompiler` and `build_skills` raise `degardis.model.DegardisError` — a
`ValueError` subclass — for invalid source, selection, or output relationships.
Filesystem operations may raise their original `OSError` subclasses.
