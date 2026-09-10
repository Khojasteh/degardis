## Modeling a skill

You are not writing a program for Degardis. You are describing a skill for an
AI agent: what job it performs, what information it needs, what it must do, and
how it knows it is finished.

| Part | Purpose | Use it for |
| --- | --- | --- |
| Manifest | The skill's cover sheet. | Name the skill, say when it applies, and choose its files. |
| Workflow | The required route through the job. | Tell the agent what to do, decide, check, and return. |
| Value | Information passed between parts of the workflow. | Keep important results explicit instead of relying on memory. |
| Record | A value with named fields. | Pass several related results as one value. |
| Policy, rule, or protocol | A requirement. | Set a boundary, a conditional requirement, or state that lasts across steps. |
| Pattern | A reusable way of doing a job. | Repeat a small procedure in more than one place. |
| Heuristic, guidance, or profile | Helpful but optional advice. | Improve a result without making the skill depend on that advice. |
| Reference, script, or asset | Supporting material. | Give the skill a document, helper, or file it needs. |

Three words recur throughout this manual. A *construct* is one part above,
written in one file. To *bind* a requirement is to name it at the manifest, a
workflow, or a step, which is the *scope* over which it applies. A construct
that is never bound, selected, or called is reported rather than shipped.

Two properties follow from that, and shape every choice below. A required
instruction reaches the agent only through a workflow, a policy, a rule, a
protocol, or a pattern; a reference, profile, heuristic, or guidance page can
help but can never carry work the skill depends on. And the compiler places
each bound requirement in the workflow position where it is enforced, so where
you bind it decides where the agent reads it.

Start small: one manifest and one workflow are enough for a working skill. Add
the other parts only when they solve a problem the workflow cannot express
clearly on its own. `degardis validate` tells you when there are missing or
misused parts.
