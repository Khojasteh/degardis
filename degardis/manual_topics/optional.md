## Reusable and optional material

The constructs above carry required behavior. These five carry everything else:
a method you want to reuse, and the advice, context, and documents that make a
result better without the skill depending on them.

All five are shipped by a `content` key. What differs is how the running agent
reaches them:

| Part | Reached by | Carries |
| --- | --- | --- |
| Pattern | A `pattern` step. | A reusable procedure that is required where it is applied. |
| Heuristic | A `decide` or `gate` step. | Advice for making one choice well. |
| Guidance | The manifest, a workflow, or a step. | Optional context at that scope. |
| Profile | Nothing in the workflow; the agent matches a situation. | Auxiliary material for a recurring situation. |
| Reference, script, asset | A `resource`, or a `references` field. | A document, helper, or file. |

A pattern is the exception in this group: what it contributes is required work,
and the only thing optional about it is whether a workflow applies it.

Everything else here is advice, and the boundary is enforced. A heuristic cannot
authorize an action, prohibit one, or verify a requirement. Guidance carries no
binding command. A profile can never decide validity or failure: removing every
profile from a built skill leaves the required instructions unchanged, so a
profile that is missed, or matched wrongly, cannot change what the agent must
do. Keep every required instruction in a workflow, policy, rule, protocol, or
pattern, so a skill whose optional material is never read still does the job.
