### `decide`

Use `decide` when the agent must choose between approaches that are all valid.
The step states the choice to be made, and each named choice states the command
that follows from taking it.

| Field | Required | Meaning |
| --- | --- | --- |
| `decide` | Yes | Complete instruction naming the choice to make. |
| `choices` | Yes | Two or more named choices, each with `command` and `next`. |
| `uses` | No | Values the agent reads to choose. |
| `heuristics` | No | Advice identifiers that help make this choice. |

```yaml
choose-depth:
  decide: Choose the amount of detail the reader needs.
  heuristics: [smallest-sufficient-detail]
  choices:
    brief:
      command: Write only detail that changes the reader's decision.
      next: write-summary
    detailed:
      command: Include the supporting detail the reader needs.
      next: write-summary
```

Later work reads the choice as `decision.<step-id>`, whose type is an enum of
the choice names, so `decision.choose-depth == "brief"` is how a condition tests
it.

Two or more choices are required: a decision with one choice is not a decision.
Name a heuristic here when advice would improve the choice, and remember that
the advice can never settle a requirement; [Verifications](#verifications) gives
what can.
