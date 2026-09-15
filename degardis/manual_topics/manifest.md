## Declaring the skill

### The manifest

`skill.yaml` says what the skill is and which files belong to it. It names the
skill's tasks, in the order the root page routes between them, and it may name
principles the skill uses; knowledge and profile ids are discovered from the
files `content` selects.

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
  profiles:
  - profiles/*.md
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
| `description` | yes | one sentence a host reads when choosing among many skills |
| `purpose` | no | a short paragraph the agent reads once this skill is selected |
| `principles` | no | principles the skill needs, by bare id; each principle's own activation decides whether it must be read |
| `tasks` | yes | every task the skill has, by bare id, in the order the root page lists them |
| `content` | yes | which files the skill ships, by construct namespace |
| `interface` | yes | how a host displays and invokes the skill |
| `license` | no | the licence the skill is published under |
| `copyright` | no | the copyright line |

`tasks` names every task, and only tasks that exist: a name with no
`tasks/<id>.md` beside it is an error, and so is a selected task file the field
does not name. The order is yours and is the order the root page lists the
routes in, so put the work most requests ask for first. Nothing else about
routing is yours to place: each task states its own recognition cues.

`description` is read before the skill is chosen; `purpose` is read after, by the
agent about to work. A manifest with no purpose has its description stand in.

### Selecting content

Each `content` key holds glob patterns, applied in order. A pattern prefixed with
`!` removes what the patterns before it selected, as in `.gitignore`.

| Key | Selected files |
| --- | --- |
| `tasks` | task Markdown files |
| `principles` | principle Markdown files |
| `knowledge` | knowledge-unit Markdown files; `kind` is `concept`, `fact`, `constraint`, or `guidance` |
| `profiles` | profile Markdown files |
| `guides` | guide Markdown files |
| `scripts` | executable helpers |
| `assets` | supporting files |

`content.tasks` is the only required key: a task is the only thing a request is
routed to. It selects the files; the top-level `tasks` field orders them, and
the two must name the same set.

A key you leave out says the skill ships none of that content. A key you declare
says it ships some, so each declared key and every positive pattern must resolve
to a file. Patterns are matched case-sensitively and use `/` on every platform.

Hidden files, platform bookkeeping such as `.DS_Store` and `Thumbs.db`, and
Python bytecode are never selected by a wildcard.
