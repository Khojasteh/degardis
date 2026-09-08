### `use`

Use `use` when a part of the job is substantial enough to have its own workflow.
It calls another workflow in the same skill and continues according to the
outcome that comes back.

| Field | Required | Meaning |
| --- | --- | --- |
| `use` | Yes | Workflow identifier. |
| `on` | Yes | Mapping of every callee outcome to the next step. |
| `with` | No | Values supplied to the callee's inputs. |

An outcome can map directly to a next step, or to a mapping with `next` and
`as`. Use `as` to retain the record returned with that outcome; the name you
give reads afterwards as `result.<name>`.

```yaml
report-gaps:
  use: describe-gaps
  with:
    gaps: {from: result.inspection.gaps}
  on:
    reported:
      next: done
      as: gap-report
```

`on` must be complete and exact. Leaving one of the callee's outcomes unmapped
is reported, and so is mapping an outcome the callee does not declare. Do not
map `blocked`: the compiler owns it and handles it for every call. An outcome
that carries record fields must be captured with `as`, so nothing the callee
returns is silently dropped, and capturing an outcome that carries no record is
reported.

Calls may not form a cycle: a workflow cannot reach itself through any chain of
`use` steps.
