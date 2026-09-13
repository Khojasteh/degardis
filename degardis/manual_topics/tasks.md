## What you write

### Tasks

A task is a recognizable class of work the requester wants performed. A request
is routed to a task, and each task compiles to one page.

```markdown
---
title: Review a draft
recognize:
- the requester asks what is wrong or weak in a draft they hand over
- the requester asks whether a draft is ready to send
goal: Find the problems that would change a reader's response, each tied to a passage in the draft.
knowledge:
- cite-the-source
- audience
- order-findings
principles:
- evidence
- delegation
guides:
- house-style
---

Read the whole draft before judging any part of it.
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | names the task in the router and heads its page |
| `recognize` | yes | the cues a request is matched against, one per line |
| `goal` | yes | what is true once this task is done |
| `knowledge` | no | the knowledge this task needs, by bare id; order is preserved within each kind |
| `principles` | no | principles this task needs, by bare id; each principle's own activation decides whether it must be read |
| `guides` | no | guides this task needs, by bare id; each guide's own activation decides when it must be read |

The body is the guidance that belongs to this task and to no other. Anything a
second task would also need belongs in a knowledge unit.

### Writing recognition cues

The cues are the whole of the router: nothing is inferred from a task's title or
from the knowledge it carries.

The routes appear in the order the manifest's `tasks` field names them, and the
agent takes the first task whose cues match. The sequence is therefore yours,
and it decides which task wins where two could both match: put the work most
requests ask for first, and a task whose cues overlap a narrower one after it.

Write each cue as the request actually arrives, not as you would classify it
afterwards. "the requester asks whether a draft is ready to send" is a cue;
"editing" is a category. Give a task more than one cue when the same work is
asked for in more than one way.

### What a task page becomes

Sections appear in this order, and one with nothing to carry contributes no
heading:

1. the title
2. **Goal**
3. **Principles** — the task's unconditional principles, followed by those with activation conditions, if any
4. **Approach** — the task's own body
5. **What you need to know** — the whole knowledge closure, grouped under the present subsections **Concepts**, **Facts**, **Constraints**, **Guidance**, in that order
6. **Guides** — the task's guides with activation conditions, followed by its unconditional guides, if any

Within one knowledge kind, authored order is preserved. The cues are not on the
page: they are what `SKILL.md` matched to send the agent here.
