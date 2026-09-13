### Profiles

A profile is guidance that applies because of the situation, not because of the
task: who the audience is, what kind of material is in hand, which jurisdiction
or house style is in force. Profiles are skill-wide and independent of tasks.

```markdown
---
title: Meeting transcripts
category: Material
description: Spoken material where positions are revised as the discussion goes on.
---

A transcript records how a group got somewhere, not where it ended up...
```

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | how a reader recognizes this profile |
| `category` | no | groups the profile in the index |
| `description` | no | one sentence refining when it applies |

**A task never selects a profile.** The reader decides from the situation which
profiles apply and uses every applicable profile.

### Choosing profiles

The generated profile list carries each profile's title, its description where
you wrote one, and a link. It never repeats a profile's contents, and it never
invents a description: a profile without one shows its title alone.

The title is the index's default discriminator. Add a description only when the
title alone does not distinguish the profile from its neighbours, and use it to
state the boundary between them rather than summarize the profile body. When the
title is enough to select the profile correctly, omit the description.

Rows group by category when there are two or more categories, and are a flat list
otherwise.

Profile titles must be unique, and `index` is reserved as a profile id.
