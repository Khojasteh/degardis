## Working with the compiler

### Checking a source

```console
degardis validate my-skill
```

Validation writes nothing, collects all findings, exits 1 on errors, and exits 0 otherwise. `--fail-on-warning` treats warnings as errors. `inspect` and `build` run the same checks.

Validation checks:

- manifest fields, content selection, interface, and icon;
- construct fields and required bodies;
- task, principle, knowledge, guide, and inline references, inline references in principles, and links written by path;
- knowledge and guide requirement cycles, and unreachable knowledge;
- unused principles, guides, scripts, and assets;
- task routing and facet identity;
- generated page budgets, heading depth, generated links, and path collisions, including paths or directories that differ only in letter case and a file where a directory goes.

A pass means the source can produce a complete bundle whose generated links resolve. It does not judge whether the skill's guidance is useful.

Every finding includes a check code. Run `degardis explain CODE` for its trigger, impact, and, when the check states one, resolution.
