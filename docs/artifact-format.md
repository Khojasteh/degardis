# Bundles

`degardis build` creates one self-contained bundle per selected skill: a folder
by default, a ZIP archive with `--zip`.

```text
.artifacts/<skill-name>/
.artifacts/<skill-name>.zip
```

Both contain the same skill content. Choose the form your agent host accepts,
and follow that host's current instructions for where to place or upload it.

## What a bundle contains

| Location | Purpose |
| --- | --- |
| `SKILL.md` | Host frontmatter, orientation, required-reading instructions, skill-level principle links, a facet-index pointer, and task routing. |
| `references/tasks/` | One page per task, carrying that task's whole knowledge closure. |
| `references/principles/` | One page per named principle, linked from its skill or task owner. |
| `references/facets/` | The facet index and one page per facet. |
| `references/guides/` | Markdown pages a task or a facet opens when the guide's activation holds, or, where it has none, whenever the page naming it applies. |
| `scripts/` | Selected executable helpers, copied unchanged. |
| `assets/` | Selected supporting files, copied unchanged, and the PNG icons rendered from `interface.icon`. |
| `agents/` | `openai.yaml`, the interface metadata a host reads. |

A directory appears only when it carries content. `SKILL.md` and
`agents/openai.yaml` are written for every bundle, because every manifest
declares an interface.

## What a host reads

`SKILL.md` opens with YAML frontmatter before its Markdown body: the `name` and
`description` from the manifest, and a `metadata` block carrying the skill's
version, the Degardis version that generated it, and the copyright and licence
lines where the manifest supplied them. Everything below that is for the agent.

`agents/openai.yaml` restates the manifest's `interface` for a host that reads
that file: the display name, the short description, the brand colour and icon
files where the manifest supplies them, and the default prompt with `{name}`
resolved into that host's invocation syntax.

## How an agent reads it

`SKILL.md` is loaded every time the skill is selected. From there the agent reads
**one** task page, carrying that task's whole knowledge closure, with principles,
guides and the facet index as separate pages behind it. The root also asks the
agent to keep a reading register of every page the bundle sends it to, and to
state at each delivery what is still outstanding.

The [reference manual](manual.md#what-it-builds) gives that reading path in
full. These instructions do not establish that an agent followed them: Degardis
validates artifact integrity, not agent behavior.

## Folder and ZIP

A folder build suits a host that reads skills from the filesystem; a ZIP suits
one that accepts an uploaded archive.

In a ZIP, files under `scripts/` are marked executable. A folder build copies
their contents and leaves filesystem permissions unchanged.

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
