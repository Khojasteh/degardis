### Principles

A principle is a standard the agent's work must honor. Each named principle has one generated page containing its title and body.

```markdown
---
title: Evidence for claims
activation: Before making an externally visible claim
---

State the observation supporting each claim beside the claim.
```

| Field | Required | Rule |
| --- | --- | --- |
| `title` | yes | page heading and link text |
| `activation` | no | condition for opening the page; omitted means unconditional |

The body must be non-empty. The manifest and tasks reference principles by bare id. A selected principle that neither the manifest nor a task names warns.

A principle named in `skill.yaml` is linked from `SKILL.md`, which every task run reads; one named by a task is linked from that task's page. Naming a principle at both levels warns, and so does naming it from every task instead of at skill level.

### Activation

A principle has one activation, shown on its owner links rather than on its page. The agent reassesses conditions as work changes and reads an applicable principle before continuing the work it governs.
