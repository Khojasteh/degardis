## Workflows

A workflow is the part that tells an agent how to complete the job. It names the
information the job starts with, the steps the agent follows, and the possible
ways it can finish. Every reachable path ends with one declared outcome.

| Field | Required | Meaning |
| --- | --- | --- |
| `description` | Yes | What the workflow does. |
| `entry` | Yes | Identifier of the first step. |
| `outcomes` | Yes | Mapping of outcomes this workflow may return. |
| `steps` | Yes | Mapping of step identifiers to one step each. |
| `title` | No | Reader-facing workflow title. |
| `inputs` | No | Values a caller must supply. |
| `policies` | No | Policies active for this workflow. |
| `rules` | No | Rules considered in this workflow. |
| `protocols` | No | Protocols active for each invocation. |
| `guidance` | No | Guidance used in this workflow. |

An outcome is either empty (`{}`) or names the record returned with that outcome:

```yaml
outcomes:
  delivered:
    record: summary-result
  no-summary: {}
```

`blocked` belongs to the compiler, not to you. Every workflow can return it when
a binding check cannot be satisfied, and it names what failed and what was
available. Declaring it, returning it, or mapping it in a source is reported.

A workflow runs forward. Its steps may not form a cycle, so there is no loop
construct and no way back to a step already taken: where a job repeats a stage,
write that stage as a step of its own. Calls are acyclic for the same reason—a
workflow cannot reach itself through any chain of `use` steps.

The steps form a graph, and the compiler checks that the graph is whole:

- `entry`, every `next`, every branch target, and every called workflow must
  name something that exists, and every step other than a `return` must have a
  successor.
- Every step must be reachable from `entry`, and every declared outcome must be
  returned by some reachable path.
- Every workflow other than the primary one must be reached by a chain of `use`
  steps from the primary workflow. Unreached selected workflows are still
  checked.
- Two steps may not declare one value name with different types.
- A result may not be defined again on a path before its earlier definition is
  read.
- One step may not be left both required and prohibited from doing the same
  thing at the same phase.

The result is that a validated workflow has no dead step, no path that stops
without an outcome, and no outcome a caller cannot receive.
