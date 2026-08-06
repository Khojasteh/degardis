# Authoring skills

This guide takes a skill author from an empty directory to a validated,
inspectable bundle. It uses a minimal `my-skill` source for the first build and
the repository's public
[`structured-summary`](../examples/structured-summary/) example for optional
features. For exact field constraints, see the [reference](reference.md).

## 1. Start with one outcome

Give a skill one outcome it can complete without another installed skill.
`structured-summary` owns turning supplied material into a summary for a
defined reader and purpose. The material can concern any subject.

Use a lowercase, hyphenated name of at most 64 characters. The directory name
and manifest `name` must match. Write the description in ordinary request
language so an agent can recognize when the skill applies:

```yaml
name: structured-summary
description: Turn supplied material into a clear, audience-appropriate summary.
```

Keep execution instructions out of the description. Put procedures in
workflows and reusable rules in entries.

## 2. Create the source layout

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
title: My Skill
format_version: 1
version: 0.1.0
description: Turn supplied notes into a concise action list.
primary_workflow: my-skill.run
interface:
  display_name: My Skill
  short_description: Turn notes into a concise action list
  default_prompt: Use $my-skill to turn these notes into an action list.
```

Create `my-skill/workflows/run.yaml`:

```yaml
id: my-skill.run
description: Extract a practical action list from supplied notes.
steps:
- action: inspect-notes
  instruction: >-
    Identify explicit tasks, owners, deadlines, and unresolved decisions in
    the supplied notes.
- action: write-actions
  instruction: >-
    Present the tasks as a concise checklist without inventing missing
    details.
```

From the directory containing `my-skill/`, verify the source and build its
first artifact:

```console
degardis validate my-skill
degardis build my-skill --output .artifacts
```

Success creates `.artifacts/my-skill/SKILL.md`. Keep editing the YAML source,
then validate and rebuild; generated files are replaceable output.

The canonical example shows the optional directories:

```text
structured-summary/
  skill.yaml
  entries/
    audience.yaml
    fidelity.yaml
  workflows/
    compose.yaml
    inspect.yaml
  profiles/
    detailed.yaml
    details/
      detailed.md
  scripts/
    list_headings.py
  assets/
    icon.svg
    template.md
```

Only `skill.yaml` and the primary workflow are universally required.

Add entries, supporting workflows, profiles, scripts, and assets only when
they materially improve repeated execution.

Degardis applies default content globs when `content` is omitted, so a
minimal source can use `workflows/*.yaml` without declaring it explicitly.

The manifest must still provide the required `interface` metadata shown in the
minimal manifest.

## 3. Write `skill.yaml`

The example manifest begins:

```yaml
name: structured-summary
title: Structured Summary
format_version: 1
version: 1.0.0
license: MIT
copyright: Copyright (c) 2026 Example Organization
description: Turn supplied material into a clear, audience-appropriate summary.
primary_workflow: structured-summary.compose
content:
  entries:
  - entries/*.yaml
  workflows:
  - workflows/*.yaml
  scripts:
  - scripts/*.py
  assets:
  - assets/*.md
profiles:
  directory: profiles
  defaults: []
interface:
  display_name: Structured Summary
  short_description: Turn supplied material into a clear summary
  icon: assets/icon.svg
  brand_color: "#5B4B8A"
  default_prompt: Use $structured-summary to summarize this material.
```

The version fields have separate meanings:

- `format_version` selects the Degardis source contract. The current compiler
  supports format 1 and rejects unsupported formats before building.
- `version` identifies the authored skill source.

Content globs are relative to the skill root and cannot escape it. Scripts and
assets are copied byte-for-byte. Icons are rendered to agent-compatible PNG
assets.

The three interface fields serve different readers:

- `display_name` labels the skill in an agent interface.
- `short_description` is a 25–64 character interface summary.
- `default_prompt` is a suggested invocation and must contain the exact
  `$structured-summary` skill token.

The top-level `description` is different: agents use it to decide when the
skill applies. Keep it specific even when the interface summary is shorter.

## 4. Put reusable rules in entries

An entry is a focused rule, not a procedure. For example:

```yaml
id: structured-summary.policy.fidelity
title: Stay faithful to the material
kind: policy
priority: 20
rule: Preserve the meaning and uncertainty of the supplied material without adding unsupported claims.
require:
- Distinguish explicit statements from reasonable but necessary interpretation.
- Retain qualifications that materially affect a conclusion.
```

Entry IDs must be unique within the skill.

The kinds this compiler knows are `principle`, `policy`, `heuristic`,
`pattern`, `constraint`, and `rule`, and `kind` defaults to `rule`. A kind
outside that list produces a warning, not an error, and the entry compiles with
the kind you declared. Source written for a later compiler therefore builds on
this one too. No manifest field lists the kinds: a skill's kinds come from the
entries it contains.

Use the optional `require`, `allow`, `reject`, `conditions`, `exceptions`, and
`examples` lists only where they clarify how the rule applies.

Give every entry a `title` and a `priority`. Both are optional, but the title is
what the always-loaded reference index shows, and the priority is what orders
it. If you omit either, Degardis warns you and names the default it used
instead.

## 5. Express procedures as workflows

The primary workflow is embedded in generated `SKILL.md`:

```yaml
id: structured-summary.compose
title: Compose a structured summary
description: Turn supplied material from any subject into a summary suited to its reader and purpose.
steps:
- action: establish-purpose
  instruction: Identify the intended reader, purpose, desired length, and supplied material.
- use: structured-summary.inspect
- action: select-content
  instruction: Choose the central ideas, supporting details, relationships, and qualifications needed for the purpose.
```

A step may be a non-empty string or a mapping. A mapping can use:

- `action` or `id` as its label;
- `instruction` as the work to perform;
- `when` as an agent-evaluated condition; and
- `use` to follow another workflow in the same skill.

A mapping must contain at least one of `use`, `action`, `id`, or `instruction`.
`use` cannot be combined with `action` or `instruction`, and it cannot
reference another skill. Supporting workflows are generated under
`references/workflows/`.

## 6. Add profiles only for material variants

Profiles are build-time additions for audiences, formats, technologies, or
environments that materially change execution:

```yaml
name: detailed
label: Detailed
description: Apply when the reader needs context, relationships, and supporting detail.
instructions:
- Explain how the main ideas relate to one another instead of presenting an isolated list.
- Include representative supporting detail while preserving the source's qualifications.
details_files:
- details/detailed.md
```

The filename and `name` must match. A profile needs a label, a selection
description, and at least one instruction. Use either inline `details` or
`details_files`, not both. Detail files must remain inside the skill and must
not contain a level-one heading.

Move shared guidance into the core workflow or entries. Delete a profile if it
adds only generic advice.

## 7. Use scripts and assets deliberately

Scripts provide necessary repeatable executable behavior. Assets are inputs
that an agent reads, copies, or fills in.

The example includes:

- `scripts/list_headings.py`, a deterministic helper for exposing the structure
  of Markdown material;
- `assets/template.md`, a starting structure for the summary; and
- `assets/icon.svg`, an interface icon source.

Keep instructions in YAML rather than hiding them in an asset.

Test every script with representative input and avoid unsafe or
environment-specific behavior unless the skill explicitly owns that
environment.

Content globs must stay inside the skill directory. Icon paths are the
exception: relative icon paths may resolve outside the skill so several skills
can share a source image. The generated bundle remains self-contained because
Degardis converts and copies the selected icons.


Content patterns read from top to bottom. A pattern prefixed with `!` removes
what the patterns above it selected, and a later pattern can put a file back:

```yaml
content:
  assets:
  - assets/**/*
  - "!assets/drafts/**/*"
  - assets/drafts/keep.md
```

Quote any pattern that begins with `!`. Left unquoted, YAML reads it as a type
tag and the manifest does not parse.

You do not have to exclude the files your tools leave behind. Hidden and system
files, anything inside a dot-prefixed directory such as `.git` or `.venv`,
Python bytecode, and host bookkeeping like `.DS_Store` and `Thumbs.db` are never
content, whatever the patterns say. See
[content patterns](reference.md#content-configuration) for the full rules.

## 8. Validate, build, and inspect

Validate your source without writing output:

```console
degardis validate my-skill
```

Inspect metadata and profiles:

```console
degardis list my-skill
```

Every message a report prints ends with the check that produced it. To find out
what a check means and how to satisfy it, pass its code to `explain`, as many at
a time as the report gave you:

```console
degardis explain entry.missing-priority entry.missing-title
```

Build and inspect the artifact:

```console
degardis build my-skill --output .artifacts
```

Inspect:

- `SKILL.md` frontmatter, primary workflow, and links;
- generated entries and supporting workflows;
- any selected profile reference;
- `agents/openai.yaml`;
- copied scripts and assets; and
- generated icon files.

Some items are emitted only when the source declares them. To inspect a
profile and icons, build the canonical example's detailed variant:

```console
degardis build examples/structured-summary --profile detailed --output .artifacts
```

Run the bundled scripts with representative input as a separate check;
`degardis validate` verifies source structure and generated links but does not
execute scripts.

Also exercise ZIP output when it is a distribution format:

```console
degardis build my-skill --zip --output .artifacts
```

If you are an AI agent rather than a person, `degardis agent my-skill --all`
reports all of the above in one pass: every entry, workflow, and profile with
its authored path and generated size, the files a build would write, what the
skill costs to load, and every error and warning found.

## 9. Preserve the example boundary

This repository contains exactly one public example so its documentation and
compiler can evolve together.

Private compiler fixtures may use multiple synthetic skills to test collection
selection, conflicts, and multi-skill builds. They are test data and must not
become tutorial dependencies.

## Final checklist

- The directory and manifest names match.
- `format_version` is supported and `version` identifies the skill source.
- The description states one recognizable outcome.
- The primary workflow is complete and independently executable.
- Entries are focused rules rather than workflow fragments.
- Every profile materially changes execution.
- Workflow composition stays inside the skill.
- Scripts are necessary and tested; assets are genuine output inputs.
- `degardis validate` succeeds, and every warning it reports is either fixed
  or a deliberate choice.
- Folder and ZIP artifacts contain only expected files.
