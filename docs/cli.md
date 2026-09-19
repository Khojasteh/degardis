# CLI reference

Run commands as `degardis COMMAND`, or `python -m degardis COMMAND` when the
executable is not on your `PATH`. `degardis COMMAND --help` gives the options and
examples of the version you have installed, `-h` works on either side of the
command name, and `degardis --version` prints that version.

| Command | What it does | Writes files? |
| --- | --- | --- |
| `init NAME` | Writes a new source tree that already compiles. | Yes |
| `list PATH ...` | Summarizes the selected skills. | No |
| `validate PATH ...` | Checks a source and reports every finding. | No |
| `build PATH ... --output DIR` | Validates, then writes installable bundles. | Yes |
| `inspect PATH ...` | Reports what a source compiles to, for an AI agent. | No |
| `explain CODE ...` | Explains a diagnostic reported by another command. | No |
| `manual [TOPIC ...]` | Prints the authoring manual by topic. | No |

`validate`, `inspect`, and `build` run the same checks over the same compilation
and set the same exit status, so you do not need to run `validate` before the
other two: a build writes nothing unless every selected skill passes. Run
`validate` when the report on its own is what you want. `list` compiles a source
too, but it reports no finding and always exits 0.

## Choosing a source path

`list`, `validate`, `build`, and `inspect` accept one or more paths. A path can
name a skill directory, or a directory containing several: Degardis finds each
descendant directory holding a `skill.yaml`.

Paths may use `~` and environment variables, and a relative path resolves from
the directory you run the command in.

Give a source directory, not a built folder or ZIP. No command reads a generated
bundle as input.

## `init`

```console
degardis init my-skill
degardis init my-skill --output ./skills
```

Writes a manifest, one task that validates and builds as it stands, and the
directories the rest of the format uses. It refuses to write over an existing
directory, and refuses a NAME that is not lowercase letters, digits, and single
hyphens. `--output` chooses where the new directory is created; the default is
the current directory.

## `list`

```console
degardis list ./skills
```

Reports each selected skill's name, version, and description, the tasks a
request can be routed to, the sources its manifest selects, its available
facets, whether it ships scripts, its licence and copyright, and where its
source is. Use it to confirm what a path selects before building it.

## `validate`

```console
degardis validate my-skill
degardis validate ./skills --fail-on-warning
```

Runs every structural check over each selected skill and reports all findings in
one run. Exit status is 0 when no skill reports an error and 1 otherwise, which
makes it a CI gate; `--fail-on-warning` reports every warning as an error.

For what is checked and what a pass does not mean, see the `validation` topic of
the [Manual](manual.md).

## `build`

```console
degardis build my-skill --output .artifacts
degardis build ./skills --output dist --zip
```

`--output` is required and is created if it does not exist. `--zip` writes each
bundle as a ZIP archive instead of a folder. `--fail-on-warning` applies the same
strict policy as `validate`, so a source that only warns is not built.

Every selected skill is validated before anything is written, and a skill that
does not pass is not written at all.

> [!WARNING]
> A rebuild replaces the folder and ZIP with the same skill name in the output
> directory. Build into a throwaway directory while you are authoring, and never
> point `--output` at a source tree — an output directory that overlaps one is
> refused.

See [Bundles](artifact-format.md) for what is written.

## `inspect`

`inspect` is for an AI agent that needs a compact, line-oriented report about a
skill. It runs exactly the checks `validate` runs, over the same compilation, and
sets the same exit status; `--only` and `--all` choose what is printed, never
what is checked.

```console
degardis inspect my-skill
degardis inspect my-skill --only composition
degardis inspect my-skill --page SKILL.md
```

| Dimension | Reports |
| --- | --- |
| `skill` | name, version, title, root, description length, one count per content key, and each generated page size against its budget |
| `identity` | full description and purpose, license, copyright, source digest |
| `sources` | every selected file, its kind, id, and size |
| `tasks` | each task, its cues, its goal, and the page it compiles to |
| `knowledge` | each unit, its kind, what it requires, and which pages carry it |
| `principles` | each principle, its placements and activation conditions, and its generated page |
| `guides` | each guide, its activation, and the tasks and facets that name it |
| `facets` | each facet, its category, and its description |
| `composition` | direct and required knowledge, then the exact render order within each present kind |
| `quality` | orphans, near-duplicates, constraint ratio, closure duplication, startup bytes, page-budget headroom, and one-load bytes by task |
| `outputs` | every file a build would write, with its size and the permission a ZIP records |
| `diagnostics` | every finding, as data |

`skill`, `tasks`, `principles`, and `diagnostics` are reported by default.
`--only` takes one or more dimensions, repeated or comma-separated, and `--all`
reports every one. `skill` is reported whatever you ask for, and the blocks come
out in the order of the table above rather than the order you asked in.
`--fail-on-warning` applies the same strict policy as `validate`.

`--page` appends the text a build would write to a generated page, without
writing anything: `SKILL.md` for the root, or a generated page such as
`references/tasks/ID.md`, `references/principles/ID.md`,
`references/guides/ID.md`, or `references/facets/index.md`. Copied scripts and
assets, and `agents/openai.yaml`, are not generated Markdown and cannot be read
this way.

Repeat or comma-separate the option to read several pages in one run. Each page
is printed once per selected skill, with its lines indented two spaces; a path no
selected skill generates is reported with the pages that do exist, and exits
non-zero.

For the line format of each row, see [Manual](manual.md#reading-a-row).

## `explain`

```console
degardis explain manifest.unknown-principle knowledge.orphan
```

Takes one or more check codes reported by `validate`, `build`, or `inspect`, and
needs no source path. For each code it gives what triggers the check, why it
matters, and how to resolve it when a resolution is available.

An unrecognized code exits non-zero and lists every code the installed version
can report.

## `manual`

```console
degardis manual
degardis manual tasks principles
```

Prints the authoring [Manual](manual.md) shipped with the installed version.
With no topic it lists every topic with a one-line summary; with topics it prints
each one once, in the order you asked for them.

An unknown name exits non-zero, after every known topic has printed, with all
unknown names reported together.

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | The command completed without an error. |
| `1` | The source, selected path, output operation, or warning policy prevented completion. |
| `2` | The command syntax was invalid; the command prints usage information. |

For `validate`, `build`, and `inspect`, a warning does not fail the command
unless you pass `--fail-on-warning`.
