### Principles

A principle is working guidance that can matter across kinds of work: how to keep
observation apart from inference, what a report owes its reader, when to ask
rather than guess. Guidance about the subject matter itself is knowledge, and a
task names that knowledge directly.

```markdown
---
title: Evidence for claims
activation: Before making an externally visible claim
---

A claim reaches the report with the observation it rests on beside it.

Every finding states what it rests on: the line, the run, the measurement...
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | a short, distinguishing heading for the principle |
| `activation` | no | when this guidance must be read; omitted means it applies unconditionally |

Each principle is a file in `principles/`, and its filename is its id. A skill
or task lists the principles it needs by bare id:

```yaml
principles:
- evidence
- delegation
```

### Where each one lands

Every named principle gets one generated page under `references/principles/`.
Skill-level references render on the root before task routing. Task-level
references render on that task page. A principle with an activation carries the
same wording beside every one of its links.

Each placement is a link whose text is the principle's title; the principle's
body appears only on its separate page. That page begins with the title and then
the body, and does not repeat the activation. A reader with only the principle
page therefore cannot tell whether its link was conditional or unconditional.

When every task needs a principle, name it at skill level instead. Do not name a
principle at both skill and task level; keep it at the one level that owns its
placement. Validation warns about either placement that makes a reader load the
same guidance unnecessarily.

The reference owns placement because only the skill or task that needs the
guidance can name it. The principle owns activation because the condition under
which its guidance applies is the same everywhere it is used.

### Choosing activation

Use an activation only when a condition determines whether the guidance is
needed. State that condition in the reader's terms. Write separate principles
when distinct guidance needs separate conditions.
