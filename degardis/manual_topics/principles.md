### Principles

A principle is working guidance shared across kinds of work. Subject-matter
guidance belongs in knowledge.

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
| `title` | yes | a short label that identifies the principle without stating its guidance |
| `activation` | no | when this guidance must be read; omitted means it applies unconditionally |

A principle needs a non-empty body.

A skill or task names principles by bare id:

```yaml
principles:
- evidence
- delegation
```

Name the subject, not the rule: prefer `Claim verification` to `Verify every
claim against two independent sources`. Keep instructions in the body so the
title cannot replace reading the page.

### Where each one lands

Every named principle becomes one page under `references/principles/`, carrying
its title and body but not its activation.

Skill-level links render in `SKILL.md`; task-level links render on that task
page. Each link is the principle's title, and because the principle owns its
activation, every link to it states the same condition.

When every task needs a principle, name it at skill level. Do not name it at
both levels or repeat a task-level reference on every task.

### Choosing activation

Use activation only when a condition determines whether the guidance is needed,
and state it in the reader's terms. Distinct conditions require distinct
principles.

A condition is read before the page is opened and decides whether to open it, so
write one the reader can settle from what it already has; one that only the page
itself could settle sends the reader in to find out whether to go in. Name the
situation, not the subject: `Before making an externally visible claim` says
when, where `When you need the evidence principle` says nothing the reader did
not already have. Each link renders as the condition followed by the page it
guards, so write the activation to open that sentence.

A condition does one of two jobs: it decides whether a run needs the page at
all, or, for a page every run needs, when in the run to open it. A reach
condition that holds on nearly every run decides nothing, so its guidance
belongs unconditional, and one that holds on no reachable run guards a page the
agent never opens. A timing condition is judged differently: `Before making an
externally visible claim` holds on nearly every run and still earns its place,
because it names the moment the guidance is needed rather than the runs that
need it. Rarity is a fault in neither, since a condition the reader can
recognize strands nothing, however seldom it holds.

The agent reassesses conditions as work develops and reads an applicable
principle before continuing the work it governs.
