### The manifest

`skill.yaml` declares skill identity, task order, skill-level principles, selected content, and host interface.

```yaml
name: structured-summary
format_version: {{format_version}}
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
| `format_version` | yes | the integer {{format_version}} |
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
