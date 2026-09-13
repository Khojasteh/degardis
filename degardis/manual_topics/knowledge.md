### Knowledge units

A knowledge unit is one reusable piece of what your skill knows. You write it
once, and every task that reaches it gets the whole of it.

```markdown
---
kind: concept
title: What supplied material is made of
requires:
- audience
---

Material breaks into subjects, claims, and the authority behind each claim.

Treat anything handed over as three layers, not one body of text...
```

| Field | Required | What it is |
| --- | --- | --- |
| `kind` | yes | which subsection carries the unit: `concept`, `fact`, `constraint`, or `guidance` |
| `title` | yes | the heading this unit is compiled under |
| `requires` | no | other knowledge this unit brings into the same task closure, by bare id |

A knowledge unit needs a non-empty body.

### Choosing a kind

Kind is presentation metadata. It does not create another namespace, change the
unit's id, or change how another unit refers to it. It decides which subsection
of **What you need to know** carries the unit.

| Kind | Subsection | Use it for |
| --- | --- | --- |
| `concept` | **Concepts** | what something is, how it works, or the distinctions the work reasons with |
| `fact` | **Facts** | a value, table, figure, or other stated truth the work needs |
| `constraint` | **Constraints** | something that must or must not happen |
| `guidance` | **Guidance** | how to act, choose, or do the work well |

Those rows are also the render order: a task's closure is grouped as concepts,
facts, constraints, then guidance, and within one kind authored order is
preserved.

### Keeping units small

A unit is the smallest reusable thing a task can want on its own. Two tasks
needing overlapping but different material is the sign that one unit should be
two: split it, and let each task name the part it needs.
