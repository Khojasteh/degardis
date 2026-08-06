# Getting started

This tutorial validates, builds, and installs the `structured-summary` example.
You need Python 3.10 or newer, a local copy of this repository, and a terminal
open at the repository root.

## Install Degardis

```console
python -m pip install degardis
degardis --help
```

This installs Degardis from PyPI. If you are working on Degardis itself,
install the current checkout instead:

```console
python -m pip install -e .
```

If your shell cannot find `degardis` after installation, use
`python -m degardis` in place of `degardis` in the commands below.

## Validate the source

```console
degardis validate examples/structured-summary
```

Expected result:

```text
Validation

[PASS] Structured Summary (structured-summary)

Summary: 1 passed, 0 failed, 0 errors, 0 warnings, 1 total.
```

Validation reads the source without writing an artifact. The manifest at
[`examples/structured-summary/skill.yaml`](../examples/structured-summary/skill.yaml)
declares source format 1 and skill version 1.0.0.

## See skill details

```console
degardis list examples/structured-summary
```

The output shows the skill title, description, optional `detailed` profile,
whether it includes scripts, legal metadata, and the absolute source path.

`degardis agent` reports the same skill in much more detail. It is designed
for AI agents, not people, so its output is compact and its format may change.
See [the reference](reference.md#degardis-agent-path-path-) before relying on it.

## Build the bundle

```console
degardis build examples/structured-summary --output .artifacts
```

Expected result, with a machine-specific artifact path:

```text
Build

[BUILT] Structured Summary (structured-summary)
  Artifact    <repository-path>/.artifacts/structured-summary

Summary: 1 skill built as folder, 0 warnings.
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

The source files remain authoritative. Do not edit the generated folder.

## Include the optional profile

```console
degardis build examples/structured-summary --profile detailed --output .artifacts
```

The rebuilt artifact now includes `references/profiles/detailed.md`. Explicit
profile selectors replace manifest defaults. Use `--profile all` to include
every profile a skill defines.

## Build a ZIP

```console
degardis build examples/structured-summary --zip --output .artifacts
```

This replaces the uncompressed folder with `.artifacts/structured-summary.zip`.
Use a ZIP for ChatGPT upload and a folder for filesystem-based agents.

## Install an uncompressed bundle

Choose an agent location from [Artifact format](artifact-format.md#install-an-uncompressed-bundle).

Building directly into a skill directory replaces any existing
`structured-summary/` folder or `structured-summary.zip` in that directory.
Review third-party skill instructions and scripts before installing them.

For example, install the skill for Codex in the current repository:

```console
degardis build examples/structured-summary --output .agents/skills
```

The command creates `.agents/skills/structured-summary/SKILL.md`. Start a new
agent session if the skill does not appear immediately.

To make the skill available across local projects in Codex and other agents
that read the personal `.agents/skills` directory:

```console
degardis build examples/structured-summary --output ~/.agents/skills
```

## Troubleshooting

- **`degardis` is not recognized or not found:** run
  `python -m degardis --help`. If that works, use `python -m degardis` in
  place of `degardis`, or add your Python scripts directory to `PATH`.

- **`No skills found inside`:** the directory you supplied is neither a skill
  nor contains skills below it. Pass the directory that contains `skill.yaml`,
  or an ancestor directory that contains one or more skills.

- **`Profile selector matched no selected skill`:** the selected skill does not
  define that profile. Run `degardis list` with the same path and use one of
  the profile names it reports.

- **`Output directory ... must not overlap skill source`:** use a separate
  output directory such as `.artifacts`, `dist`, or an agent skill directory
  outside the source. This check protects your authored files from being
  overwritten.

- **`[FAIL]` or `[ERROR]`:** `[FAIL]` means a skill is invalid. `[ERROR]`
  means the command could not complete, for example because a path or profile
  selector was invalid. Fix the reported issue and validate again before
  building.

## Next steps

- Read [Concepts](concepts.md) to learn the source and artifact models.
- Follow [Authoring skills](authoring-guide.md) to create a new skill.
- Use [Reference](reference.md) for exact fields and command behavior.
