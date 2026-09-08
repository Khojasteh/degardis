### Protocols

A protocol tracks a lifecycle across steps. Use it when something is opened in
one place, must be retained or updated while the work continues, and must be
closed correctly later—an acquired resource, an unresolved question, an
authorization that has to be obtained before something is spent.

| Field | Required | Meaning |
| --- | --- | --- |
| `purpose` | Yes | What the protocol tracks. |
| `rationale` | No | Why the tracked lifecycle matters. |
| `states` | Yes | All allowed state identifiers. |
| `initial` | Yes | State at the start. |
| `accepting` | Yes | States in which the protocol may finish. |
| `hooks` | Yes | Non-empty mapping of checks or actions that use or change state. |
| `title` | No | Reader-facing title. |
| `data` | No | Typed state values. |

```yaml
purpose: Keep the inspected evidence available until the result has used it.
rationale: A later review cannot recover evidence that the run discarded.
states: [empty, held, spent]
initial: empty
accepting: [empty, spent]
data:
  evidence:
    type: {optional: {record: material-inspection}}
  reviewed:
    type: {list: string}
    default: []
hooks:
  hold-evidence:
    phase: after
    from: [empty]
    to: held
    match:
      subjects: [material.inspect]
    command: Keep the inspected subjects, claims, and gaps available for
      whatever uses them next.
    set:
      evidence: {from: result.inspection}
  spend-on-review:
    phase: before
    from: [held]
    to: spent
    match:
      subjects: [summary.review]
    command: Check the draft against the evidence you kept.
    clear: [evidence]
```

Each `data` item declares `type` or `record` and an optional `description`, and
may declare a `default`—the same field, meaning the same thing, as on a value an
action produces. The protocol's own `initial` names the lifecycle state the
frame opens in, and nothing else.

A `default` is a literal of the declared type, so the frame holds it the moment
it opens. An optional field takes none, because it is already absent then; a
record takes none, because a record has no literal form. A field with no default
that is not optional may be declared only when every path assigns it before a
hook reads it. A frame establishes its opening state and data before any enter
hook runs. A hook reads state data as `state.<name>`.

Each hook accepts these fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `phase` | Yes | `enter`, `before`, `after`, or `exit`. |
| `from` | Yes | States from which the hook may run. |
| `command` or `verify` | Yes | An instruction, a verification, or both. |
| `match` | For `before` and `after` | Selector for affected work. |
| `to` | No | State after the hook. |
| `when` | No | DExpr condition. |
| `set` | No | State-data bindings to write. |
| `clear` | No | State-data names to clear. |

Where a protocol is bound decides the lifetime of its frame: the manifest for
the full run, a workflow for each invocation of it, a step for each time that
step is reached.

Every state named by `from`, `to`, `initial`, or `accepting` must be declared,
and every declared state must be reachable. `set` and `clear` name declared data
fields, and only an optional field can be cleared—clearing one that must always
hold a value is reported. One hook cannot both set and clear the same field.
Data that no hook reads, sets, or clears is reported as unused.

The lifecycle must be able to complete. A hook whose `from` states cannot hold
where it was placed, and a frame that could close with no accepting state
reachable, are each reported: the protocol would otherwise track something the
run has no way to finish.
