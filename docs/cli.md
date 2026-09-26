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
| `manual [TOPIC ...]` | Print the authoring manual by topic. | No |

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

Creates a manifest, one task, and the standard source directories. It refuses an existing destination and names other than lowercase letters, digits, and single hyphens. The current directory is the default output.

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

Runs all structural checks and reports all findings. Exit status is 0 without errors and 1 with errors. A pass means the source can produce a complete bundle with valid generated references; it does not assess instruction quality.

See [Validation](manual.md#checking-a-source) for the checks and repair workflow.

## `build`

```console
degardis build my-skill --output .artifacts
degardis build ./skills --output dist --zip
```

`--output` is required and created when necessary. `--zip` writes one ZIP per skill instead of a folder. All selected sources are checked before output starts; a validation failure writes nothing. Each skill artifact is then replaced atomically, so an output failure cannot damage its previous artifact, although a sibling already completed in the same run remains written.

The output directory may not overlap a source directory. A rebuild replaces the folder and ZIP with the same skill name, so use a staging directory while authoring.

See [Bundles](artifact-format.md) for the generated layout.

## `inspect`

`inspect` is a compact, line-oriented interface for AI agents. It runs the same checks as `validate`; report selection does not change validation.

```console
degardis inspect my-skill
degardis inspect my-skill --only composition
degardis inspect my-skill --page SKILL.md
```

| Dimension | Reports |
| --- | --- |
| `skill` | identity, selected-content counts, and page sizes against budgets |
| `identity` | description, purpose, rights metadata, source fingerprint |
| `sources` | selected files, kinds, ids, sizes |
| `tasks` | task routing cues, goals, generated pages, pages that link them |
| `knowledge` | units, dependencies, task-page placement |
| `principles` | owners, conditions, pages that link them, generated pages |
| `guides` | conditions, owners, pages that link them |
| `facets` | categories, descriptions, pages that link them |
| `scripts` | selected scripts, sizes, pages that link them |
| `assets` | selected assets, sizes, pages that link them |
| `composition` | direct/required knowledge and render order |
| `quality` | structural quality signals and minimum and maximum read sizes by task |
| `outputs` | files a build would write, sizes, ZIP modes, and total bytes |
| `diagnostics` | errors and warnings as data |

By default, `skill`, `tasks`, `principles`, and `diagnostics` are printed. `--only` accepts repeated or comma-separated dimensions; `--all` prints every dimension. `skill` is always included.

`--page` appends generated Markdown without building. Use `SKILL.md` or a page path reported by `inspect`; repeat or comma-separate the option for multiple pages. Copied files and host metadata are not generated Markdown and cannot be read with `--page`.

See [Inspection](manual.md#seeing-what-the-compiler-decided) for row shapes and interpretation.

## `explain`

```console
degardis explain manifest.unknown-principle knowledge.orphan
```

Explains each check code's trigger, reason, and resolution when available. It needs no source path. Unknown codes fail the command and list the codes the installed version knows.

## `manual`

```console
degardis manual
degardis manual tasks principles
```

With no topic, lists available manual topics. With topic names, prints each requested topic once, in request order. Unknown names fail the command after any known requested topics have printed.

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | Command completed successfully. |
| `1` | Source, path, output, or warning policy prevented completion. |
| `2` | Command syntax was invalid. |

For `validate`, `build`, and `inspect`, warnings fail only with `--fail-on-warning`.
