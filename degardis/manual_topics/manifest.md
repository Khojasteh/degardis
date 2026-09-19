## Declaring the skill

### The manifest

`skill.yaml` identifies the skill, orders its tasks, names skill-level
principles, selects content, and defines the host interface.

```yaml
name: structured-summary
format_version: {{format_version}}
version: 2.0.0
license: MIT
copyright: Copyright (c) 2026 Example Organization
description: Turn supplied material into a clear, audience-appropriate summary.
purpose: >-
  Work from material someone has handed you and give them back something
  shorter that they can act on.
principles:
- evidence
- reporting
tasks:
- summarize
- brief
content:
  tasks:
  - tasks/*.md
  principles:
  - principles/*.md
  knowledge:
  - knowledge/*.md
  facets:
  - facets/*.md
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  default_prompt: Use {name} to summarize this material.
```

| Field | Required | What it is |
| --- | --- | --- |
| `name` | yes | lowercase letters, digits, single hyphens; must match the directory name |
| `format_version` | yes | the integer {{format_version}} |
| `version` | yes | the skill's own version |
| `description` | yes | one sentence a host reads when choosing among many skills, up to about 1024 characters |
| `purpose` | no | a short paragraph the agent reads once this skill is selected |
| `principles` | no | principles the skill needs, by bare id; each principle's own activation decides whether it must be read |
| `tasks` | yes | every task the skill has, by bare id, in the order the root page lists them |
| `content` | yes | which files the skill ships, by construct namespace |
| `interface` | yes | how a host displays and invokes the skill |
| `license` | no | the licence the skill is published under |
| `copyright` | no | the copyright line |

`tasks` must name every selected task exactly once. Its order is the root's route
order; each task supplies its own recognition cues.

`description` is read before the skill is chosen; `purpose` is read after, by the
agent about to work. A manifest with no purpose has its description stand in.

Every unprefixed field is reserved for Degardis, so an unrecognized manifest
field is an error. Metadata another tool owns goes in an `x-` field, such as
`x-owner`, at the top of `skill.yaml`: Degardis parses its value as YAML and
otherwise ignores it. `content` and `interface` take no `x-` fields.

### Selecting content

Each `content` key holds ordered glob patterns. A pattern prefixed with `!`
removes earlier matches, as in `.gitignore`.

| Key | Selected files |
| --- | --- |
| `tasks` | task Markdown files |
| `principles` | principle Markdown files |
| `knowledge` | knowledge-unit Markdown files; `kind` is `concept`, `fact`, `constraint`, or `guidance` |
| `guides` | guide Markdown files |
| `facets` | facet Markdown files |
| `scripts` | executable helpers |
| `assets` | supporting files |

`content.tasks` is the only required key. It selects task files; top-level
`tasks` must name the same set.

An omitted key ships none of that content. A declared key and each positive
pattern must select a file. Matching is case-sensitive and uses `/` on every
platform.

A wildcard never selects what the author does not see or did not write:
anything under a dot-prefixed or filesystem-hidden directory, platform
bookkeeping such as `.DS_Store` and `Thumbs.db`, and Python bytecode. A pattern
that spells the dot-prefixed path out, or that names a file without any
wildcard, selects what it names.
