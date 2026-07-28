# Degardis

Degardis is a command-line compiler for authors of portable Agent Skills. It
turns structured YAML sources into self-contained bundles for Claude, Codex,
Copilot, Cursor, Roo, and ChatGPT. Before writing an artifact, it validates the
source, selected profiles, generated paths, and generated links.

Authoring stays separate from generated output: edit the source files, validate
them, and rebuild either an installable folder or a distributable ZIP.

## Quick start

Degardis requires Python 3.10 or later. Install it from PyPI:

```console
python -m pip install degardis
degardis --version
```

For an isolated command-line installation, use `pipx install degardis`.

To work on Degardis from this repository instead:

```console
python -m pip install -e .
degardis validate examples/structured-summary
degardis list examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

The successful build ends with `Summary: 1 skill built as folder.` and reports
the artifact path. The generated folder is ready to inspect or install:

```text
.artifacts/structured-summary/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
  assets/
```

Degardis writes only beneath the requested output root. Rebuilding a skill
replaces that skill's existing folder and ZIP there, while preserving unrelated
entries. See [Artifact format](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md#replace-an-artifact)
before building directly into an agent's skill directory.

Add the example's optional profile or produce a ZIP:

```console
degardis build examples/structured-summary --profile detailed --output .artifacts
degardis build examples/structured-summary --zip --output .artifacts
```

`examples/structured-summary` is the canonical public example used throughout
the guides and CLI help. It summarizes supplied material from any subject;
synthetic skills under `tests/fixtures` are compiler test data.

## Companion skills

The [Degardis skills catalog](https://github.com/Khojasteh/degardis-skills)
contains reusable skills authored with Degardis.

For the smoothest authoring experience, use
[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring).
It guides a skill from initial design through review, validation, packaging,
and installation while applying Degardis conventions across manifests,
workflows, entries, profiles, scripts, and assets.

## Commands

```console
degardis list PATH [PATH ...]
degardis validate PATH [PATH ...]
degardis build PATH [PATH ...] --output PATH [--profile [SKILL:]PROFILE] [--zip]
```

Run `degardis COMMAND --help` for exact options and examples. All commands
accept individual skill directories, directories containing skills at any
depth, or a mixture of both. This lets a source tree group skills into
subdirectories while building all of them with one command.

An unqualified profile name applies to every selected skill that defines it.
`SKILL:PROFILE` selects one owner, and `all` selects all available profiles.
Supplying explicit selectors replaces manifest defaults for that build.

For exact command behavior, profile selectors, source schemas, and the Python
API, see the [reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md).

## Documentation

| Reader goal                                  | Document                                   |
| -------------------------------------------- | ------------------------------------------ |
| Build and install the example                | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand the source and artifact models    | [Concepts](https://github.com/Khojasteh/degardis/blob/main/docs/concepts.md) |
| Create or modify a skill                     | [Authoring guide](https://github.com/Khojasteh/degardis/blob/main/docs/authoring-guide.md) |
| Look up commands, schemas, or the Python API | [Reference](https://github.com/Khojasteh/degardis/blob/main/docs/reference.md) |
| Inspect and install generated output         | [Artifact format](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |

## Development

```console
python -m unittest discover -s tests -v
python -m degardis validate examples/structured-summary
python -m degardis build examples/structured-summary --profile all --output .artifacts
```
