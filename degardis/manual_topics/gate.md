### `gate`

Use `gate` when the agent must establish and record which stated condition is
true. A gate is not a choice between approaches: the states are findings, and
which one holds is a matter of fact about the work in front of the agent.

| Field | Required | Meaning |
| --- | --- | --- |
| `gate` | Yes | Complete instruction naming the condition to establish. |
| `states` | Yes | Two or more named states, each with `command` and `next`. |
| `uses` | No | Values the agent reads to judge. |
| `heuristics` | No | Advice identifiers that help make the judgement. |

```yaml
check-readiness:
  gate: Judge whether the material supports a faithful summary.
  states:
    ready:
      command: Continue with the material as supplied.
      next: write-summary
    incomplete:
      command: Report what the material does not support.
      next: report-gaps
```

Later work reads the finding as `gate.<step-id>`, whose type is an enum of the
state names. That is what makes a gate the one step form a requirement can
verify against: `verify: {gate: check-readiness}` reads this value, so the gate
must lie on every path to whatever it constrains.

A `decide` and a `gate` are written the same way and mean different things.
Reach for `decide` when two answers would both be correct and the agent picks
one; reach for `gate` when one answer is correct and the agent has to find out
which.
