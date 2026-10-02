### Knowledge units

Knowledge is reusable subject matter that task pages carry.

```markdown
---
kind: concept
title: Audience
requires:
- source-material
---

The audience determines what must be explained and what may be assumed.
```

- `kind` (required) — `concept`, `fact`, `constraint`, or `guidance`.
- `title` (required) — heading on task pages.
- `requires` (optional) — additional knowledge ids brought into the same closure.

The body must be non-empty.

### Kinds

A unit has one kind, which names what the unit states and the heading it appears under on task pages:

- `concept` — a definition, model, or distinction; heading **Concepts**.
- `fact` — an established value, figure, table, or truth; heading **Facts**.
- `constraint` — behavior that must or must not occur; heading **Constraints**.
- `guidance` — how to act or choose; heading **Guidance**.

Task pages render kinds in that order. Kind changes nothing else in the bundle.
