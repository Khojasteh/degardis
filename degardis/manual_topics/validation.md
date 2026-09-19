## Working with the compiler

### Checking a source

```console
degardis validate my-skill
```

Validation writes no files.

Validation collects all findings. Exit status is 0 without errors and 1 with
errors, and `--fail-on-warning` promotes every warning to an error.

`inspect` and `build` run these same checks over the same compilation and set
the same exit status, so a `validate` run before either adds nothing. Reach for
`validate` when the report itself is what you want, as a CI gate does. `list`
compiles a source too, but it reports no finding and always exits 0.

What is checked:

- the manifest, its content selection, its interface, and the icon it names
- each construct's frontmatter, against that kind's schema
- every skill and task principle reference, against the files this skill ships,
  and every selected principle no level names
- every knowledge reference, and every requirement chain
- knowledge no task reaches, and tasks that carry nothing
- guide references, and every selected guide, script, or asset nothing reaches
- facet titles and ids
- the generated pages: their size, their collisions, and every link they emit

A pass establishes a complete bundle whose links resolve, not that the skill is
useful or that each task has the right knowledge.

### Reading a code

Every finding has a check code. `degardis explain CODE` gives its trigger,
reason, and resolution where one exists, and an unknown code lists known codes.

A code is `<namespace>.<hyphenated-check>`. A check naming a source key preserves
that key's spelling, as in `interface.short_description-length`.

Three codes cover the three ways a field goes wrong:

| Code | Means |
| --- | --- |
| `<kind>.missing-<key>` | a required field is not there |
| `<kind>.invalid-<key>` | the field is there and cannot be read |
| `<kind>.unknown-field` | the schema does not define that field |
