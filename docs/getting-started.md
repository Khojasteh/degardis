# Getting started

Install Degardis, build the worked example, then start a skill of your own. The
[Manual](manual.md) is the reference for every construct, field, and rule —
`degardis manual TOPIC` prints the same topics at a terminal. This page is the
first run.

You need Python 3.10 or newer.

## Install

```console
python -m pip install degardis
degardis --help
```

If your shell cannot find `degardis`, use `python -m degardis` in the commands
below. To work on a checkout of the repository itself, install it with
`python -m pip install -e .`.

## Build the example

From a clone of the repository:

```console
degardis validate examples/structured-summary
degardis build examples/structured-summary --output .artifacts
```

`validate` reads the source, reports every structural problem it finds in one
run, and writes nothing. `build` writes `.artifacts/structured-summary/`; add
`--zip` for an archive a host can accept as an upload.

Open the result. `SKILL.md` routes a request to a task, and the page under
`tasks/` carries that work's whole knowledge closure. Principles and guides stay
as separately loaded pages when the root or task links to them. Treat the folder
as output: change the source and build again rather than editing inside it.
[Bundles](artifact-format.md) describes what a bundle contains and what a rebuild
replaces.

If a report names a check code you do not recognize, ask for it:

```console
degardis explain manifest.unknown-principle
```

## Start your own

```console
degardis init my-skill
degardis validate my-skill
```

`init` writes a manifest and one task that already validates and builds.

Before filling it in, list your **tasks** — the recognizable classes of work
someone asks for. "Summarize supplied material", "review a draft", "investigate a
complaint" are tasks. "French", "our house style", "the customer archive" are
not; those are things the tasks work on. Getting this right early is what makes
the rest fall out: knowledge goes to the tasks that need it, principles belong to
the skill or task that needs them, and profiles carry what depends on the situation
rather than on the work.

Then write the files. Each construct is one Markdown file whose directory says
what it is, whose stem is its id, whose frontmatter holds its fields, and whose
body is its content. Open `my-skill/tasks/primary.md` to see the shape.

One order matters while you are starting: a skill or task `principles` reference
resolves to `principles/<id>.md` in your own skill and nowhere else, so write the
principle file before a level names it.

## Ask the compiler what it decided

```console
degardis inspect my-skill --only composition,principles
```

`composition` answers the question you will actually have — why does this page
carry this material? — by naming what the task asked for, what that knowledge
required. `principles` names each principle's file, its owners, and its own activation condition.

A pass from `validate` means the source compiles to a complete bundle whose
links resolve. It does not mean the skill guides an agent well. Read the
generated task pages as an agent would, and use the skill against real requests,
before you share it.

## Next

- [Manual](manual.md) — what each part of a source is for, and every field.
- [CLI reference](cli.md) — commands, options, and exit status.
- [Bundles](artifact-format.md) — what `build` produces.
