### Phases

A phase says where a requirement stands relative to the work its selector
matched. Policies and rules use four:

| Phase | Use it when |
| --- | --- |
| `before` | Work must happen before the selected step. |
| `during` | A requirement shapes the selected work itself. |
| `after` | Work must happen after the selected step. |
| `before-return` | Work must happen before a workflow returns. |

`before-return` is separate from `before` because a return has no action to
precede: what it precedes is leaving the workflow.

A `during` requirement renders beside a command, so only the step forms that
state one can carry it: an action, a call, a pattern application, and a return.
A decision, a gate, and a branch state a choice rather than a command, so a
`during` requirement selecting only those three matches work and reaches no
position, and is reported. Use `before` for a requirement about a decision, a
gate, or a branch—it is the phase that puts the requirement where the agent
reads it before choosing.

That command is the whole of where a `during` requirement lands, so its `when`,
its `unless`, and its `verify` render there too, on the lines beneath the
sentence they belong to. All three read the values in scope entering the step,
the same ones a `before` requirement reads, because a `during` requirement is
proved as the command is performed rather than after it.

Protocol hooks use four phases of their own:

| Phase | Runs |
| --- | --- |
| `enter` | At the start of the protocol frame. |
| `before` | Before the work its `match` selects. |
| `after` | After the work its `match` selects. |
| `exit` | At the end of the protocol frame. |

`enter` and `exit` sit at the frame boundary rather than at any selected step,
so they take no `match`; `before` and `after` require one.
