### Knowledge units

Knowledge is reusable subject matter copied into every task closure that needs it.

```markdown
---
kind: concept
title: Audience
requires:
- source-material
---

The audience determines what must be explained and what may be assumed.
```

| Field | Required | Rule |
| --- | --- | --- |
| `kind` | yes | `concept`, `fact`, `constraint`, or `guidance` |
| `title` | yes | heading on task pages |
| `requires` | no | additional knowledge ids brought into the same closure |

The body must be non-empty.

### Kinds

A unit has one kind, which names what the unit states and the heading it appears under on task pages:

| Kind | Heading | The unit states |
| --- | --- | --- |
| `concept` | Concepts | a definition, model, or distinction |
| `fact` | Facts | an established value, figure, table, or truth |
| `constraint` | Constraints | behavior that must or must not occur |
| `guidance` | Guidance | how to act or choose |

Task pages render kinds in that order and preserve authored order within a kind. Kind changes nothing else in the bundle.
