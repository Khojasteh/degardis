# Getting started

This guide validates and builds the `structured-summary` example. It is a good
first run if you understand what an AI skill is but have not authored one with
Degardis before.

You need Python 3.10 or newer, a clone of this repository, and a terminal open
at the repository root.

## Install Degardis

```console
python -m pip install degardis
degardis --help
```

If your shell cannot find `degardis`, use `python -m degardis` in the commands
below. To work on this checkout itself, install it with `python -m pip install
-e .` instead.

## Check the example

```console
degardis validate examples/structured-summary
```

Validation reads the YAML source and reports all of the structural problems it
finds. A passing result means the source has a complete, usable skill structure.
It does not judge whether the instructions are suitable for every task, so read
the skill as an agent would before you share it.

If validation reports something you do not understand, pass the diagnostic from
the report to `degardis explain`. The command explains the problem and shows how
to correct it.

## See what the example contains

```console
degardis list examples/structured-summary
```

`list` shows the skill's name, description, main workflow, optional profiles,
and the kinds of files it includes. It does not build anything.

## Build a bundle

```console
degardis build examples/structured-summary --output .artifacts
```

The command creates `.artifacts/structured-summary/`. The folder contains the
root `SKILL.md`, any required workflow pages, optional profiles and references,
and the files selected by the skill source.

Treat the built folder as output. Change the YAML source, validate it again, and
rebuild instead of editing files inside `.artifacts`.

To create a ZIP for a host that accepts uploaded skill archives, add `--zip`:

```console
degardis build examples/structured-summary --output .artifacts --zip
```

For the contents and replacement behavior of a bundle, see [Bundles](artifact-format.md).
Install the folder or archive using your agent host's current skill-installation
instructions.

## Next steps

- Follow the [Authoring guide](authoring-guide.md) to create a skill of your own.
- Use the [Manual](manual.md) to understand skill parts or look up a field.
  `degardis manual` reads the same topics at the terminal.
- Use the [CLI reference](cli.md) when you need a command option.
