# Getting started

Degardis turns a source directory into an installable agent skill. This guide covers the shortest authoring loop; use the [Manual](manual.md) for format rules and the [CLI reference](cli.md) for command details.

Python 3.10 or newer is required.

## Install

```console
python -m pip install degardis
degardis --help
```

If `degardis` is not on your `PATH`, use `python -m degardis` instead. From a repository checkout, install with `python -m pip install -e .`.

## Create a source

```console
degardis init my-skill
```

The new source already validates and builds. Its `skill.yaml` declares the skill, and `tasks/primary.md` is its first task.

Think in **tasks** first: each task is a recognizable class of request, such as "summarize supplied material" or "review a draft." Shared information belongs in knowledge units; shared working rules in principles; situational variants in facets; separately loaded detail in guides.

Each construct is a Markdown file. The manifest selects its namespace, the file stem is its id, frontmatter contains fields, and the body contains authored content.

## Validate and inspect

```console
degardis validate my-skill
degardis inspect my-skill --only composition,principles
```

`validate` reports structural problems without writing files. `inspect` gives a compact view of what will reach each generated page; `composition` is useful for checking why a task received particular knowledge.

If a finding includes an unfamiliar code:

```console
degardis explain manifest.unknown-principle
```

A clean validation means the source can produce a complete bundle with valid references. It does not judge whether the instructions are useful, so read the generated pages and test the skill on real requests.

## Build

```console
degardis build my-skill --output .artifacts
```

Add `--zip` when the target host accepts an uploaded archive. Build into a separate output directory: rebuilding replaces the artifact with the same skill name.

Do not edit generated output. Change the source, validate, and rebuild.

## Try the repository example

From a repository clone:

```console
degardis validate examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

The example uses every source construct and is useful as a complete reference.

## Next

- [Manual](manual.md) — source format, fields, relationships, and authoring rules.
- [CLI reference](cli.md) — commands, options, and exit status.
- [Bundles](artifact-format.md) — generated files and rebuild behavior.
