### Patterns

A pattern is a reusable procedure, selected explicitly by a `pattern` step and
performed in full wherever it is applied.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | Yes | What the procedure accomplishes. |
| `procedure` | Yes | Non-empty ordered mapping of procedure items. |
| `title` | No | Reader-facing title. |
| `inputs` | No | Typed values supplied through `with`. |
| `references` | No | Supporting Markdown. |

```yaml
summary: Check that every claim carries the attribution it needs.
inputs:
  claims:
    type: {list: string}
procedure:
  list-claims:
    command: List the claims the draft makes.
    uses: [input.claims]
  attribute:
    command: Name the supporting material behind each claim.
    subjects: [attribution.check]
```

Each procedure item has a required `command` and optional `uses`, `subjects`,
and `effects`. Items run in the order written. A procedure item reads only the
pattern's own inputs, so a pattern is self-contained: what it needs comes in
through `with`, and it cannot reach into the workflow that applied it.

Put `subjects` and `effects` on the items that do the work, not on the step that
applies the pattern. That is what lets a requirement select the work itself
wherever the pattern is used.

Use a workflow instead of a pattern when the reusable work needs branches,
decisions, calls, returns, or values that later workflow steps read. A pattern
is a straight-line procedure; anything that has to choose a route or hand a
result back is a workflow reached by `use`.
