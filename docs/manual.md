# Reference manual

This is the reference for Degardis source format 2. Topics are ordered from source structure and syntax through constructs, validation, inspection, and build. `degardis manual TOPIC` prints the same topic text at a terminal. For a guided first run, see [Getting started](getting-started.md).

<!-- Generated file. Do not edit directly. -->

## What a source is

A Degardis source declares a skill and the authored material each class of work needs. A build produces an agent skill with one page per task.

Five construct types hold authored Markdown:

- **Task** — one recognizable class of requested work.
- **Knowledge** — reusable subject matter, classified as concept, fact, constraint, or guidance.
- **Principle** — a standard the agent's work must honor.
- **Facet** — guidance selected by the situation rather than the task.
- **Guide** — detail a task or facet loads separately.

Degardis adds no domain content. It places authored material and may only re-level headings, turn inline references into links, and fold hard-wrapped paragraphs; it does not paraphrase, merge, summarize, reorder, or drop it. The headings and short instructions it adds around that material are in English with American spelling.

A task page contains that task's complete knowledge closure. Principles, facets, and guides remain separate loads. An omitted activation condition means the principle or guide always applies where it is referenced.

See also: [The source folder](#the-source-folder), [The manifest](#the-manifest), [What you write](#what-you-write).

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

Directories appear only when needed. Scripts and assets keep the paths they have in the source, so `scripts/` and `assets/` appear where the source uses them. Builds emit no plan, closure, source map, coverage file, or build report.

`SKILL.md` is the bundle entry point. It identifies the skill, carries its skill-wide guidance, and routes requests to the appropriate task-specific and situational guidance.

See also: [The manifest](#the-manifest), [Building a bundle](#building-a-bundle).

### The manifest

`skill.yaml` declares skill identity, task order, skill-level principles, selected content, and host interface.

```yaml
name: structured-summary
format_version: 2
version: 2.0.0
description: Turn supplied material into a clear, audience-appropriate summary.
purpose: Produce a shorter result the requester can act on.
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

| Field | Required | Rule |
| --- | --- | --- |
| `name` | yes | lowercase letters, digits, single hyphens; names the bundle, independent of the source directory name |
| `format_version` | yes | the integer 2 |
| `version` | yes | the skill's version |
| `description` | yes | host selection description; over 1024 characters warns |
| `purpose` | no | brief agent-facing purpose; defaults to `description` |
| `principles` | no | skill-level principle ids |
| `tasks` | yes | every selected task id exactly once, in routing order |
| `content` | yes | selected files by namespace |
| `interface` | yes | host display and invocation metadata |
| `license` | no | publication license |
| `copyright` | no | copyright line |

Unprefixed top-level fields are reserved. Put other tool metadata in top-level `x-` fields such as `x-owner`; Degardis validates their YAML value but otherwise ignores them. `content` and `interface` do not accept `x-` fields.

### Selecting content

Each `content` key is an ordered list of glob patterns. `!pattern` removes files matched earlier.

| Key | Files |
| --- | --- |
| `tasks` | task Markdown |
| `knowledge` | knowledge Markdown |
| `principles` | principle Markdown |
| `facets` | facet Markdown |
| `guides` | guide Markdown |
| `scripts` | executable helpers |
| `assets` | supporting files |

`content.tasks` is required; other keys may be omitted. Every declared key and every positive pattern must match at least one file. Matching is case-sensitive and uses `/` as the separator on every platform.

Wildcard matches skip hidden directories, common platform bookkeeping files, and Python bytecode. An explicit path, or a pattern explicitly naming a hidden path, may select it.

See also: [The interface](#the-interface), [What you write](#what-you-write), [How a source file is read](#how-a-source-file-is-read).

### The interface

`interface` tells a host how to display and invoke the skill.

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  brand_color: '#5B4B8A'
  default_prompt: Use structured-summary to summarize this material.
```

| Field | Required | Rule |
| --- | --- | --- |
| `display_name` | yes | human-readable skill name |
| `short_description` | yes | host list text; 60 characters or fewer avoids a warning |
| `default_prompt` | yes | suggested invocation |
| `icon` | no | source image inside the skill directory |
| `brand_color` | no | six-digit hex color, for example `'#5B4B8A'` |

`default_prompt` should contain the skill's exact `name`, and a prompt that does not warns. Write the name with no host invocation prefix such as `$` or `/`: a prefixed name is an error, because Degardis adds each target's prefix.

Naming `interface.icon` ships the icon, so do not also select it under `content.assets`. SVG and raster sources are accepted. SVGs must be self-contained: no scripts, `foreignObject`, external references, or external CSS URLs. Internal fragments and inline `data:` images are allowed. Degardis does not rescale the image: an ICO uses its smallest image for the small role and largest for the large role; other sources supply the same rendered image to both roles.

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

Frontmatter accepts only fields defined for that construct. Unknown fields warn but still compile. Metadata owned by another tool may use `x-` fields such as `x-owner`; Degardis reads the YAML value and otherwise ignores it.

### Body handling

When authored Markdown is placed on a generated page, Degardis only:

- shifts heading levels while preserving relative depth and text;
- turns inline references into links;
- folds hard-wrapped prose paragraphs into one line.

Code, tables, lists, explicit line breaks, link definitions, authored links, and authored order are preserved.

### Inline references

Use `[[kind:target]]` in prose to link to selected content:

```markdown
Read [[task:review]], [[principle:evidence]], or [[facet:python]].
Use [[guide:checklist]], [[asset:template.docx]], or [[script:check.py]].
```

`task`, `principle`, `facet`, and `guide` targets are bare ids. An `asset` or `script` target is the file's source-relative path or any trailing part of it made of whole segments: `check.py` and `lint/check.py` both name `scripts/lint/check.py`. A target that ends more than one selected file of its kind is refused; write more of the path. Tokens inside frontmatter, code, or another Markdown link remain literal; indentation that places a line in a list is not code. Every target must be selected into the bundle. An inline reference to a principle or guide shows only its title; the page's activation still decides when it is read.

### Links

Link to bundle content only through inline references. A Markdown link or image, a reference definition, or an HTML `href` or `src` whose destination is a relative or absolute path is refused, because the text lands on a page in another directory. Links to external addresses, such as `https:` or `mailto:`, and anchors on the same page are kept as written. A link inside code is a sample and is not checked.

See also: [YAML the compiler accepts](#yaml-the-compiler-accepts), [Names and references](#names-and-references).

### YAML the compiler accepts

`skill.yaml` and construct frontmatter accept mappings, lists, strings, integers, finite numbers, booleans, and null.

The following are refused:

| Form | Why |
| --- | --- |
| anchors/aliases (`&x`, `*x`) | node reuse |
| merge keys (`<<:`) | imported fields |
| explicit tags (`!!tag`) | unsupported types |
| bare dates | timestamp values |
| `.inf`, `.nan` | non-finite numbers |
| repeated fields | ambiguous value |
| non-string field names | field names must be text |

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

Knowledge dependencies use the same form:

```yaml
requires:
- audience
```

Every id in a reference list must name selected content and may appear only once in that list.

See also: [What you write](#what-you-write), [Knowledge units](#knowledge-units).

## What you write

### Tasks

A task is one recognizable class of requested work. Each task becomes one task page.

```markdown
---
title: Review a draft
recognize:
- the requester asks what is wrong or weak in a draft
- the requester asks whether a draft is ready to send
goal: Identify problems that would change the reader's response.
knowledge:
- audience
principles:
- evidence
guides:
- house-style
---

Read the whole draft before judging any part of it.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | router label and task-page heading |
| `recognize` | yes | request cues, one per list item |
| `goal` | yes | finished state the task reaches; rendered as **Goal** |
| `knowledge` | no | direct knowledge ids |
| `principles` | no | principle ids |
| `guides` | no | guide ids |

The body renders as **Approach**. A task with no body, knowledge, or guide still builds but warns.

### Routing

Recognition cues are the router; title, goal, and knowledge do not affect matching. The first task in manifest order with a matching cue is chosen.

### Task page order

Present sections appear in this order:

1. title
2. **Goal**
3. **Principles**
4. **Approach** — task body
5. **What you need to know** — **Concepts**, **Facts**, **Constraints**, **Guidance**
6. **Guides**

Recognition cues stay in `SKILL.md`. Within **Principles** and **Guides**, unconditional links come before conditional ones. Authored knowledge order is preserved within each knowledge kind.

See also: [Knowledge units](#knowledge-units), [Principles](#principles), [Guides](#guides).

### Knowledge units

Knowledge is reusable subject matter copied into every task closure that needs it.

```markdown
---
kind: concept
title: Audience
requires:
- source-material
---

The audience determines what must be explained and what may be assumed.
```

| Field | Required | Rule |
| --- | --- | --- |
| `kind` | yes | `concept`, `fact`, `constraint`, or `guidance` |
| `title` | yes | heading on task pages |
| `requires` | no | additional knowledge ids brought into the same closure |

The body must be non-empty.

### Kinds

A unit has one kind, which names what the unit states and the heading it appears under on task pages:

| Kind | Heading | The unit states |
| --- | --- | --- |
| `concept` | Concepts | a definition, model, or distinction |
| `fact` | Facts | an established value, figure, table, or truth |
| `constraint` | Constraints | behavior that must or must not occur |
| `guidance` | Guidance | how to act or choose |

Task pages render kinds in that order and preserve authored order within a kind. Kind changes nothing else in the bundle.

See also: [How knowledge reaches a page](#how-knowledge-reaches-a-page), [What you write](#what-you-write).

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

A task receives its direct knowledge plus all transitive `requires`. Direct units keep task order; required units follow in first-introduced order; grouping by knowledge kind happens afterward.

Prose creates no dependency. Requirement chains may not cycle. Selected knowledge that no task reaches warns and is omitted from generated task pages. A unit reached by several tasks is copied into each closure; inspection reports the resulting duplication cost.

See also: [What you write](#what-you-write), [Knowledge units](#knowledge-units), [Seeing what the compiler decided](#seeing-what-the-compiler-decided).

### Principles

A principle is a standard the agent's work must honor. Each named principle has one generated page containing its title and body.

```markdown
---
title: Evidence for claims
activation: Before making an externally visible claim
---

State the observation supporting each claim beside the claim.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | page heading and link text |
| `activation` | no | condition for opening the page; omitted means unconditional |

The body must be non-empty. The manifest and tasks reference principles by bare id. A selected principle that neither the manifest nor a task names warns.

A principle named in `skill.yaml` is linked from `SKILL.md`, which every task run reads; one named by a task is linked from that task's page. Naming a principle at both levels warns, and so does naming it from every task instead of at skill level.

### Activation

A principle has one activation, shown on its owner links rather than on its page. The agent reassesses conditions as work changes and reads an applicable principle before continuing the work it governs.

See also: [What you write](#what-you-write), [Guides](#guides).

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

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | index link text and page heading; unique across facets |
| `category` | no | index grouping label |
| `description` | no | text after the title in the index and under the page heading |
| `guides` | no | guide ids opened from this facet |

The body must be non-empty.

The facet index lists each facet's title, optional description, and link. When two or more categories exist, rows are grouped by category; otherwise the index is flat.

A facet's guides appear at the foot of its page. A file a `facets` pattern matches is selected as a facet, so select facet guides under `content.guides` from outside those patterns, for example `facets/guides/`.

See also: [Guides](#guides), [What you write](#what-you-write).

### Guides

A guide is detail a task or facet loads as a separate page.

```markdown
---
title: House style
activation: When the result will be published under the organization's name
---

Use the organization's publication rules.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | page heading and link text |
| `activation` | no | condition for opening the page; omitted means unconditional |

The body must be non-empty. Tasks and facets reference guides by bare id; an owner's guides are linked at the foot of its page. A selected guide with no owner or inline reference warns. Each selected guide has one generated page containing its title and body.

One guide may have several owners but keeps one page and one activation, shown on its owner links rather than on its page. The agent reassesses conditions as work changes and reads an applicable guide before continuing the work it governs.

See also: [What you write](#what-you-write), [Facets](#facets), [Principles](#principles).

### Scripts

`content.scripts` selects executable helpers. Each selected script is copied unchanged to the same path it has in the source, wherever the manifest selects it from, and is executable in both folder and ZIP builds, whatever permissions the source file has. A file selected as an asset is never executable, even under a `scripts/` directory.

An inline reference links a script:

```markdown
Run [[script:check.py]] before publishing.
```

The target is the script's source-relative path, or any trailing part of it made of whole segments. When it ends more than one selected script, as `check.py` ends both `scripts/check.py` and `tools/check.py`, the reference is refused until it names one, such as `tools/check.py`. A selected script with no inline reference warns because no reader reaches it.

See also: [The manifest](#the-manifest), [How a source file is read](#how-a-source-file-is-read).

### Assets

`content.assets` selects supporting files that are neither scripts nor guides. Selected assets are copied unchanged, including Markdown assets, to the same path they have in the source.

An inline reference links an asset:

```markdown
Use [[asset:template.docx]] for the final document.
```

The target is the asset's source-relative path, or any trailing part of it made of whole segments; one that ends more than one selected asset is refused until it names one. A selected asset with no inline reference warns.

The bundle may also contain generated support assets: PNG icon roles when `interface.icon` is set, and an instruction-register asset when the bundle contains at least one principle or guide page.

See also: [The manifest](#the-manifest), [How a source file is read](#how-a-source-file-is-read).

## Working with the compiler

### Checking a source

```console
degardis validate my-skill
```

Validation writes nothing, collects all findings, exits 1 on errors, and exits 0 otherwise. `--fail-on-warning` treats warnings as errors. `inspect` and `build` run the same checks.

Validation checks:

- manifest fields, content selection, interface, and icon;
- construct fields and required bodies;
- task, principle, knowledge, guide, and inline references, and links written by path;
- knowledge dependency cycles and unreachable knowledge;
- unused principles, guides, scripts, and assets;
- task routing and facet identity;
- generated page budgets, generated links, and path collisions, including paths that differ only in letter case.

A pass means the source can produce a complete bundle whose generated links resolve. It does not judge whether the skill's guidance is useful.

Every finding includes a check code. Run `degardis explain CODE` for its trigger, reason, and resolution. Unknown codes cause `explain` to list the codes supported by the installed version.

See also: [Seeing what the compiler decided](#seeing-what-the-compiler-decided), [Building a bundle](#building-a-bundle).

### Seeing what the compiler decided

`inspect` reports the same compilation and findings as `validate` in a compact, line-oriented form. `--only` and `--all` change output only.

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

The `skill` block's `size` row gives generated bytes per page class against that class's one-load budget: `SKILL.md` with its line count, the instruction-register asset, task pages (count, total, average, largest), principle pages, guide pages, and facet pages including the facet index, whose own size follows as `index`.

| Dimension | Row shape |
| --- | --- |
| `sources` | `KIND ID PATH BYTES` |
| `tasks` | `ID "TITLE" PAGE BYTES N knowledge`, then goal, `when` cues, guides, principles, linked |
| `knowledge` | `ID kind=KIND BYTES requires=... tasks=...` |
| `principles` | `ID PATH BYTES activation=ACTIVATION -> PLACEMENTS linked=PAGES page=PAGE` |
| `guides` | `ID PATH BYTES [ACTIVATION] -> OWNERS linked=PAGES` |
| `facets` | `ID "TITLE" CATEGORY BYTES linked=PAGES DESCRIPTION` |
| `scripts` | `ID PATH BYTES linked=PAGES` |
| `assets` | `ID PATH BYTES linked=PAGES` |
| `outputs` | `PATH BYTES MODE`, under a heading giving the file count and total bytes |
| `diagnostics` | `SEVERITY CODE LOCATION MESSAGE` |

For knowledge, `tasks` names pages carrying the unit. Principle placements name skill/task owners; `activation=always` means no condition. Guide owners are qualified as `task:ID` or `facet:ID`. `linked` names each page whose authored text links the task, principle, guide, facet, script, or asset by inline reference, as `task:ID`, `principle:ID`, `guide:ID`, or `facet:ID`; a reference in knowledge counts on every task page carrying that unit. Links the bundle writes itself are not counted: the root's task routes, the facet index, and owner links. For a principle or guide, owners and `linked` together are every page that links it. A task has a `linked` line only when some page links it. A script or asset ID is the shortest inline reference target that names that file alone. `outputs` MODE is the permission a build gives the file in either form.

The inspect report is the machine interface; builds do not emit a plan, closure, source map, coverage file, or build report.

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
- **Maximum read bytes by task** — every generated page one run of that task can be directed to read, each counted once: the root, the instruction-register asset, the task page, the facet index, and every principle, guide, and facet page reachable from them without opening another task's page.
- **Headroom** — smallest remaining one-load budget across the root and every task, principle, guide, and facet page; negative when a page is over its budget.

These measures describe structure and read cost, not behavioral quality.

### Source fingerprint

`--only identity` reports a source fingerprint tied to the manifest, selected files, interface icon, and compiler version; it identifies the exact compiled source.

See also: [Working with the compiler](#working-with-the-compiler), [How knowledge reaches a page](#how-knowledge-reaches-a-page).

### Building a bundle

```console
degardis build my-skill --output .artifacts
```

Builds write folders by default; `--zip` writes ZIP archives. `build` runs the same checks as `validate`, and source-validation errors prevent any output. `--fail-on-warning` applies the stricter warning policy before writing.

Each skill artifact is replaced atomically. A failed write leaves that skill's previous artifact unchanged; siblings already completed in the same run remain. A rebuild replaces the folder and ZIP with the same skill name.

The same source and compiler version produce byte-identical output across hosts.

### Page budgets

Root, task, principle, guide, and facet pages have warning-level size budgets, reported by `inspect --only skill`. The root is startup cost, a task page is one task load, and each separately opened page is an additional load.

Degardis does not truncate oversized pages, but a host may. A budget finding names the page's largest contributors.

See also: [Working with the compiler](#working-with-the-compiler), [The source folder](#the-source-folder).
