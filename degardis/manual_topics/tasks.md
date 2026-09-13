## What you write

### Tasks

A task is one recognizable class of requested work. Each task becomes one task page.

```markdown
---
title: Review a draft
recognize:
- the requester asks what is wrong or weak in a draft
- the requester asks whether a draft is ready to send
goal: Identify problems that would change the reader's response.
knowledge:
- audience
principles:
- evidence
guides:
- house-style
---

Read the whole draft before judging any part of it.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | router label and task-page heading |
| `recognize` | yes | request cues, one per list item |
| `goal` | yes | finished state the task reaches; rendered as **Goal** |
| `knowledge` | no | direct knowledge ids |
| `principles` | no | principle ids |
| `guides` | no | guide ids |

The body renders as **Approach**. A task with no body, knowledge, or guide still builds but warns.

### Routing

Recognition cues are the router; title, goal, and knowledge do not affect matching. The first task in manifest order with a matching cue is chosen.

### Task page order

Present sections appear in this order:

1. title
2. **Goal**
3. **Principles**
4. **Approach** — task body
5. **What you need to know** — **Concepts**, **Facts**, **Constraints**, **Guidance**
6. **Guides**

Recognition cues stay in `SKILL.md`. Within **Principles** and **Guides**, unconditional links come before conditional ones. Authored knowledge order is preserved within each knowledge kind.
