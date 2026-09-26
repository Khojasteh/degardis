### Guides

A guide is detail a task or facet loads as a separate page.

```markdown
---
title: House style
activation: When the result will be published under the organization's name
---

Use the organization's publication rules.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | page heading and link text |
| `activation` | no | condition for opening the page; omitted means unconditional |

The body must be non-empty. Tasks and facets reference guides by bare id; an owner's guides are linked at the foot of its page. A selected guide with no owner or inline reference warns. Each selected guide has one generated page containing its title and body.

One guide may have several owners but keeps one page and one activation, shown on its owner links rather than on its page. The agent reassesses conditions as work changes and reads an applicable guide before continuing the work it governs.
