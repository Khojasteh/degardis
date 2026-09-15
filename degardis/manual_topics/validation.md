## Working with the compiler

### Checking a source

```console
degardis validate my-skill
```

Validation writes no files.

Every check runs over the whole source in one pass, and every finding is
reported: the checks never stop at the first problem. Exit status is 0 when no
skill reports an error and 1 otherwise. `--fail-on-warning` reports every warning
as an error.

What is checked:

- the manifest, its content selection, and its interface
- each construct's frontmatter, against that kind's schema
- every skill and task principle reference, against the files this skill ships
- every knowledge reference, and every requirement chain
- knowledge no task reaches, and tasks that carry nothing
- each declared guide, both directions
- profile titles and ids
- the generated pages: their size, their collisions, and every link they emit

What is not checked is whether the skill is any good. A pass means the source
compiles to a complete bundle whose links resolve; whether a task page carries
the knowledge that task needs is established by using the skill, not by
compiling it.

### Reading a code

Every finding carries a check code, and `degardis explain CODE` gives what
triggers it, why it matters, and how to resolve it where a resolution exists. An
unrecognized code lists every code this version can report.

A code is `<namespace>.<check>`, hyphenated — except where the check names a
field of the source, which it spells exactly as the key does:
The field part keeps the manifest key's spelling. So a code can be built from
the key rather than looked up.

Three codes cover the three ways a field goes wrong:

| Code | Means |
| --- | --- |
| `<kind>.missing-<key>` | a required field is not there |
| `<kind>.invalid-<key>` | the field is there and cannot be read |
| `<kind>.unknown-field` | the schema does not define that field |
