### Facets

A facet is guidance selected by one aspect of the situation, such as audience,
material type, or jurisdiction. Facets are skill-wide; tasks never select them.

```markdown
---
title: Meeting transcripts
category: Material
description: Spoken material where positions are revised as the discussion goes on.
guides:
- transcript-passes
---

A transcript records how a group got somewhere, not where it ended up...
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | how a reader recognizes this facet |
| `category` | no | groups the facet in the index |
| `description` | no | one sentence refining when it applies |
| `guides` | no | guides this facet opens, by bare id |

A facet needs a non-empty body.

The reader uses every facet that applies to the situation.

### Guides a facet opens

A facet names guides the way a task does, and they render the same way: a Guides
section at the foot of the facet page, unconditional guides first, then those
with an activation, each row carrying the guide's own condition.

Use one when a facet needs material too long to sit in its body and only worth
loading once the facet applies. A guide a facet names is loaded because the
situation called for the facet, not because any task selected it, so the reader
reaches it only through the facet page.

Keep facet guides in `facets/guides/` and select them with their own
`content.guides` pattern, so the file tree shows which guides belong to facets
and which to tasks:

```yaml
content:
  facets:
  - facets/*.md
  guides:
  - guides/*.md
  - facets/guides/*.md
```

This is a convention, not a rule: the manifest decides what a file is, and a
guide compiles to the same `references/guides/ID.md` wherever its source sits.
Keep the facet pattern to `facets/*.md` rather than `facets/**/*.md`, or it
selects the guides under it as facets too. Ids are unique across the whole
`guides` namespace, so a facet guide may not share a stem with a task guide.

### Choosing facets

The facet index shows each title, optional description, and link. It never
repeats facet bodies or invents descriptions.

Add a description only when the title cannot distinguish the facet from
another. State the selection boundary, not a summary of the body.

Rows group when two or more categories exist; otherwise they remain flat.

Titles must be unique, and `index` is a reserved facet id.
