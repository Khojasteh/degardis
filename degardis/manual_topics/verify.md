### Verifications

A policy provision, a rule, and a protocol hook may each add one `verify`,
naming how the requirement is proved rather than merely stated. It takes exactly
one of three forms, and exactly one at a time:

```yaml
verify:
  expression: length(result.inspection.subjects) > 1
```

```yaml
verify:
  gate: check-readiness
```

```yaml
verify:
  confirm: Each heading names one subject.
```

| Form | Proved by | Use it when |
| --- | --- | --- |
| `expression` | A DExpr condition over declared values. | The proof is already a value the workflow holds. |
| `gate` | The finding a `gate` step recorded. | The agent had to establish the fact, and did so at a named step. |
| `confirm` | The agent confirming a complete statement. | The proof is a judgement no declared value carries. |

A gate verification names a `gate` step, and reads the value that step recorded.
That value has to exist wherever the requirement is enforced, so the gate must
lie on every path reaching the node the requirement constrains. A gate on only
some of those paths is reported: the verification would otherwise name a finding
that, on the other paths, was never made. That holds at every phase, including
`during`, where the constrained node is the step the selector matched rather
than a check generated in front of it.

Write a `confirm` as a complete statement the agent can hold the work against—
`Each heading names one subject.`, not `Check the headings`. It should state one
testable thing, because the agent's answer to it is the whole of the proof.

Advice can never verify. Naming a heuristic in a `verify`, or writing a
verification as a preference, is reported: a heuristic improves a choice among
options that are already valid, and nothing that may be ignored can establish
that a requirement was met.
