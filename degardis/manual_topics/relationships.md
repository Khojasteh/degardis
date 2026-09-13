### How knowledge reaches a page

Two declarations put knowledge on a task page, and there are no others.

A task names what it needs:

```yaml
knowledge:
- source-material
- order-findings
```

A unit names additional knowledge its task closure needs:

```yaml
requires:
- audience
```

The task page carries both sets, following `requires` transitively.

Direct knowledge keeps task order. Required units follow in first-introduced
order. Grouping by kind happens afterward.

A unit in two tasks' closures is compiled into both pages, and
`degardis inspect --only quality` reports how many bytes that cost.

Prose creates no dependency. A `requires` chain must not cycle. A unit no task
reaches is reported as a warning, and the bundle carries none of it.
