### Subjects and effects

A tag labels work so that a requirement can find it. `subjects` say what the
work is about; `effects` say what it does to the world. Declare them on the
steps and procedure items that do the work, and select on them from a policy
provision, a rule, or a protocol hook.

```yaml
write-summary:
  action: Write the summary the chosen depth calls for.
  subjects: [summary.write]
  effects: [workspace.write]
  next: review
```

A tag is lowercase, written in segments of letters and digits joined by `.` or
`-`: `summary.write`, `workspace.write`, `gap.report`. Nothing about a tag's
words carries meaning to the compiler. `workspace.write` restricts nothing by
itself; it matches a selector that names `workspace.write`, and that is all.
The meaning is the one your own requirements give it.

Choose a vocabulary and keep to it. Segments are what make a prefix selector
work: `publication.*` matches `publication.draft` and `publication.release`
together, and the bare tag `publication` as well. Group related work under a
shared first segment and you can widen or narrow a requirement without touching
any step.

Two tags on one step are both true of it, and a selector naming either finds it.
Tag a step for what it actually does rather than for the requirement you have in
mind, so that a requirement added later finds the work already labelled.

Tags are declared on a workflow step and on a pattern's procedure items. A
pattern application declares no effects of its own: the items inside the pattern
are the work, so they carry the tags.
