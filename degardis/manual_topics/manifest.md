### The manifest

`skill.yaml` declares skill identity, task order, skill-level principles, selected content, and host interface.

```yaml
name: structured-summary
format_version: {{format_version}}
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
- `format_version` (required) — the integer {{format_version}}.
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
