### Fields shared by steps

A step has exactly one form—`action`, `branch`, `decide`, `gate`, `use`,
`pattern`, or `return`—and the field that names the form is what says which it
is. The fields below may appear on any of them. Add one only when it helps
describe the work at that step:

| Field | Meaning |
| --- | --- |
| `policies` | Additional policies active at this step. |
| `rules` | Additional rules considered at this step. |
| `protocols` | Protocols active while this step is reached. |
| `guidance` | Guidance identifiers, or mappings with `guidance` and optional `detail`. |
| `subjects` | Tags that describe the work. |
| `effects` | Tags that describe the technical effect. |
| `heuristics` | Advice identifiers; allowed only on `decide` and `gate`. |

```yaml
write-summary:
  action: Write the summary the chosen depth calls for.
  subjects: [summary.write]
  effects: [workspace.write]
  rules: [cite-the-source]
  next: review
```

`subjects` and `effects` are how a requirement finds this step; see
[Subjects and effects](#subjects-and-effects). Naming a heuristic on any step
but a `decide` or a `gate` is reported, because advice belongs where a choice is
made.

A step is the narrowest of the three scopes a requirement can be bound at, and
the one to use where the requirement holds only here;
[Choosing a requirement](#choosing-a-requirement) gives the rest.

For `guidance`, omit `detail` or use `detail: synopsis` for its short form. Use
`detail: inline` when the additional guidance points should appear at that step;
that form needs a guidance file that declares `points`.
