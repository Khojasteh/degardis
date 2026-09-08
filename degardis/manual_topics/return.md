### `return`

Use a return to finish the workflow. Its `return` mapping has a required
`outcome` and an optional `with` mapping supplying the fields of that outcome's
record.

```yaml
deliver:
  return:
    outcome: delivered
    with:
      summary: {from: result.reviewed}
```

The outcome named must be one this workflow declares, and `with` must supply
every field that outcome's record declares, each with a compatible type. An
outcome that is declared and never returned is reported, as is one returned but
not declared.

A return is the only step form with no successor, and every reachable path must
end at one. Give a workflow a return for each way the job can genuinely finish—
the outcome a caller receives is how it knows which one happened.
