# Authoring a skill

This guide shows how to make a small skill, then explains when to add the other
parts of the source format. For every field and allowed value, use the
[Manual](manual.md) as the lookup page, in the browser or from
`degardis manual TOPIC`.

## Start with one outcome

Give a skill one outcome it can deliver on its own. The included
[`structured-summary`](../examples/structured-summary/) example turns supplied
material into a summary for a stated reader and purpose.

Choose a lowercase, hyphenated name. The skill directory and the manifest name
must match. Write the description as the kind of request that should select the
skill, not as instructions for running it.

## Create the smallest useful source

Start with a manifest and one workflow:

```text
my-skill/
  skill.yaml
  workflows/
    run.yaml
```

Create `my-skill/skill.yaml`:

```yaml
name: my-skill
format_version: 2
version: 0.1.0
description: Turn supplied notes into a concise action list.
entrypoints:
  run:
    target: run
content:
  workflows:
  - workflows/*.yaml
interface:
  display_name: My Skill
  short_description: Turn notes into an action list
  default_prompt: Use {name} to turn these notes into an action list.
```

Create `my-skill/workflows/run.yaml`:

```yaml
title: Turn notes into an action list
description: Read the supplied notes and report the actions they commit someone to.
inputs:
  notes:
    type: string
outcomes:
  listed: {}
entry: read-notes
steps:
  read-notes:
    action: Identify every task, owner, deadline, and unresolved decision the notes state.
    uses: [input.notes]
    produces:
      actions:
        type: {list: string}
    next: report
  report:
    action: Write the actions as a checklist, and invent no detail the notes do not state.
    next: done
  done:
    return:
      outcome: listed
```

Validate and build from the directory that contains `my-skill/`:

```console
degardis validate my-skill
degardis build my-skill --output .artifacts
```

Keep editing the YAML source. The folder under `.artifacts` is generated output,
so replace it by rebuilding instead of editing it directly.

## Write a useful manifest

The manifest answers four questions:

- What is this skill called, and when should an agent use it?
- Which workflow starts the skill?
- Which source and support files belong in the bundle?
- What should an agent host display?

`format_version` identifies the source format. `version` identifies your own
skill release. The `content` mapping selects each file that ships; files are not
included merely because they are in a familiar directory.

The three required `interface` fields have different jobs:

- `display_name` is the name people see in a host.
- `short_description` is the short host-facing summary.
- `default_prompt` is a suggested way to invoke the skill. Use `{name}` exactly
  as written so each host can render its own skill-name syntax.

Keep the top-level `description` specific. It helps an agent host decide whether
the skill applies to a request.

## Build the workflow

A workflow states what it receives, how it proceeds, and what it returns. Every
reachable path must finish at one of its declared outcomes.

Use the step form that matches the work:

| Form | Use it when |
| --- | --- |
| `action` | The agent performs one action and may produce a value. |
| `branch` | A declared expression chooses the route. |
| `decide` | The agent chooses among named alternatives. |
| `gate` | The agent records one of several stated conditions. |
| `use` | Another workflow in this skill performs the next part. |
| `pattern` | A reusable procedure performs the next part. |
| `return` | The workflow finishes with an outcome. |

Declare values where they enter or are produced, then refer to them by name. For
example, an action can read `input.material`, produce `result.inspection`, and a
later step can use that result. This makes the information each step needs clear
to both the author and the agent.

A value has to be available on every path that reaches a reader of it. When a
branch can skip the action that produces one, give that value a `default` and it
holds what you wrote wherever the branch skipped it, so a later step can read it
either way.

Write every command as a complete instruction. A reader should understand what
to do from the command where it appears, without inferring it from a title.

Split a second workflow out with `use` when that part has a clear purpose of its
own. Supply its declared inputs and handle every outcome it can return.

## Add requirements in the right place

Choose a construct by the role it plays, not by the wording you happen to have.

| If the content is | Use |
| --- | --- |
| A standing boundary with related requirements | A policy |
| One requirement that applies only in a stated condition | A rule |
| A requirement that opens, changes, and closes across steps | A protocol |
| A reusable sequence of actions | A pattern |
| A preference among valid choices | A heuristic |
| Useful context | Guidance |
| Optional help for a recurring situation | A profile |

Policies, rules, and protocols are binding. Put a requirement in one of those
or in the workflow itself. Heuristics, guidance, profiles, and reference pages
can help an agent, but they must not be the only place a required action appears.

### Policies and rules

Policies and rules use selectors to say which workflow steps they affect. First,
give the relevant steps clear `subjects` and, when useful, `effects` tags:

```yaml
write-summary:
  subjects: [summary.write]
  effects: [workspace.write]
```

Then select that work from a policy provision or rule:

```yaml
summary: Keep every claim inside what the supplied material supports.
phase: before
match:
  subjects: [summary.write]
require: Establish support for each claim before writing it.
verify:
  confirm: Each claim is supported by the supplied material.
```

Use `before` when something must be established before a step. Use `during`
when the requirement shapes how an action is performed. Use `after` for work
that must follow a step, and `before-return` for work required before an outcome
is returned. The manual lists the full selector and phase rules.

### Protocols

Use a protocol only when a requirement has state that crosses a boundary. For
example, a skill can keep evidence after inspection and require it to be used
before the workflow ends. A protocol declares the allowed states, its initial
and accepting states, and the hooks that move between them.

If the requirement is satisfied at one step, prefer a policy provision or rule.

### Patterns, heuristics, and guidance

A pattern is a reusable procedure selected by a `pattern` step. Give it typed
inputs and a sequence of commands. Use it when the same method belongs in more
than one workflow.

A heuristic helps an agent choose between valid options. Attach one to a
`decide` or `gate` step; do not use it as proof that a requirement was met.

Guidance is concise context that may help at the skill, workflow, or step level.
Keep required behavior out of guidance and its linked references.

## Use profiles and support files deliberately

Profiles are optional guidance for a situation such as a reader who needs a
different level of detail. The core workflow must not require an agent to find
or use one.

References are supporting Markdown. Scripts are helpers an agent may run, and
assets are files it may read, copy, or fill in. Select all of them explicitly in
`content`. Review and test scripts with representative input before you ship a
skill that uses them.

Use `/` in every content pattern, even on Windows. Quote a pattern that starts
with `!`; it excludes files selected earlier in the same list.

## Write YAML safely

Quote a value when you mean text that YAML might read as another kind of value:

```yaml
summary: "no"
version: "1.10"
window: "1:30"
```

Use YAML comments for author-only information, such as explanations or design
notes. They help the people maintaining the source but do not become part of
the installed skill.

## Review before sharing

Use this loop as you work:

```console
degardis validate my-skill
degardis list my-skill
degardis build my-skill --output .artifacts
```

Use `inspect` when an AI agent needs a compact report about the source or the
generated skill. Read the built skill before sharing it: confirm that each
instruction is clear at the point where it is needed and that required behavior
is not hidden in optional material.

Before release, check that:

- the manifest name and directory name match;
- every path ends at a declared outcome;
- every value is declared before a later step reads it;
- each policy, rule, and protocol is used at the scope where it matters;
- profiles and references are optional support, not required execution;
- scripts are necessary, reviewed, and tested; and
- the folder or ZIP contains only the files you expect.
