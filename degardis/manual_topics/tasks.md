## What you write

### Tasks

A task is one recognizable class of requested work. Each task becomes one task page.

```markdown
---
title: Review a draft
cues:
- the requester asks what is wrong or weak in a draft
- the requester asks whether a draft is ready to send
goal: Identify problems that would change the reader's response.
knowledge:
- audience
guides:
- house-style
handoffs:
- task: revise-draft
  applicability:
  - When the requester authorized fixing what the review finds
  - When the review request explicitly includes revision
---

Read the whole draft before judging any part of it.
```

- `title` (required) — router label and task-page heading.
- `cues` (required) — routing cues, one per list item.
- `goal` (required) — finished state the task reaches; rendered as **Goal**.
- `knowledge` (optional) — direct knowledge ids.
- `guides` (optional) — guide ids.
- `handoffs` (optional) — tasks this one sends the work to, each a `task` id with optional `applicability` conditions, one per list item.

The body renders as **Approach**. A task with no body, knowledge, guide, or hand-off still builds but warns.

### Routing

Cues are the router; title, goal, and knowledge do not affect matching. A cue states what a request for this task's outcome looks like. Overlap between tasks' cues is expected, and manifest order resolves it.

A request may ask for the outcome of more than one task. Each outcome it asks for goes to the first task in manifest order with a matching cue, and the chosen tasks are done one at a time, in the order the request states or otherwise in manifest order. A task does only its own outcome and receives what earlier tasks produced. A request no task matches is reported rather than forced into the closest task.

### Hand-offs

A hand-off names another task this one sends the work to when its `applicability` conditions hold. An omitted `applicability` means the hand-off always follows this task. Two tasks may hand off to one task under different conditions. The agent adds an applying task to its route before continuing, so a hand-off can send work to a task before, after, or instead of finishing the current one, as its conditions say.

Hand-offs render as links on the task page and never reach `SKILL.md`. A task may not hand off to itself, and it names a target once; two tasks may hand off to each other.

### Task page order

Present sections appear in this order:

1. title
2. **Goal**
3. **Hand-offs**
4. **Approach** — task body
5. **What you need to know** — **Concepts**, **Facts**, **Constraints**, **Guidance**
6. **Guides**

Cues appear only in `SKILL.md`.
