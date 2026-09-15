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

The page carries the closure of the two: what the task named, plus everything
that knowledge requires, transitively.

`requires` changes inclusion, not presentation order. Direct knowledge keeps the
order written on the task. Units reached only through `requires` follow, in the
order requirement lists first introduce them. The result is then grouped by kind
in the order **Concepts**, **Facts**, **Constraints**, **Guidance**, preserving
that order within each kind.

A unit in two tasks' closures is compiled into both pages, and
`degardis inspect --only quality` reports how many bytes that cost.

Nothing else creates an edge: mentioning a term another unit defines does not
pull that unit onto the page.

### Two failures

A `requires` chain must not close on itself. Break a cycle by deciding which
unit depends on the other, or by splitting what the two share into a third unit
both require.

Every knowledge unit must reach at least one task; the bundle carries none that
does not.
