### Guidance

Guidance is optional context, used at the manifest, a workflow, or a step. It
carries no required behavior: it explains, frames, or reminds, and the skill
works the same if an agent skims past it.

| Field | Required | Meaning |
| --- | --- | --- |
| `summary` | Yes | Short guidance shown where it is used. |
| `rationale` | No | Why the guidance helps the reader. |
| `title` | No | Reader-facing title. |
| `points` | No | Additional optional guidance. |
| `references` | No | Supporting Markdown. |

```yaml
title: Clear reporting
summary: Report what the work established, not how the work was done.
rationale: The reader needs the outcome before the method.
points:
- Lead with what the reader has to act on.
- Name what was not covered, so a short report does not read as a complete one.
```

Where guidance is applied, `detail` decides how much of it appears. Omit
`detail`, or write `detail: synopsis`, for the `summary` alone; write
`detail: inline` to bring the `points` in at that place. `detail: inline` on a
guidance file that declares no `points` is reported, and so is naming guidance
where a binding construct is expected.

Guidance renders once per scope. Bind it at the manifest when it frames the
whole skill, at a workflow when it frames that job, and at a step when it only
helps there.
