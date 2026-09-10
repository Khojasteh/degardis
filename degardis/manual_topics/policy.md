### Policies

A policy groups related requirements under one boundary. Use one when several
requirements protect the same thing, such as handling sensitive material or
keeping a result faithful to its source.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | Yes | Boundary the policy establishes. |
| `rationale` | No | Why that boundary exists. |
| `provisions` | Yes | Non-empty mapping of named provisions. |
| `title` | No | Reader-facing title. |

Each provision is one requirement within that boundary:

| Field | Required | Meaning |
| --- | --- | --- |
| `phase` | Yes | `before`, `during`, `after`, or `before-return`. |
| `match` | Yes | Selector for affected work. |
| `require` or `prohibit` | Yes | Exactly one complete instruction. |
| `when` | No | DExpr condition; the provision applies only when it holds. |
| `unless` | No | DExpr exception; the provision is set aside when it holds. |
| `verify` | No | Expression, gate, or confirmation. |

```yaml
summary: Keep every claim inside what the supplied material supports.
rationale: Unsupported claims make the result unreliable.
provisions:
  establish-support:
    phase: before
    match:
      subjects: [summary.write]
    require: Establish support for each claim before writing it.
```

A provision applies when its selector matches, its `when` is true if present,
and its `unless` is false if present. Declaring neither `require` nor `prohibit`
is reported, and so is declaring both: a provision states one obligation, and
which of the two it is decides how the agent reads it.

Write a prohibition as the thing not to do—`prohibit: Publish a claim the
material does not support.`—because the compiler renders it as the negative
command it means, keeping your sentence beside it.

Group provisions into a policy when they share a boundary. Where a requirement
stands alone with its own condition, write a rule instead; several unrelated
provisions in one policy make the boundary its `summary` states untrue.

Grouping earns something at the other end too. Where several provisions of one
policy apply at the same point in a workflow, the generated skill states them
together, as one list of obligations the agent satisfies before it goes on. So
the boundary the policy names reads as one thing to meet rather than as a run of
unrelated checks, and an agent reaches the work behind it sooner.
