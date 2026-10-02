# CLI reference

Run commands as `degardis COMMAND`, or `python -m degardis COMMAND` when the executable is not on your `PATH`. `degardis COMMAND --help` shows the options and examples for the installed version; `-h` also works before the command name.

| Command | Purpose | Writes files? |
| --- | --- | --- |
| `init NAME` | Create a source that already compiles. | Yes |
| `list PATH ...` | Summarize selected skills and content. | No |
| `validate PATH ...` | Report every structural finding. | No |
| `build PATH ... --output DIR` | Validate and write installable bundles. | Yes |
| `inspect PATH ...` | Report compilation facts for an AI agent. | No |
| `explain CODE ...` | Explain diagnostic codes. | No |
| `manual [TOPIC ...]` | Print the authoring manual by topic, or all of it with `--all`. | No |

`validate`, `inspect`, and `build` use the same checks and exit status. `--fail-on-warning` makes warnings fail those commands.

Redirected or piped output, including errors, is UTF-8 whatever the platform's code page or locale. A terminal receives text in the encoding it displays.

## Source paths

`list`, `validate`, `build`, and `inspect` accept one or more paths. A path may name a skill directory or a directory containing skills; Degardis discovers descendant directories containing `skill.yaml` and passes over built bundles among them.

`~`, environment variables, and relative paths are supported. Give source directories, not generated folders or ZIP files.

## `init`

```console
degardis init my-skill
degardis init my-skill --output ./skills
```

Creates a manifest, one task, and empty `principles/`, `knowledge/`, `facets/`, and `guides/` directories. It refuses an existing destination and names other than lowercase letters, digits, and single hyphens. The current directory is the default output.

## `list`

```console
degardis list ./skills
```

Shows each selected skill's identity, tasks, selected sources, available facets, script presence, license/copyright, and source location. Use it to confirm what a path selects. Source diagnostics are not reported by `list`.

## `validate`

```console
degardis validate my-skill
degardis validate ./skills --fail-on-warning
```

Runs all structural checks and reports all findings. See [Checking a source](manual.md#checking-a-source) for what the checks cover and what a pass means.

## `build`

```console
degardis build my-skill --output .artifacts
degardis build ./skills --output dist --zip
```

`--output` is required, is created when necessary, and may not overlap a source directory. `--zip` writes one ZIP per skill instead of a folder.

See [Building a bundle](manual.md#building-a-bundle) for when a build writes and how it replaces an existing artifact, and [Bundles](artifact-format.md) for the generated layout.

## `inspect`

`inspect` is a compact, line-oriented interface for AI agents. Selecting what it reports does not change validation.

```console
degardis inspect my-skill
degardis inspect my-skill --only composition
degardis inspect my-skill --page SKILL.md
```

| Dimension | Reports |
| --- | --- |
| `skill` | identity, selected-content counts, and page sizes against budgets |
| `identity` | description, stance, rights metadata, source format, source fingerprint |
| `sources` | selected files, kinds, ids, sizes |
| `tasks` | task routing cues, goals, guides, hand-offs, generated pages |
| `knowledge` | units, dependencies, task-page placement |
| `principles` | placement, conditions, pages that link them, generated pages |
| `guides` | conditions, owners, required guides |
| `facets` | categories and descriptions |
| `scripts` | selected scripts, sizes, pages that name them |
| `assets` | selected assets, sizes, pages that name them |
| `composition` | direct/required knowledge and render order |
| `quality` | structural quality signals and minimum and maximum read sizes by task |
| `outputs` | files a build would write, sizes, permission modes, and total bytes |
| `diagnostics` | errors and warnings as data |

By default, `skill`, `tasks`, `principles`, and `diagnostics` are printed. `--only` accepts repeated or comma-separated dimensions; `--all` prints every dimension. `skill` is always included.

`--page` appends a generated page without building; see [Reading a page without building](manual.md#reading-a-page-without-building). See [Seeing what the compiler decided](manual.md#seeing-what-the-compiler-decided) for row shapes and interpretation.

## `explain`

```console
degardis explain manifest.unknown-principle knowledge.orphan
```

Explains each check code's trigger, impact, and, when one is stated, resolution. It needs no source path. Unknown codes fail the command and list the codes the installed version knows.

## `manual`

```console
degardis manual
degardis manual tasks principles
degardis manual --all
```

With no topic, lists available manual topics. With topic names, prints each requested topic once, in request order. Unknown names fail the command after any known requested topics have printed. `--all` prints every topic once, in manual order, and cannot be combined with topic names.

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | Command completed successfully. |
| `1` | `validate`, `inspect`, or `build` found errors, or warnings under `--fail-on-warning`; or a path, output directory, check code, topic, or page could not be used. |
| `2` | Command syntax was invalid. |
