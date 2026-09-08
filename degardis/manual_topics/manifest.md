## The manifest

`skill.yaml` is the one required file at the top of a skill. It answers three
questions: what this skill is called, when an agent should use it, where a
request enters it, and which files belong in it. It also supplies the short
name and prompt that an agent host shows people.

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | Yes | Lowercase, hyphenated name; it matches the source directory name. |
| `format_version` | Yes | The source format version: `{{format_version}}`. |
| `version` | Yes | Your skill release version. |
| `description` | Yes | When an agent host should select the skill; at most 1024 characters. |
| `entrypoints` | Yes | [Entrypoints](#entrypoints) a request is routed to. |
| `content` | Yes | [Patterns](#content-selection) selecting every file the skill ships. |
| `interface` | Yes | Host-facing display metadata. |
| `license` | No | License name or a bundled license reference. |
| `copyright` | No | Copyright notice. |
| `policies` | No | [Policies](#policies) active for the full run. |
| `rules` | No | [Rules](#rules) considered for the full run. |
| `protocols` | No | [Protocols](#protocols) active for the full run. |
| `guidance` | No | [Guidance](#guidance) shown for the full run. |

```yaml
name: structured-summary
format_version: {{format_version}}
version: 1.0.0
description: Turn supplied material into a clear, audience-appropriate summary.
entrypoints:
  summarize:
    target: compose
guidance:
- clear-reporting
content:
  workflows:
  - workflows/*.yaml
  guidance:
  - guidance/*.yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  default_prompt: Use {name} to summarize this material.
```

`format_version` is an integer, and it names the format the source is written
in rather than the compiler. A source older than the installed compiler reads,
or newer than it reads, is reported so that you upgrade the source deliberately
instead of compiling it under rules it was not written for.

The four binding fields name requirements that apply from the start of the
skill to its end. Use them only when the requirement really does apply
throughout, and name each construct once: binding one construct twice in a list
is reported, and so is binding it here and again at a workflow it reaches. A
manifest binds no pattern and no heuristic, because neither is binding by being
available—a pattern is chosen by a workflow step, and a heuristic by a decision
or gate.
