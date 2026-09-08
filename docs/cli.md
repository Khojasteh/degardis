# CLI reference

Run commands as `degardis COMMAND`. If the command is not available on your
`PATH`, use `python -m degardis COMMAND` instead.

Use `degardis COMMAND --help` for the options and examples supported by the
version you have installed. `-h` also works before a command name.

## Choose a source path

`list`, `validate`, `build`, and `inspect` accept one or more paths. A path can
name a skill directory, or a directory containing several skills. Degardis finds
each descendant directory with a `skill.yaml` manifest.

Paths may use `~`, which means your current user's home directory, and environment
variables. Relative paths are resolved from the directory where you run the
command.

Use a source directory, not a built folder or ZIP. Commands that read a source
do not use generated artifacts as input.

## Command overview

| Command | What it does | Writes files? |
| --- | --- | --- |
| `list PATH [PATH ...]` | Summarizes the selected skills. | No |
| `validate PATH [PATH ...]` | Checks a source and reports every finding. | No |
| `build PATH [PATH ...] --output PATH` | Validates and creates installable bundles. | Yes |
| `inspect PATH [PATH ...]` | Produces a compact report for an AI agent. | No |
| `explain CODE [CODE ...]` | Explains diagnostics reported by another command. | No |
| `manual [TOPIC ...]` | Reads the source authoring manual by topic. | No |

## `list`

Use `list` to confirm what a path selects before you build it:

```console
degardis list ./skills
```

The report includes each skill's identity, description, the entrypoints a
request is routed to, selected content, available profiles, and source
location.

## `validate`

Use `validate` before building, sharing, or accepting a change to a skill:

```console
degardis validate my-skill
```

Validation checks the source format, selected files, value flow, workflow paths,
and how requirements apply to the workflow. It reports all findings it can see
in one run. A pass means the source has a complete structure; you still need to
review whether its instructions are appropriate for the intended task.

Use `--fail-on-warning` when warnings should fail a local or CI check:

```console
degardis validate ./skills --fail-on-warning
```

When a report includes a diagnostic you need help with, run `degardis explain`
with that diagnostic. The CLI explains the condition, its impact, and how to
correct it.

## `build`

Use `build` to create one folder per skill:

```console
degardis build my-skill --output .artifacts
```

Use `--zip` when you need ZIP bundles:

```console
degardis build ./skills --output dist --zip
```

The output directory is required. Builds validate all selected skills before
writing. A skill that does not pass validation is not written.

> [!WARNING]
> A rebuild replaces the folder and ZIP with the same skill name in the output
> directory. Build into a throwaway directory while you are authoring, and do
> not point `--output` at the skill source.

Use `--fail-on-warning` to apply the same strict warning policy as `validate`.
Read [Bundles](artifact-format.md) before building into a directory that already
contains installed or distributed skills.

## `inspect`

`inspect` is for an AI agent that needs a compact, line-oriented report about a
skill. It runs the same checks as `validate` and can report the selected skill,
workflows, requirements, optional material, build outputs, and diagnostics.

```console
degardis inspect my-skill
degardis inspect my-skill --only diagnostics
degardis inspect my-skill --all
```

By default, the report includes the skill summary, workflows, reading cost, and
diagnostics. Use `--only` with one or more comma-separated report dimensions to
request only what the agent needs. Use `--all` for every dimension. `--body-text`
also includes the generated root skill text in the report.

`--fail-on-warning` makes warnings fail the command. For the exact report
dimensions and line format, use `degardis inspect --help`; the installed CLI is
the authoritative description of this agent-facing output.

## `explain`

`explain` takes one or more diagnostics reported by `validate`, `build`, or
`inspect`. It does not need a source path and does not create files.

```console
degardis explain CODE [CODE ...]
```

Use it when the short report message does not tell you how to repair the source.
An unrecognized diagnostic causes a nonzero exit status and lists the diagnostics
available in the installed version.

## `manual`

`manual` prints the authoring [Manual](manual.md) shipped with the installed
version. It does not need a source path, reads no source, and creates no files.

```console
degardis manual [TOPIC ...]
```

With no topic, it lists every topic with a one-line summary. With topics, it
prints each requested topic once, in the order you asked for them, restating
each cross-reference as the topic name it points at. An unknown
topic name causes a nonzero exit status; known topics in the same command are
still printed, and every unknown name is reported together.

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | The command completed without an error. |
| `1` | The source, selected path, output operation, or warning policy prevented completion. |
| `2` | The command syntax was invalid; the command prints usage information. |

For `validate`, `build`, and `inspect`, a warning does not fail the command
unless you pass `--fail-on-warning`.
