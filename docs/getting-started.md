# Getting started

This tutorial validates, builds, and installs the repository's canonical
`structured-summary` example. You need Python 3.10 or later, a local checkout,
and a terminal at the repository root.

## Install Degardis

```console
python -m pip install degardis
degardis --help
```

This installs Degardis from PyPI. Contributors can instead install the current
checkout with `python -m pip install -e .`. If your shell cannot find
the `degardis` command after installation, use `python -m degardis` in its
place in the commands below.

## Validate the source

```console
degardis validate examples/structured-summary
```

Expected result:

```text
Validation

[PASS] Structured Summary (structured-summary)

Summary: 1 passed, 0 failed, 1 total.
```

Validation reads the source without creating an artifact. The manifest at
[`examples/structured-summary/skill.yaml`](../examples/structured-summary/skill.yaml)
declares source format 1 and skill version 1.0.0.

## Inspect available profiles

```console
degardis list examples/structured-summary
```

The output identifies the skill, its version, optional `detailed` profile,
bundled scripts, legal metadata, and absolute source path. Look for these
lines; the source path differs by machine:

```text
Profiles    detailed
Scripts     Yes
```

## Build the bundle

```console
degardis build examples/structured-summary --output .artifacts
```

Expected result, with a machine-specific artifact path:

```text
Build

[BUILT] Structured Summary (structured-summary)
  Artifact    <repository-path>/.artifacts/structured-summary

Summary: 1 skill built as folder.
```

Inspect the generated folder:

```text
.artifacts/structured-summary/
  SKILL.md
  agents/
    openai.yaml
  references/
    entries/
      audience.md
      fidelity.md
    workflows/
      inspect.md
  scripts/
    list_headings.py
  assets/
    icon-large.png
    icon-small.png
    template.md
```

Sources remain authoritative; do not edit the generated folder.

## Include the optional profile

```console
degardis build examples/structured-summary --profile detailed --output .artifacts
```

The rebuilt artifact includes `references/profiles/detailed.md`. Explicit
profile selectors replace manifest defaults. Use `--profile all` to include
every profile.

## Build a ZIP

```console
degardis build examples/structured-summary --zip --output .artifacts
```

This replaces the uncompressed `structured-summary/` folder with
`.artifacts/structured-summary.zip`. Use ZIP output for ChatGPT upload and an
uncompressed folder for filesystem-based agents.

## Install an uncompressed bundle

Choose an agent location from [Artifact format](artifact-format.md#install-an-uncompressed-bundle).
Building directly into a skill directory replaces any existing
`structured-summary/` folder or `structured-summary.zip` in that directory.
Inspect third-party skill instructions and scripts before installing them.

For example, install the skill for Codex in the current repository:

```console
degardis build examples/structured-summary --output .agents/skills
```

The command creates `.agents/skills/structured-summary/SKILL.md`. Start a new
agent session if the installed skill does not appear immediately.

To make it available across local projects in Codex and other hosts that read
the personal `.agents/skills` directory:

```console
degardis build examples/structured-summary --output ~/.agents/skills
```

## Troubleshooting

- **`degardis` is not recognized or not found:** run
  `python -m degardis --help`. If that works, use
  `python -m degardis` in place of `degardis`, or add your Python scripts
  directory to `PATH`.

- **`No skills found inside`:** the supplied directory is neither a skill nor
  contains skill descendants. Pass the directory containing `skill.yaml`, or
  an ancestor directory that contains one or more skills.

- **`Profile selector matched no selected skill`:** the selected skill does
  not define that profile. Run `degardis list` with the same path and use one
  of the reported profile names.

- **`Output directory ... must not overlap skill source`:** use a separate
  output such as `.artifacts`, `dist`, or an agent skill directory outside the
  source. This check protects authored files from artifact replacement.

- **`[FAIL]` or `[ERROR]`:** `[FAIL]` identifies an invalid skill. `[ERROR]`
  means the command itself could not complete, for example because a path or
  profile selector was invalid. Correct the reported issue and validate again
  before building.

## Next steps

- Read [Concepts](concepts.md) for the source and artifact models.
- Follow [Authoring skills](authoring-guide.md) to make a new skill.
- Use [Reference](reference.md) for exact fields and command behavior.
