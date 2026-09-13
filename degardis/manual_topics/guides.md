### Guides

A guide is a Markdown page a task opens as a separate load for detail it does
not carry itself.

```markdown
---
title: House style
activation: when the draft will go out under the organization's name
---

Write for the organization's readers...
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | names the guide in its task link and heads its page |
| `activation` | no | when the guide must be opened; omitted means it applies unconditionally |

A task names the guide by its file-stem id:

```yaml
guides:
- house-style
```

The task reference owns placement because only a task can say it needs the
guide. The guide owns activation because its condition is the same everywhere
it is used. Write separate guides when the material needs separate conditions.

A guide with activation is for detail the situation decides whether to load. A
guide without activation is an unconditional separate load. Knowledge remains
the material the compiler places directly on the task page.

The guide page begins with the title, then carries the Markdown body. The body
does not need to begin with a Markdown heading.

The guide's filename stem is its id, and the manifest selects it under
`content.guides`. Every selected guide must either be named by a task or linked
from authored Markdown.
