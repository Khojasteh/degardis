### Building a bundle

```console
degardis build my-skill --output .artifacts
```

Builds write folders by default; `--zip` writes ZIP archives. `build` runs the same checks as `validate`, and source-validation errors prevent any output. `--fail-on-warning` applies the stricter warning policy before writing.

Each skill artifact is replaced atomically. A failed write leaves that skill's previous artifact unchanged; siblings already completed in the same run remain. A rebuild replaces the folder and ZIP with the same skill name.

The same source and compiler version produce byte-identical output across hosts.

### Page budgets

Root, task, principle, guide, and facet pages have warning-level size budgets, reported by `inspect --only skill`. The root is startup cost, a task page is one task load, and each separately opened page is an additional load.

Degardis does not truncate oversized pages, but a host may. A budget finding names the page's largest contributors.
