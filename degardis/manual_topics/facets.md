### Facets

A facet is guidance selected by the situation rather than the task. Facets are skill-wide; tasks do not select them. The agent reads every facet whose index entry applies.

```markdown
---
title: Meeting transcripts
category: Material
description: Spoken material where positions may change during discussion.
guides:
- transcript-passes
---

Treat later decisions as authoritative over earlier proposals.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | index link text and page heading; unique across facets |
| `category` | no | index grouping label |
| `description` | no | text after the title in the index and under the page heading |
| `guides` | no | guide ids opened from this facet |

The body must be non-empty.

The facet index lists each facet's title, optional description, and link. When two or more categories exist, rows are grouped by category; otherwise the index is flat.

A facet's guides appear at the foot of its page. A file a `facets` pattern matches is selected as a facet, so select facet guides under `content.guides` from outside those patterns, for example `facets/guides/`.
