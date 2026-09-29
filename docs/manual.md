# Reference manual

This is the reference for Degardis source format 2. Topics are ordered from source structure and syntax through constructs, validation, inspection, and build. `degardis manual TOPIC` prints the same topic text at a terminal. For a guided first run, see [getting started](getting-started.md).

<!-- Generated file. Do not edit directly. -->

## What a source is

A Degardis source declares a skill and the authored material each class of work needs. A build produces an agent skill with one page per task.

Five construct types hold authored Markdown:

- **Task** — one recognizable class of requested work.
- **Knowledge** — reusable subject matter, classified as concept, fact, constraint, or guidance.
- **Principle** — a standard the agent's work must honor.
- **Facet** — guidance selected by the situation rather than the task.
- **Guide** — detail a task, facet, or another guide loads separately.

Degardis adds no domain content and never paraphrases, merges, summarizes, or drops authored material. Around that material it adds headings and short, domain-neutral instructions in English with American spelling. The instructions route each requested outcome to a task and tell the agent which pages to read and when. When the bundle has at least one principle or guide page, they also have the agent track its progress and check its work against the requirements that apply, before an effect it cannot undo and before it claims completion.

`SKILL.md` is the bundle entry point: it identifies the skill, carries its skill-wide guidance, and routes a request to task pages. A task page contains that task's complete knowledge closure and may hand the work to another task. Principles, facets, and guides remain separate loads.

See also: [The source folder](#the-source-folder), [The manifest](#the-manifest), [Tasks](#tasks).

### The source folder

A source has one `skill.yaml` manifest plus authored files selected by it. Constructs are Markdown; scripts and assets are shipped files.

```text
my-skill/
  skill.yaml
  tasks/
  knowledge/
  principles/
  facets/
  guides/
  scripts/
  assets/
```

`degardis init NAME` creates a minimal valid source. The directories above are conventional, not required; manifest patterns decide which namespace each selected file belongs to and may select subdirectories.

Every selected file, and the interface icon, must be inside the source. Source and output paths may not overlap. Generated bundles are output only and cannot be used as source input; one inside a directory of skills is passed over.

### What it builds

```text
my-skill/
  SKILL.md
  references/tasks/...
  references/principles/...
  references/facets/...
  references/guides/...
  scripts/...
  assets/...
  agents/openai.yaml
```

Directories appear only when needed. Scripts and assets keep the paths they have in the source, so `scripts/` and `assets/` appear where the source uses them. A bundle with at least one principle or guide page also contains a generated progress register under `assets/`.

See also: [The manifest](#the-manifest), [Building a bundle](#building-a-bundle).

### The manifest

`skill.yaml` declares skill identity, task order, skill-level principles, selected content, and host interface.

```yaml
name: structured-summary
format_version: 2
version: 2.0.0
description: Turn supplied material into a clear, audience-appropriate summary.
stance: Act as an experienced editor for this work.
principles:
- evidence
tasks:
- summarize
content:
  tasks:
  - tasks/*.md
  principles:
  - principles/*.md
  knowledge:
  - knowledge/*.md
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  default_prompt: Use structured-summary to summarize this material.
```

- `name` (required) — lowercase letters, digits, single hyphens; names the bundle, independent of the source directory name; 64 characters max. A name containing an AI vendor or agent-host brand warns.
- `format_version` (required) — the integer 2.
- `version` (required) — the skill's version.
- `description` (required) — host selection description; 1,024 characters max. A description containing XML tags is an error.
- `stance` (optional) — opening paragraph of `SKILL.md`.
- `principles` (optional) — ids of the principles `SKILL.md` links.
- `tasks` (required) — every selected task id exactly once, in routing order.
- `content` (required) — selected files by namespace.
- `interface` (required) — host display and invocation metadata.
- `license` (optional) — publication license.
- `copyright` (optional) — copyright line.

An unprefixed top-level field the manifest does not define is an error. Put other tool metadata in top-level `x-` fields such as `x-owner`; Degardis validates their YAML value but otherwise ignores them. `content` and `interface` refuse every field they do not define, `x-` fields included.

### Selecting content

Each `content` key is an ordered list of glob patterns. `!pattern` removes files matched earlier.

- `tasks` — task Markdown.
- `knowledge` — knowledge Markdown.
- `principles` — principle Markdown.
- `facets` — facet Markdown.
- `guides` — guide Markdown.
- `scripts` — executable helpers.
- `assets` — supporting files.

`content.tasks` is required; other keys may be omitted. Every declared key must select at least one file, and every pattern, whether positive or an exclusion, must match at least one path. Matching is case-sensitive and uses `/` as the separator on every platform.

No pattern selects common platform bookkeeping files or Python bytecode. A wildcard pattern also skips hidden paths: files under a dot-prefixed directory and anything the filesystem marks hidden. A pattern without wildcards, or one that spells out a dot-prefixed directory, selects the hidden path it names.

See also: [The interface](#the-interface), [Tasks](#tasks), [How a source file is read](#how-a-source-file-is-read).

### The interface

`interface` tells a host how to display and invoke the skill.

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  default_prompt: Use structured-summary to summarize this material.
```

- `display_name` (required) — human-readable skill name; 64 characters max.
- `short_description` (required) — host list text; 64 characters max.
- `default_prompt` (required) — starting prompt a host inserts when a user invokes the skill; 1,024 characters max.
- `icon` (optional) — path of the skill's icon image inside the skill directory.

`default_prompt` should contain the skill's exact `name`. Write the name with no host invocation prefix such as `$` or `/`: a prefixed name is an error, because Degardis adds each target's prefix.

`interface.icon` selects the icon, which ships whether or not a `content.assets` pattern also matches it. The file must be an SVG, PNG, JPEG, or WebP image named by that suffix, and a raster file must be the image its suffix states. SVGs must be self-contained: no scripts, `foreignObject`, external references, or external CSS URLs. Internal fragments and inline `data:` images are allowed. The file may be at most 10 MiB and its image at most 67,108,864 pixels. Degardis does not rescale or convert the image, and one image serves every size a host shows.

See also: [The manifest](#the-manifest).

### How a source file is read

Each construct is one `.md` or `.markdown` file:

> The manifest selects its namespace. The file stem is its id. Frontmatter holds its fields. The body is its content.

```markdown
---
kind: concept
title: Audience
---

The audience determines what the result must explain.
```

Files are UTF-8; a leading byte-order mark is ignored. The opening `---` must be the first line and a closing `---` must precede the body. Do not declare `id`; rename the file to rename the construct.

Frontmatter accepts only fields defined for that construct. Unknown fields warn but still compile. Metadata owned by another tool may use `x-` fields such as `x-owner`; Degardis validates the YAML value and otherwise ignores it.

### Body handling

When authored Markdown is placed on a generated page, Degardis only:

- shifts heading levels while preserving relative depth and text;
- renders inline references as names or bundle paths;
- folds hard-wrapped prose paragraphs into one line.

Code, tables, lists, explicit line breaks, link definitions, authored links, and authored order are preserved.

Underlined headings shift too, and a shifted one is written with `#`. Markdown has no heading level below six, so a body whose headings would reach past it on its page warns; use fewer levels there.

### Inline references

Use `[[kind:target]]` in prose to reference selected content:

```markdown
Work through [[guide:checklist]] before release.
Fill in [[asset:template.docx]], then run [[script:check.py]].
```

`principle` and `guide` targets are bare ids. An `asset` or `script` target is the file's source-relative path or any trailing part of it made of whole segments: `check.py` and `lint/check.py` both name `scripts/lint/check.py`. A target that ends more than one selected file of its kind is refused; write more of the path. Tokens inside frontmatter, code, or another Markdown link remain literal; indentation that places a line in a list is not code. A `guide`, `asset`, or `script` target must be selected under its content key. A `principle` target must also be named in `skill.yaml`, because a principle the skill does not name gets no page. Any other kind is refused. Tasks and facets have no inline reference: send work to another task through a declared hand-off, and leave facet selection to the facet index.

A principle stands on its own, so its body may contain no inline reference of any kind; one is refused. Every other body may reference any kind. A guide referencing itself still renders but warns.

An `asset` or `script` reference renders as the file's bundle path in inline code, such as `scripts/check.py`. A `principle` reference renders as `principle:ID` in inline code and places nothing: `SKILL.md` lists every principle beside its conditions.

A `guide` reference renders as `guide:ID` in inline code and makes an owner of the guide: from a knowledge unit, every task whose page carries the unit; from a task, a facet, or a guide, that construct. The owner's page links the guide under **Guides**.

### Links

Refer to bundle content only through inline references. A Markdown link or image, a reference definition, or an HTML `href` or `src` whose destination is a relative or absolute path is refused, because the text lands on a page in another directory. Links to external addresses, such as `https:` or `mailto:`, and anchors on the same page are kept as written. A link inside code is a sample and is not checked.

See also: [YAML the compiler accepts](#yaml-the-compiler-accepts), [Names and references](#names-and-references).

### YAML the compiler accepts

`skill.yaml` and construct frontmatter accept mappings, lists, strings, integers, finite numbers, booleans, and null.

The following are refused:

- anchors and aliases (`&x`, `*x`), which reuse nodes;
- merge keys (`<<:`), which import fields;
- explicit tags (`!!tag`), which name unsupported types;
- bare dates, which become timestamps;
- `.inf` and `.nan`, which are non-finite numbers;
- repeated fields, whose value would be ambiguous; and
- non-string field names, because field names must be text.

Field names are always text, so a key such as `on` remains the string `on`.

Values such as `yes`, `no`, `on`, `off`, `08`, `1.50`, or `1:30` are accepted with YAML semantics but warned because authors often intend text. Quote them to force strings.

Each manifest or frontmatter block must parse to a mapping.

See also: [The manifest](#the-manifest), [How a source file is read](#how-a-source-file-is-read).

### Names and references

A construct id is its file stem and must contain lowercase letters, digits, and single hyphens: `review-draft`, `source-material`.

Ids are unique within a namespace, including across subdirectories. All knowledge kinds share the `knowledge` namespace; different construct namespaces may reuse the same id.

Reference fields that already name a namespace use bare ids:

```yaml
principles:
- evidence
knowledge:
- source-material
```

Knowledge and guide requirements use the same form:

```yaml
requires:
- audience
```

Every id in a reference list must name selected content and may appear only once in that list.

See also: [Tasks](#tasks), [Knowledge units](#knowledge-units).

## What you write

### Tasks

A task is one recognizable class of requested work. Each task becomes one task page.

```markdown
---
title: Review a draft
cues:
- the requester asks what is wrong or weak in a draft
- the requester asks whether a draft is ready to send
goal: Identify problems that would change the reader's response.
knowledge:
- audience
guides:
- house-style
handoffs:
- task: revise-draft
  applicability:
  - When the requester authorized fixing what the review finds
  - When the review request explicitly includes revision
---

Read the whole draft before judging any part of it.
```

- `title` (required) — router label and task-page heading.
- `cues` (required) — routing cues, one per list item.
- `goal` (required) — finished state the task reaches; rendered as **Goal**.
- `knowledge` (optional) — direct knowledge ids.
- `guides` (optional) — guide ids.
- `handoffs` (optional) — tasks this one sends the work to, each a `task` id with optional `applicability` conditions, one per list item.

The body renders as **Approach**. A task with no body, knowledge, guide, or hand-off still builds but warns.

### Routing

Cues are the router; title, goal, and knowledge do not affect matching. A cue states what a request for this task's outcome looks like. Overlap between tasks' cues is expected, and manifest order resolves it.

A request may ask for the outcome of more than one task. Each outcome it asks for goes to the first task in manifest order with a matching cue, and the chosen tasks are done one at a time, in the order the request states or otherwise in manifest order. A task does only its own outcome and receives what earlier tasks produced. A request no task matches is reported rather than forced into the closest task.

### Hand-offs

A hand-off names another task this one sends the work to when its `applicability` conditions hold. An omitted `applicability` means the hand-off always follows this task. Two tasks may hand off to one task under different conditions. The agent adds an applying task to its route before continuing, so a hand-off can send work to a task before, after, or instead of finishing the current one, as its conditions say.

Hand-offs render as links on the task page and never reach `SKILL.md`. A task may not hand off to itself, and it names a target once; two tasks may hand off to each other.

### Task page order

Present sections appear in this order:

1. title
2. **Goal**
3. **Hand-offs**
4. **Approach** — task body
5. **What you need to know** — **Concepts**, **Facts**, **Constraints**, **Guidance**
6. **Guides**

Cues appear only in `SKILL.md`.

See also: [Knowledge units](#knowledge-units), [Guides](#guides), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### Knowledge units

Knowledge is reusable subject matter that task pages carry.

```markdown
---
kind: concept
title: Audience
requires:
- source-material
---

The audience determines what must be explained and what may be assumed.
```

- `kind` (required) — `concept`, `fact`, `constraint`, or `guidance`.
- `title` (required) — heading on task pages.
- `requires` (optional) — additional knowledge ids brought into the same closure.

The body must be non-empty.

### Kinds

A unit has one kind, which names what the unit states and the heading it appears under on task pages:

- `concept` — a definition, model, or distinction; heading **Concepts**.
- `fact` — an established value, figure, table, or truth; heading **Facts**.
- `constraint` — behavior that must or must not occur; heading **Constraints**.
- `guidance` — how to act or choose; heading **Guidance**.

Task pages render kinds in that order. Kind changes nothing else in the bundle.

See also: [How knowledge reaches a page](#how-knowledge-reaches-a-page), [Tasks](#tasks).

### Principles

A principle is a standard the agent's work must honor across every task: domain-neutral guidance, or the skill's own domain guidance that holds whatever the task.

```markdown
---
title: Evidence for claims
applicability:
- Before making an externally visible claim
- Before recording a finding others will act on
---

State the observation supporting each claim beside the claim.
```

- `title` (required) — page heading and link text.
- `applicability` (optional) — conditions under which the principle applies, one per list item.

The body must be non-empty. Only the manifest's `principles` list places a principle in the bundle, by bare id. `SKILL.md`, which every task run reads, links each named principle, and each has one generated page containing its title and body. A selected principle the manifest does not name warns and gets no page.

See also: [The manifest](#the-manifest), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### Facets

A facet is guidance selected by the situation rather than the task. Facets are skill-wide; tasks do not select them. The agent reads every facet whose index entry applies.

```markdown
---
title: Meeting transcripts
category: Material
description: Spoken material where positions may change during discussion.
guides:
- transcript-passes
---

Treat later decisions as authoritative over earlier proposals.
```

- `title` (required) — index link text and page heading; unique across facets.
- `category` (optional) — index grouping label.
- `description` (optional) — text after the title in the index and under the page heading.
- `guides` (optional) — guide ids opened from this facet.

The body must be non-empty.

The facet index lists each facet's title, optional description, and link. When two or more categories exist, rows are grouped by category; otherwise the index is flat.

A file a `facets` pattern matches is selected as a facet, so select facet guides under `content.guides` from outside those patterns, for example `facets/guides/`.

See also: [Guides](#guides), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### Guides

A guide is detail a task, facet, or another guide loads as a separate page.

```markdown
---
title: House style
applicability:
- When the result will be published under the organization's name
- When the requester asks for the house style
requires:
- citation-style
---

Use the organization's publication rules.
```

- `title` (required) — page heading and link text.
- `applicability` (optional) — conditions under which the guide applies, one per list item.
- `requires` (optional) — ids of guides this guide cannot be understood without.

The body must be non-empty. Each selected guide has one generated page containing its title, its body, and the guides it owns, however many owners list it. A selected guide that no page lists and no inline reference names warns.

See also: [Tasks](#tasks), [Facets](#facets), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### How knowledge reaches a page

Knowledge reaches a task in only two ways:

```yaml
# task frontmatter
knowledge:
- source-material
- order-findings
```

```yaml
# knowledge frontmatter
requires:
- audience
```

A task page carries its direct knowledge plus all transitive `requires`. Direct units keep task order, and required units follow in the order requirements first introduce them; the page then groups units by kind, keeping this order within each kind.

Prose creates no dependency. Requirement chains may not cycle. Selected knowledge that no task reaches warns and is omitted from generated task pages. A unit reached by several tasks is copied into each closure; inspection reports the resulting duplication cost.

### How guides reach a page

A task or facet owns each guide its `guides` field names, a guide owns each guide its `requires` names, and each owns each guide its inline references make it own. Its page lists them at its foot: the guides it names, then those its inline references own, in the order its page first references them. Each guide is listed once, and never on its own page. Ownership does not pass along: a guide's requirements are listed on its page, not on its owners'. Guide requirement chains may not cycle.

### Conditions

Hand-offs, principles, and guides take an optional `applicability` list of conditions, one per item. Each applies when any of its items holds; conditions that must all hold belong in one item. An omitted list applies unconditionally. Items keep their authored order.

Conditions appear beside the link they qualify, not on the target page: a hand-off on its task page, a principle in `SKILL.md`, a guide on each owner's page. Each list of these links puts unconditional links first and otherwise keeps its order. The agent reassesses conditions as the work changes and reads an applicable principle or guide before continuing the work it governs.

See also: [Knowledge units](#knowledge-units), [Guides](#guides), [Seeing what the compiler decided](#seeing-what-the-compiler-decided).

### Scripts

`content.scripts` selects executable helpers. Each selected script is copied unchanged and is executable in both folder and ZIP builds, wherever it sits and whatever permissions the source file has. No other bundle file is executable, including a file selected as an asset under a `scripts/` directory.

A selected script with no inline reference warns because no reader reaches it.

See also: [The manifest](#the-manifest), [How a source file is read](#how-a-source-file-is-read), [The source folder](#the-source-folder).

### Assets

`content.assets` selects supporting files that are neither scripts nor guides. Selected assets are copied unchanged, including Markdown assets.

A selected asset with no inline reference warns because no reader reaches it; the asset selected by `interface.icon` is exempt.

See also: [The manifest](#the-manifest), [How a source file is read](#how-a-source-file-is-read), [The source folder](#the-source-folder).

## Working with the compiler

### Checking a source

```console
degardis validate my-skill
```

Validation writes nothing, collects all findings, exits 1 on errors, and exits 0 otherwise. `--fail-on-warning` treats warnings as errors. `inspect` and `build` run the same checks.

Validation checks:

- manifest fields, content selection, interface, and icon;
- construct fields and required bodies;
- task, principle, knowledge, guide, and inline references, inline references in principles, and links written by path;
- knowledge and guide requirement cycles, and unreachable knowledge;
- unused principles, guides, scripts, and assets;
- task routing and facet identity;
- generated page budgets, heading depth, generated links, and path collisions, including paths or directories that differ only in letter case and a file where a directory goes.

A pass means the source can produce a complete bundle whose generated links resolve. It does not judge whether the skill's guidance is useful.

Every finding includes a check code. Run `degardis explain CODE` for its trigger, impact, and, when the check states one, resolution.

See also: [Seeing what the compiler decided](#seeing-what-the-compiler-decided), [Building a bundle](#building-a-bundle).

### Seeing what the compiler decided

`inspect` reports a compilation and its findings in a compact, line-oriented form. `--only` and `--all` change output only.

`--only composition` shows why each task carries its knowledge:

```console
degardis inspect my-skill --only composition
```

```text
review-draft -> references/tasks/review-draft.md
  direct cite-the-source, audience
  required source-material
  concept audience, source-material
  constraint cite-the-source
```

`direct` is task-selected knowledge; `required` arrived through `requires`. Kind rows show render order.

### Reading a row

Every report includes `skill`; dimension blocks use a fixed order rather than request order. Fields are one space apart; indentation marks a line nested under the one above. Absent scalar values are `-` and empty lists are `none`.

The `skill` block's `size` row gives generated bytes per page class, against the class's one-load budget where it has one: `SKILL.md` with its line count, the progress-register asset, which has no budget, task pages (count, total, average, largest), principle pages, guide pages, and facet pages including the facet index, whose own size follows as `index`.

Row shapes by dimension:

- `identity` — unheaded rows `desc TEXT`, `brief TEXT`, `lic TEXT`, `copy TEXT`, `fmt FORMAT_VERSION`, and `hash ALGORITHM:DIGEST (N files)`
- `sources` — `KIND ID PATH BYTES`
- `tasks` — `ID "TITLE" PAGE BYTES N knowledge`, then goal, cues, guides, handoffs
- `knowledge` — `ID kind=KIND BYTES requires=... tasks=...`
- `principles` — `ID PATH BYTES -> PLACEMENTS linked=PAGES page=PAGE`, then one `applicability` line per condition
- `guides` — `ID PATH BYTES -> OWNERS requires=...`, then one `applicability` line per condition
- `facets` — `ID "TITLE" CATEGORY BYTES DESCRIPTION`
- `scripts` — `ID PATH BYTES linked=PAGES`
- `assets` — `ID PATH BYTES linked=PAGES`
- `outputs` — `PATH BYTES MODE`, under a heading giving the file count and total bytes
- `diagnostics` — `SEVERITY CODE LOCATION MESSAGE`

For identity, `brief` is the manifest stance, `lic` and `copy` are rights metadata, `fmt` is the declared source format, and the digest is shortened to 16 characters. For knowledge, `tasks` names pages carrying the unit. A principle's one placement is `SKILL.md`, present when `skill.yaml` names it. A principle or guide with no `applicability` line is unconditional. A task's `guides` line names ids only; conditions are in the `guides` dimension. A task's `handoffs` line names each task it hands off to, followed by one nested `ID applicability CONDITION` line per condition. Guide owners are qualified as `task:ID`, `facet:ID`, or `guide:ID`. `linked` names each page whose authored text names the principle, script, or asset by inline reference, as `task:ID`, `guide:ID`, or `facet:ID`; a reference in knowledge counts on every task page carrying that unit. Links the bundle writes itself are not counted: the root's task routes, the facet index, and owner links. A principle's placement and `linked` together are every page that links or names it; a guide's owners are every page that lists or names it. A script or asset ID is the shortest inline reference target that names that file alone. `outputs` MODE is the permission a build gives the file in either form.

The inspect report is the only machine-readable view of a compilation; a build writes the bundle and no plan, closure, source map, or coverage file beside it.

### Reading a page without building

`--page` prints generated Markdown without writing a bundle:

```console
degardis inspect my-skill --page SKILL.md
degardis inspect my-skill --page references/tasks/review-draft.md
```

Use `SKILL.md` or a page path reported by `inspect`. Repeat or comma-separate the option for several pages. Unknown paths are reported; the run fails if no selected skill generates a requested page. Only generated Markdown pages are accepted; copied scripts/assets and host metadata are not.

### Quality measures

`--only quality` reports structural signals without changing output:

- **Orphan knowledge** — selected knowledge reaching no task.
- **Near-duplicate knowledge** — units with substantial wording overlap.
- **Duplicated bytes** — knowledge repeated across task closures.
- **Constraint ratio** — share of carried knowledge classified as constraint.
- **Startup bytes** — generated root size.
- **Minimum read bytes by task** — root plus that task page.
- **Maximum read bytes by task** — every generated page one run of that task can be directed to read, each counted once: the root, the progress-register asset, the task page, the facet index, and every principle, guide, and facet page reachable from them without opening another task's page.
- **Headroom** — smallest remaining one-load budget across the root and every task, principle, guide, and facet page; negative when a page is over its budget.

These measures describe structure and read cost, not behavioral quality.

### Source fingerprint

`--only identity` reports a source fingerprint tied to the manifest, selected files, interface icon, and compiler version; it identifies the exact compiled source.

See also: [Checking a source](#checking-a-source), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### Building a bundle

```console
degardis build my-skill --output .artifacts
```

Builds write folders by default; `--zip` writes ZIP archives. Source-validation errors prevent any output. `--fail-on-warning` applies the stricter warning policy before writing.

Each skill artifact is replaced atomically. A failed write leaves that skill's previous artifact unchanged; siblings already completed in the same run remain. A rebuild replaces both the folder and the ZIP with the same skill name, whichever form it writes, so build into a scratch directory rather than a live agent skill directory, and build the two forms of one skill into separate directories.

The same source and compiler version produce byte-identical output across hosts.

### Page budgets

Root, task, principle, guide, and facet pages have warning-level size budgets, reported by `inspect --only skill`. The root is startup cost, a task page is one task load, and each separately opened page is an additional load.

Degardis does not truncate oversized pages, but a host may. A task-page budget finding names the knowledge units that weigh most on the page.

See also: [Checking a source](#checking-a-source), [The source folder](#the-source-folder).
