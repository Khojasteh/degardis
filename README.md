# Degardis

Degardis helps you turn a structured AI skill source into a portable skill
bundle. You describe the skill in YAML: what it does, the choices it can make,
and the requirements it must follow. Degardis checks the structure, then builds
the Markdown, supporting files, and metadata that an agent host can use.

Use Degardis when you want a skill to be easier to review, maintain, and rebuild
than a hand-written collection of instructions.

## Start here

You need Python 3.10 or newer.

```console
python -m pip install degardis
degardis validate examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

The example is included in this repository, so run the last two commands from a
clone of it. `validate` checks the source without changing files. `build` writes
the finished bundle under the output directory you choose. Use a throwaway
directory such as `.artifacts` while you are authoring.

## What the commands do

| Command | Use it to |
| --- | --- |
| `list` | See the skills selected by a path and their basic information. |
| `validate` | Check a source before you build or share it. |
| `build` | Create a folder or ZIP bundle. |
| `inspect` | Give an AI agent a compact report about a source and its build result. |
| `explain` | Learn how to fix a diagnostic reported by another command. |
| `manual` | Read the source authoring manual by topic, without a source path. |

Run `degardis COMMAND --help` for the exact options and examples. Only `build`
writes files.

## Documentation

| If you want to | Read |
| --- | --- |
| Build the included example | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand the parts of a skill or look up YAML fields | [Manual](https://github.com/Khojasteh/degardis/blob/main/docs/manual.md) |
| Create or change a skill by hand | [Authoring guide](https://github.com/Khojasteh/degardis/blob/main/docs/authoring-guide.md) |
| Look up a command | [CLI reference](https://github.com/Khojasteh/degardis/blob/main/docs/cli.md) |
| Understand a built bundle | [Bundles](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |

[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring)
is a companion skill for agents that help create Degardis sources.
