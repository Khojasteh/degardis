### Profiles

A profile is auxiliary guidance for a recurring situation—a language, a
framework, a kind of material the skill keeps meeting. `content.profiles` ships
it, but nothing in the workflow reaches it: the built skill offers an index, and
the agent opens a profile whose situation matches the work in front of it.

| Field | Required | Meaning |
| --- | --- | --- |
| `points` | Yes | Non-empty list of guidance. |
| `title` | No | Profile page title; omitting it warns and uses the filename. |
| `description` | No | Situation in which the profile is useful. |
| `category` | No | Optional grouping label. |
| `references` | No | Supporting Markdown. |

```yaml
title: Regulated material
description: Applies when the material carries a confidentiality marking.
category: Material
points:
- Keep the marking on every extract you quote.
- Summarize the finding rather than the identifying detail behind it.
```

Give a profile a `title` and a `description` that let an agent decide whether it
applies without opening it, since that decision is made from the index alone.
Two profiles may not share a title, compared without regard to case.

`references` names supporting Markdown the same way a pattern, a heuristic, or a
guidance file does: each path is the one the bundle ships, selected under
`content.references`, and the generated profile page links it rather than
absorbing it. A page nothing else points at is reached through the profile that
names it, so keep it to material a reader of that profile wants.

A profile stands outside execution entirely, and two checks keep it there. It
may not declare policies, rules, protocols, or workflows, and no workflow or
step may name one. That is what guarantees a profile missed, or matched wrongly,
cannot change what the skill requires: put nothing in a profile that the job
depends on.
