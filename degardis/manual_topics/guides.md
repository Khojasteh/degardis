### Guides

A guide is detail a task, facet, or another guide loads as a separate page.

```markdown
---
title: House style
applicability:
- When the result will be published under the organization's name
- When the requester asks for the house style
requires:
- citation-style
---

Use the organization's publication rules.
```

- `title` (required) — page heading and link text.
- `applicability` (optional) — conditions under which the guide applies, one per list item.
- `requires` (optional) — ids of guides this guide cannot be understood without.

The body must be non-empty. Each selected guide has one generated page containing its title, its body, and the guides it owns, however many owners list it. A selected guide that no page lists and no inline reference names warns.
