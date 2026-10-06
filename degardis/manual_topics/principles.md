### Principles

A principle is a standard the agent's work must honor across every task: domain-neutral guidance, or the skill's own domain guidance that holds whatever the task.

```markdown
---
title: Evidence for claims
applicability:
- Before making an externally visible claim
- Before recording a finding others will act on
---

State the observation supporting each claim beside the claim.
```

- `title` (required) — page heading and link text.
- `applicability` (optional) — conditions under which the principle applies, one per list item.

The body must be non-empty. Only the manifest's `principles` list places a principle in the bundle, by bare id. `SKILL.md`, which every task run reads, links each named principle in manifest order, and each has one generated page containing its title and body. A selected principle the manifest does not name warns and gets no page.
