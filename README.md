# Degardis

Degardis turns a structured AI skill source into a portable skill bundle. You write what your skill knows as small Markdown files and say which classes of work need which pieces. Degardis checks the structure and assembles one complete page per class of work, so the agent reads that page and starts.

Use Degardis when you want a skill to be easier to review, maintain, and rebuild than a hand-written collection of instructions.

## Start here

You need Python 3.10 or newer.

```console
python -m pip install degardis
degardis init my-skill
degardis validate my-skill
degardis build my-skill --output .artifacts
```

`init` writes a source that already compiles. `build` runs the same checks as `validate` and writes the bundle only when they pass. [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) walks through the loop, including the repository's worked example.

## What you write

| You write | Which is |
| --- | --- |
| a **task** | a recognizable class of work someone asks for |
| a **knowledge unit** | one reusable piece of what your skill knows: a concept, fact, constraint, or guidance |
| a **principle** | a standard the agent's work must honor across all of your tasks |
| a **facet** | guidance one aspect of the situation calls for, such as the audience, the material, or the rules in force |
| a **guide** | detail a task, a facet, or another guide opens as a separate page when it applies |

Each is one Markdown file with YAML frontmatter. The [reference manual](https://github.com/Khojasteh/degardis/blob/main/docs/manual.md) has one topic per construct.

## What you get

Each task becomes one page carrying everything it needs: its approach, the knowledge it names, and whatever that knowledge requires. Choices only the running agent can make stay with the agent: which tasks a request asks for, whether a hand-off applies, which facets the situation calls for, and whether a principle or guide applies.

All subject guidance is yours. Degardis adds only domain-neutral instructions for routing, reading, and conformance, and it never paraphrases, merges, summarizes, or drops what you wrote.

## Commands

| Command | Use it to |
| --- | --- |
| `init` | Write a new source tree that already compiles. |
| `list` | See the skills a path selects and their basic information. |
| `validate` | Check a source before you build or share it. |
| `build` | Create a folder or ZIP bundle. |
| `inspect` | Give an AI agent a compact report on a source and why each page carries what it carries. |
| `explain` | Learn how to fix a diagnostic reported by another command. |
| `manual` | Read the source authoring manual by topic, or all of it at once, without a source path. |

Run `degardis COMMAND --help` for the exact options. Only `init` and `build` write files.

## Documentation

| If you want to | Read |
| --- | --- |
| Install it and build your first skill | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand a part of a source, or look up a field | [Reference manual](https://github.com/Khojasteh/degardis/blob/main/docs/manual.md) |
| Look up a command, an option, or an exit status | [CLI reference](https://github.com/Khojasteh/degardis/blob/main/docs/cli.md) |
| Understand a built bundle | [Bundles](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |

## What a passing build does not tell you

Compilation establishes artifact integrity: the source compiles, the pages are complete, every link resolves. It does not establish that the skill works. Whether an agent holding the bundle does better work than one without it is a behavioral question, answered by using the skill against real situations — not by the compiler.

[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring) is a companion skill for agents that help create Degardis sources.
