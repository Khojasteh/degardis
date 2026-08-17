# Degardis

Degardis is a command-line compiler for portable Agent Skills.

You write a skill once as structured YAML: the workflows it runs, the policies
and rules that bind them, the protocols that carry state across steps, and the
reusable patterns, advisory heuristics, and supplementary guidance around them.
Degardis checks that source, lowers every binding requirement into the workflow
step where it is enforced, and renders an installable bundle for Claude, Codex,
Copilot, Cursor, Roo, or ChatGPT. Your source stays authoritative; the bundle is
generated output you can replace at any time.

Compiling buys you what writing Markdown by hand cannot: every requirement you
declare is checked to have reached a step. A policy that matched no reachable
node, a rule that was never lowered, or a link where required behavior belongs is
a reported finding rather than a silent gap in the bundle. One run reports every
error and warning it found, and every finding carries a check code you can look
up.

## Author with an agent

[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring)
is a skill for building skills. Hand it to your agent and it guides the whole
loop: it draws a skill's boundary so the right requests select it and the wrong
ones do not, holds down what the skill costs to load and to run, keeps
credentials and private material out of both sources and bundles, establishes how
the skill really behaves by trialling it blind, then validates, packages, and
installs it with this compiler.

The compiler accepts one source format and converts none, so use the authoring
skill version published for the compiler version you have installed.

## Quick start

You need Python 3.10 or newer.

```console
python -m pip install degardis
degardis --version
```

For an isolated command-line install, use `pipx install degardis`. To work from
a clone of this repository instead, install it in place with
`python -m pip install -e .`.

The example below ships in this repository, so run these commands from a clone
of it:

```console
degardis list examples/structured-summary
degardis validate examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

The build writes one ready-to-install folder per skill; add `--zip` for a single
archive instead.

Degardis only writes inside the output directory you choose, and rebuilding a
skill replaces that skill's artifacts there. Before you build directly into an
agent's skill directory, read
[how Degardis replaces artifacts](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md#replace-an-artifact).

## Commands

```console
degardis list PATH [PATH ...]
degardis validate PATH [PATH ...]
degardis build PATH [PATH ...] --output PATH [--zip]
degardis inspect PATH [PATH ...]
degardis explain CODE [CODE ...]
```

- `list` shows metadata and available profiles as a readable summary.
- `validate` checks a skill source and reports every problem it finds. This is
  the one to gate on in CI.
- `build` creates the installable folder or ZIP.
- `inspect` reports what a skill compiles to and where each requirement was
  enforced, in a compact form meant for AI agents rather than for people.
- `explain` describes the checks behind reported diagnostic codes.

Run `degardis COMMAND --help` for exact options and examples. Only `build`
writes files.

For exact command behavior, source schemas, and the Python API, see the
[reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md).

## Source format

A source declares `format_version: 2`, and each selected YAML file defines one
construct. Degardis 2.0 redefines that format: a skill written for Degardis 1.x
is rewritten against the current schemas rather than upgraded. The
[authoring guide](https://github.com/Khojasteh/degardis/blob/main/docs/authoring-guide.md)
covers every construct, and `degardis validate` reports what a partial rewrite
still needs. To keep building an existing 1.x source unchanged, stay on the
Degardis 1.x release that reads it.

## Documentation

| Reader goal | Document |
| --- | --- |
| Build and install the example | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand the source and artifact models | [Concepts](https://github.com/Khojasteh/degardis/blob/main/docs/concepts.md) |
| Create or modify a skill with an agent | [Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring) |
| Create or modify a skill by hand | [Authoring guide](https://github.com/Khojasteh/degardis/blob/main/docs/authoring-guide.md) |
| Look up commands, schemas, or the Python API | [Reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md) |
| Inspect and install generated output | [Artifact format](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |
