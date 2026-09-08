## Checking a source

`degardis validate PATH` runs every check over a source and reports what it
found. `degardis build PATH --output DIR` runs the same checks and writes a
bundle only if they pass, so a failing source never becomes a bundle and a
completed build is never half-written.

Every finding carries a check code, such as `rule.unmatched`. Run
`degardis explain CODE [CODE ...]` for what triggers that check, why it matters,
and a failing and a passing example. A code is built from the construct and the
key it concerns—`workflow.missing-entry`, `interface.invalid-brand_color`—so
where you know the key you can look the check up without searching for it.

Checks collect rather than stop at the first problem, so one run reports
everything it can see. They fall into five groups, roughly in the order a source
is read:

| Group | Establishes |
| --- | --- |
| Files and fields | Every selected file parses, and every field is one the schema declares, present where required and readable where given. |
| Names and references | Every identifier is well formed, unique in its kind, selected by a content pattern, and of the kind expected where it is named. |
| Flow and values | Every path is complete and acyclic, every outcome handled, every value available with a compatible type where it is read, and every produced value read. |
| Binding and lowering | Every bound requirement matches reachable work and reaches the position that enforces it. |
| The generated skill | Every command reads as an instruction, every link is reachable, no two files collide, and the result fits its load budgets. |

A pass means the source compiles to a complete execution graph. It does not
mean the skill guides an agent well: whether the commands say the right thing,
whether the requirements protect what matters, and whether the decisions are the
ones a reader faces are judgements no check can make for you.

Warnings do not fail a run by default. Pass `--fail-on-warning` where a warning
should stop a build, and read the warnings either way—most name something that
will not behave the way the source suggests.
