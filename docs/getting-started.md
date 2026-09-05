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
A pass means these sources compile to a complete execution graph, not that the skill guides an agent well.
```

Validation reads the source without writing an artifact. The manifest at
[`examples/structured-summary/skill.yaml`](../examples/structured-summary/skill.yaml)
declares source format 2 — the format this compiler reads — and skill version
1.0.0.

The closing line is the boundary of what a pass establishes. Degardis checks the
declarations and relations it can observe: the workflow graph terminates, every
outcome is handled, every value is assigned before it is read, and every policy,
rule, and protocol hook the source binds reached a step in the generated
document. It never judges what the instructions say.

## See skill details

```console
degardis list examples/structured-summary
```

The output is a readable summary of what the skill declares: its title,
description, primary workflow, what it ships, and its legal metadata.

To see what the source compiles to rather than what it declares, use `inspect`:

```console
degardis inspect examples/structured-summary --only lowering
```

Each row names one binding construct and the generated node it was lowered
into — the step where that requirement is actually enforced. `inspect` is
designed for AI agents, so its output is compact rather than readable; see
[the reference](reference.md#degardis-inspect-path-path-) for what each row
means.

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

The generated folder holds `SKILL.md` beside `execution/`, `profiles/`,
`references/`, `scripts/`, `assets/`, and `agents/openai.yaml`. See
[Artifact format](artifact-format.md) for what each holds.

The source files remain authoritative. Do not edit the generated folder.

## Read what the compiler produced

Open `.artifacts/structured-summary/SKILL.md`. It is a compact control plane, not
a dump of every workflow: its `Start` section names the module to read and the
node to begin at. Open that module to see the workflow nodes.

The rule `structure-subjects` appears there as a generated check ahead of the
writing operation. Use `degardis inspect ... --only lowering` to see where each
generated check came from.

## The two profiles

The example also ships Concise and Detailed auxiliary profiles, listed in
`profiles/index.md` so an agent can open whichever ones its task matches. Nothing
selects them: missing a match, or deleting the entire `profiles/` directory,
changes no required behavior.

## Build a ZIP

```console
degardis build examples/structured-summary --zip --output .artifacts
```

This replaces the uncompressed folder with `.artifacts/structured-summary.zip`.
Use a ZIP for ChatGPT upload through the current
[Skills in ChatGPT](https://chatgpt.com/skills) workflow, and a folder for
filesystem-based agents.

## Install an uncompressed bundle

Choose an agent location from [Artifact format](artifact-format.md#install-an-uncompressed-bundle).

> [!WARNING]
> Building directly into a skill directory replaces any existing
> `structured-summary/` folder or `structured-summary.zip` in that directory.
> Review third-party skill instructions and scripts before installing them.

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

- **`Output directory ... must not overlap skill source`:** use a separate
  output directory such as `.artifacts`, `dist`, or an agent skill directory
  outside the source. This check protects your authored files from being
  overwritten.

- **`format_version 1 ...` (`manifest.obsolete-format_version`):** the source
  was written for Degardis 1.x, and no command converts one format to another.
  Rewrite the source against the current schemas — the
  [authoring guide](authoring-guide.md) covers each construct — or stay on the
  Degardis 1.x release that reads it.

- **`[FAIL]` or `[ERROR]`:** `[FAIL]` means a skill did not compile. `[ERROR]`
  means the command could not complete, for example because a path was invalid.
  Fix the reported issue and validate again before building.

- **A message you do not understand:** every validation message ends with the
  check that reported it, in parentheses, such as `(rule.unmatched)`. Pass that
  code to `degardis explain` for what triggers the check, why it matters, and a
  failing and passing example:

  ```console
  degardis explain rule.unmatched
  ```

  Pass several codes at once to work through a whole report.

## Next steps

- Read [Concepts](concepts.md) to learn the source and artifact models.
- Follow [Authoring skills](authoring-guide.md) to create a new skill.
- Use [Reference](reference.md) for exact fields and command behavior.
