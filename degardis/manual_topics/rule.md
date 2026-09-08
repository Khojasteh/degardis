### Rules

A rule is one conditional requirement or prohibition. Use one when the rule has
its own condition and does not belong with a larger policy boundary.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | Yes | Relationship the rule states. |
| `rationale` | No | Why the rule exists. |
| `phase` | Yes | `before`, `during`, `after`, or `before-return`. |
| `match` | Yes | Selector for affected work. |
| `require` or `prohibit` | Yes | Exactly one complete instruction. |
| `title` | No | Reader-facing title. |
| `when` | No | DExpr condition. |
| `unless` | No | DExpr exception condition. |
| `verify` | No | Expression, gate, or confirmation. |

```yaml
summary: A summary that omits a known gap is reported as incomplete.
rationale: A reader otherwise cannot distinguish a complete review from a partial one.
phase: before-return
match:
  outcomes: [delivered]
when: length(result.inspection.gaps) > 0
require: State each gap the material leaves open before returning the summary.
```

A rule is a policy provision that stands on its own: the binding fields below
`rationale`
are exactly a provision's, and everything that holds for one holds here. What
differs is the unit an author repairs, and the unit a reader reads—a rule is
found and understood by itself, where a provision is read alongside the boundary
its policy establishes.

Reach for a rule when the requirement's condition is the whole of what it says.
Where you find yourself writing a third rule whose `summary` restates the same
boundary, those rules are provisions of one policy.
