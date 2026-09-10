## Choosing a requirement

Requirements are instructions the agent must follow, not suggestions. Three
constructs carry them, and they differ in what they hold onto:

| You need to say | Choose | Because |
| --- | --- | --- |
| "Always stay within this boundary." | A policy. | Several requirements protect one thing and belong together. |
| "When this condition is true, do or do not do this." | A rule. | The requirement has its own condition and no larger boundary. |
| "Keep track of this until it is safely finished." | A protocol. | Something is opened in one place and must be closed in another. |

Use a heuristic, guidance, or profile only for advice that is safe to ignore.
Advice can improve a result; it can never authorize an action, prohibit one, or
prove that a requirement was met.

All three share the same three questions, each answered by its own field. *Which
work does this apply to?* is `match`, a selector over declared metadata. *Where
relative to that work?* is `phase`. *How is it proved?* is the optional `verify`.
A policy provision answers all three; a rule answers all three; a protocol hook
answers them too, with its own phase names and a state transition beside them.

Bind a policy or a rule at the manifest, a workflow, or a step—whichever is the
narrowest scope where it applies. A protocol is bound the same way, and the
scope decides the lifetime of its frame: the full run, one workflow invocation,
or one reached step.

Two findings tell you a binding did not land where you meant it to. A bound
requirement whose selector matches no reachable work at its phase is reported as
unmatched: the selector names something this skill does not do. One that matches
but reaches no generated position is reported as unlowered, and the usual cause
is a `during` requirement selecting only a decision, a gate, or a branch, which
[Phases](#phases) explains.
