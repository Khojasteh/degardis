### Guides

A guide is detail a task or a facet loads as a separate page. Knowledge stays on
the task page.

```markdown
---
title: House style
activation: When the draft will go out under the organization's name
---

Write for the organization's readers...
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | identifies the guide without stating the instructions it contains |
| `activation` | no | when the guide must be opened; omitted means it applies unconditionally |

A guide needs a non-empty body.

A task or a facet names guides by bare id:

```yaml
guides:
- house-style
```

Name the subject, not the directions: prefer `House style` to `Use sentence
case, keep lines under 80 characters, and avoid jargon`. Keep rules, exceptions,
thresholds, and procedures in the body so the title cannot substitute for
reading the page.

Whoever names the guide determines placement; the guide owns its activation.
Omitted activation is an unconditional separate load, and distinct conditions
require distinct guides. What makes a condition decidable is the same here as
for a principle; see the `principles` topic.

A task's guides sit at the foot of its task page, a facet's at the foot of that
facet's page. One guide may be named by several tasks, several facets, or both,
and stays one page stating one condition wherever it is reached from.

The agent reassesses conditions as work develops and reads an applicable guide
before continuing the work it governs.

Select guide files under `content.guides`. A selected guide that no task or
facet names and no authored Markdown links to is reported as a warning.

Each selected guide becomes one page under `references/guides/`, carrying its
title and body.
