## What you write

### Tasks

A task is a recognizable class of requested work. Each task compiles to one
page.

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
second task would also need belongs in a knowledge unit. A task that names no
knowledge, no guide, and writes no body compiles to a page carrying its goal and
nothing else, and is reported as a warning.

### Writing recognition cues

The cues are the whole router; titles and knowledge do not affect matching.

The agent takes the first matching task in manifest order. Put common work early,
but place a narrow task before any broader task whose cues overlap it.

Write the request language, not a category: "the requester asks whether a draft
is ready to send," not "editing." Add cues for materially different ways of
asking for the same work.

### What a task page becomes

Sections appear in this order; empty sections are omitted:

1. the title
2. **Goal**
3. **Principles** — the task's unconditional principles, followed by those with activation conditions, if any
4. **Approach** — the task's own body
5. **What you need to know** — the whole knowledge closure, grouped under the present subsections **Concepts**, **Facts**, **Constraints**, **Guidance**, in that order
6. **Guides** — the task's unconditional guides, followed by those with activation conditions, if any

Authored order is preserved within each knowledge kind. Recognition cues remain
in `SKILL.md`.
