# Degardis

Degardis is a command-line compiler for portable Agent Skills.

You write a skill once as structured YAML source. Degardis validates it,
renders agent-ready Markdown and interface metadata, and packages everything
into a self-contained bundle for Claude, Codex, Copilot, Cursor, Roo, or
ChatGPT. Your source stays authoritative; the bundle is generated output you
can replace at any time.

## Quick start

You need Python 3.10 or newer.

Install Degardis from PyPI:

```console
python -m pip install degardis
degardis --version
```

For an isolated command-line install, use `pipx install degardis`.

To use this repository instead:

```console
python -m pip install -e .
degardis validate examples/structured-summary
degardis list examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

A successful build reports the artifact path and ends with:

```text
Summary: 1 skill built as folder, 0 warnings.
```

The generated folder is ready to inspect or install:

```text
.artifacts/structured-summary/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
  assets/
```

Degardis only writes inside the output directory you choose. Rebuilding a skill
replaces that skill's folder and ZIP in that directory, but leaves everything
else untouched. Before you build directly into an agent's skill directory, read
[how Degardis replaces artifacts](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md#replace-an-artifact).

Add the example's optional profile or build a ZIP:

```console
degardis build examples/structured-summary --profile detailed --output .artifacts
degardis build examples/structured-summary --zip --output .artifacts
```

`examples/structured-summary` is the canonical example used throughout these
guides. It summarizes material on any subject. The synthetic skills under
`tests/fixtures` are compiler test data, not examples.

## Companion skills

The [Degardis skills catalog](https://github.com/Khojasteh/degardis-skills)
contains reusable skills built with Degardis.

For the best authoring experience, try
[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring).
It guides you from initial design through review, validation, packaging, and
installation, and it follows Degardis conventions for every part of a skill.

## Commands

```console
degardis list PATH [PATH ...]
degardis validate PATH [PATH ...]
degardis build PATH [PATH ...] --output PATH [--profile [SKILL:]PROFILE] [--zip]
degardis agent PATH [PATH ...] [--only DIMENSION] [--all] [--profile PROFILE] [--baseline REF]
degardis explain CODE [CODE ...]
```

- `list` shows metadata and available profiles.
- `validate` checks a skill source and reports every problem it finds.
- `build` creates the installable folder or ZIP.
- `agent` reports full skill intelligence in a compact form meant for AI
  agents, not humans. It covers entries, workflows, profiles, generated files,
  the workflow graph, loading cost, and diagnostics. `--baseline REF` also
  reports what a skill cost at a git revision and how much your edits changed
  it, without checking that revision out.
- `explain` describes the checks behind reported diagnostic codes: what
  triggers each one, why it matters, and a failing and passing example. Pass as
  many codes as a report gave you.

Run `degardis COMMAND --help` for exact options and examples.

All commands accept individual skill directories, directories that contain
skills at any depth, or a mix of both. This lets you group skills into
subdirectories and build them all with one command.

An unqualified profile name applies to every selected skill that defines it.
`SKILL:PROFILE` selects one skill, and `all` selects every available profile.
A build includes a profile only when `--profile` names it; without the option,
the bundle ships none.

For exact command behavior, profile selectors, source schemas, and the Python
API, see the [reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md).

## Documentation

| Reader goal | Document |
| --- | --- |
| Build and install the example | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand the source and artifact models | [Concepts](https://github.com/Khojasteh/degardis/blob/main/docs/concepts.md) |
| Create or modify a skill | [Authoring guide](https://github.com/Khojasteh/degardis/blob/main/docs/authoring-guide.md) |
| Look up commands, schemas, or the Python API | [Reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md) |
| Inspect and install generated output | [Artifact format](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |

## Development

```console
python -m unittest discover -s tests -v
python -m degardis validate examples/structured-summary
python -m degardis build examples/structured-summary --profile all --output .artifacts
```
