### Knowledge units

A knowledge unit is one reusable piece of what the skill knows. Every task that
reaches it receives the whole unit.

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

A knowledge unit needs a non-empty body. Keep it to the smallest piece a task
can need independently; split material when tasks need different parts.

### Choosing a kind

`kind` chooses the unit's subsection under **What you need to know**. All four
kinds share the `knowledge` namespace.

| Kind | Subsection | Use it for |
| --- | --- | --- |
| `concept` | **Concepts** | what something is, how it works, or the distinctions the work reasons with |
| `fact` | **Facts** | a value, table, figure, or other stated truth the work needs |
| `constraint` | **Constraints** | something that must or must not happen |
| `guidance` | **Guidance** | how to act, choose, or do the work well |

The table is also the render order. Authored order is preserved within a kind.
