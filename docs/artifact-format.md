# Bundles

`degardis build` creates one self-contained bundle per selected skill: a folder
by default, a ZIP archive with `--zip`.

```text
.artifacts/<skill-name>/
.artifacts/<skill-name>.zip
```

Both contain the same skill content. Choose the form your agent host accepts, and
follow that host's current instructions for where to place or upload it.

## What a bundle contains

| Location | Purpose |
| --- | --- |
| `SKILL.md` | Orientation, skill-level principle links, and task routing in its Start section. |
| `references/tasks/` | One page per task, carrying that task's whole knowledge closure. |
| `references/principles/` | One page per named principle, linked from its skill or task owner. |
| `references/profiles/` | The profile index and one page per profile. |
| `references/guides/` | Markdown pages a task opens when their activation holds, or unconditionally when it is omitted. |
| `scripts/` | Selected executable helpers, copied unchanged. |
| `assets/` | Selected supporting files and generated icons; selected files are copied unchanged. |
| `agents/` | Host-facing interface metadata when the manifest provides it. |

A directory appears only when it carries content.

## How an agent reads it


`SKILL.md` is loaded every time the skill is selected. It states what the skill
is for, a Start section, and a pointer to the profile index if there are any
profiles. Start lists skill-level principles first, then one router entry per task
with that task's own recognition cues. Profiles is the final section and points
to the profile index.

From there the agent reads **one** task page. That page carries the task's whole
knowledge closure — everything the task named plus everything that knowledge
required — so that knowledge has no second hop. Principles and guides remain
separate pages: their activation decides whether the agent opens them, and an
omitted activation applies unconditionally.

The profile index is the one lookup the bundle keeps, because which profiles
apply depends on the situation in front of the agent. A task never points at a
profile.

## Folder and ZIP

A folder build suits a host that reads skills from the filesystem; a ZIP suits
one that accepts an uploaded archive. In a ZIP, files under `scripts/` are marked
executable. A folder build copies their contents and leaves filesystem
permissions unchanged.

## Rebuilding

Building replaces the folder and ZIP carrying that skill's name inside the output
directory, so an installed or distributed bundle is overwritten by a rebuild
aimed at it.

Every selected skill is validated before a byte is written. A build that fails
leaves existing artifacts unchanged, and when several skills are built together,
a skill that completed stays available even if a later one cannot be built.

Rebuilding the same source produces a byte-identical bundle, on every host.

Do not edit a generated bundle. Update the source, validate it, and build again,
so the source stays the version you maintain.
