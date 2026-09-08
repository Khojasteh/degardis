# Bundles

`degardis build` creates one self-contained bundle for each selected skill. By
default the bundle is a folder. Add `--zip` to create a ZIP archive instead.

```text
.artifacts/<skill-name>/
.artifacts/<skill-name>.zip
```

Choose the format your agent host accepts. Follow that host's current
installation instructions for where to place or upload the finished bundle.

## What a bundle contains

Every bundle has a root `SKILL.md`. It introduces the skill and directs the
agent to the workflow material it needs: its last section is the entrypoints the
skill declares, each naming the execution module and node a request routed there
begins at, and any value that route supplies, so choosing between them costs no
read of its own. Degardis adds other directories only when the source selects
or needs them.

```text
SKILL.md
execution/
profiles/
references/
scripts/
assets/
agents/
```

| Location | Purpose |
| --- | --- |
| `SKILL.md` | The skill's starting instructions. |
| `execution/` | Required workflow instructions. |
| `profiles/` | Optional guidance for recurring situations. |
| `references/` | Supporting Markdown selected by the source. |
| `scripts/` | Selected executable helpers. |
| `assets/` | Selected supporting files and generated icons. |
| `agents/` | Host-facing interface metadata when the manifest provides it. |

The source manifest decides which references, scripts, and assets are copied.
Profiles and references are optional support; required instructions belong in the
workflow material.

## Folder and ZIP behavior

A folder build is useful when a host reads skills from the filesystem. A ZIP is
useful when a host accepts a skill archive for upload. Both contain the same
skill content. In a ZIP, files under `scripts/` are marked as executable. A
folder build copies their contents but leaves filesystem permissions unchanged.

Build into a temporary output directory while you are working:

```console
degardis build my-skill --output .artifacts
degardis build my-skill --output .artifacts --zip
```

The build refuses an output directory that overlaps the skill source. This
protects the YAML and supporting files you edit.

## Rebuilding safely

> [!WARNING]
> Building replaces the folder and ZIP with the matching skill name inside the
> output directory. Use a throwaway directory until you are ready to install or
> distribute the result.

Degardis validates every selected skill before writing a bundle. If validation
does not pass, it leaves existing artifacts unchanged. When several skills are
built together, each completed skill remains available even if a later one
cannot be built.

Rebuilding the same source produces the same bundle content on supported
platforms. The bundle contains only the files needed by the skill; it does not
include a separate build report.

Do not edit generated bundle files. Update the source, validate it, and build
again so the source remains the version you maintain.
