# Degardis

Degardis turns a structured AI skill source into a portable skill bundle. You write what your skill knows as small Markdown files and say which kinds of work need which pieces. Degardis checks the structure and assembles one page per kind of work — complete, so the agent reads it and starts.

Use Degardis when you want a skill to be easier to review, maintain, and rebuild than a hand-written collection of instructions.

## Start here

You need Python 3.10 or newer.

```console
python -m pip install degardis
degardis init my-skill
degardis validate my-skill
degardis build my-skill --output .artifacts
```

`init` writes a source tree that already compiles, `validate` checks a source without changing files, and `build` writes the finished bundle — into a throwaway directory such as `.artifacts` while you are authoring. `build` runs the same checks as `validate` and writes nothing unless they pass, so run `validate` when the report on its own is what you want.

The repository ships one worked example. From a clone:

```console
degardis build examples/structured-summary --output .artifacts
```

## What you write

| You write | Which is |
| --- | --- |
| a **task** | a recognizable class of work someone asks for |
| a **knowledge unit** | one reusable piece of what your skill knows, classified as a concept, fact, constraint, or guidance |
| a **principle** | guidance that holds across several of your tasks rather than being about the subject matter |
| a **facet** | guidance one aspect of the situation calls for: the audience, the kind of material, the rules in force |
| a **guide** | detail a task or a facet opens as a separate page; activation states when it applies |

Each is one Markdown file. Its namespace says what construct it is, its filename is its id, its frontmatter holds its fields, and its body is its content. Knowledge lives together under `knowledge/`, and its required `kind` field is `concept`, `fact`, `constraint`, or `guidance`. Examples belong in the body of the knowledge they illustrate.

All subject guidance is yours. The compiler supplies only domain-neutral control instructions for routing, reading, and conformance; a principle is read from your skill's own `principles/` directory and nowhere else. The compiler never invents subject guidance.

## What the compiler does

It resolves what each task needs, follows what that knowledge itself requires, and compiles the whole closure into that task's page. Knowledge is grouped by the canonical kind order — concepts, facts, constraints, guidance — while preserving the author's order within each kind. Your decomposition is for whoever maintains the source; the agent should not have to follow it at run time.

It keeps the choices only the running agent can make: which task a request is, which facets the situation calls for, whether a principle or guide activation applies. Omitted activation applies unconditionally.

It does not rewrite what you wrote. It moves your material, adjusts heading levels, and turns your `[[kind:target]]` references into links — never paraphrasing, merging, summarizing, or dropping any of it. When a page comes out too large it says so and names what is on it; deciding what to cut is yours.

## Commands

| Command | Use it to |
| --- | --- |
| `init` | Write a new source tree that already compiles. |
| `list` | See the skills a path selects and their basic information. |
| `validate` | Check a source before you build or share it. |
| `build` | Create a folder or ZIP bundle. |
| `inspect` | Give an AI agent a compact report on a source and why each page carries what it carries. |
| `explain` | Learn how to fix a diagnostic reported by another command. |
| `manual` | Read the source authoring manual by topic, without a source path. |

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
