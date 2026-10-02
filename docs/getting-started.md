# Getting started

Degardis turns a source directory into an installable agent skill. This guide covers the shortest authoring loop; use the [reference manual](manual.md) for format rules and the [CLI reference](cli.md) for command details.

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

The new source already validates and builds. Its `skill.yaml` declares the skill, and `tasks/primary.md` is its first task. The [reference manual](manual.md#what-a-source-is) describes each construct you can add and its fields.

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

## Build

```console
degardis build my-skill --output .artifacts
```

Add `--zip` when the target host accepts an uploaded archive. [Bundles](artifact-format.md) describes what the build writes, and [Building a bundle](manual.md#building-a-bundle) how a rebuild replaces it.

## Try the repository example

From a repository clone:

```console
degardis validate examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

The example uses every source construct and is useful as a complete reference.

## Next

- [Reference manual](manual.md) — source format, fields, relationships, and authoring rules.
- [CLI reference](cli.md) — commands, options, and exit status.
- [Bundles](artifact-format.md) — generated files and runtime behavior.
