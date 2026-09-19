### Building a bundle

```console
degardis build my-skill --output .artifacts
```

Each skill builds as a folder by default; `--zip` writes a ZIP instead.

`build` runs every check `validate` runs, over the same compilation, and writes
nothing unless every selected skill passes. `--fail-on-warning` holds them to the
stricter standard, so a source that only warns is not built.

Builds are atomic per skill: a failure leaves that skill's existing artifact
unchanged, while completed siblings remain.

A rebuild replaces that skill's folder and ZIP, so use a throwaway output rather
than a live agent directory.

The same source and compiler version produce byte-identical output on every
host.

### Page budgets

Root, task, principle, guide, and facet pages each have warning-level budgets.
`SKILL.md` is charged to every run; a task page is one complete task load; each
principle, guide, or facet is an additional load the reader opens when it
applies.

Nothing is dropped from an oversized page to make it fit. A host may truncate it
instead, and a reader may never reach the end of it.

A finding names the largest contributors; remove unneeded material, shorten it,
split work with separate purposes, or move conditional detail to a guide. Split a
principle or guide only where its parts have distinct conditions.
