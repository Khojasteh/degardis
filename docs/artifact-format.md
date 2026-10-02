# Bundles

`degardis build` produces one self-contained bundle per selected skill: a folder by default, or a ZIP with `--zip`.

```text
.artifacts/<skill-name>/
.artifacts/<skill-name>.zip
```

The folder and ZIP contain the same skill content. A folder suits filesystem-based hosts; a ZIP suits upload-based hosts.

## Contents

| Location | Purpose |
| --- | --- |
| `SKILL.md` | Host metadata, skill-wide guidance, and task routing. |
| `references/tasks/` | One page per task with that task's complete knowledge closure. |
| `references/principles/` | Separately loaded principle pages. |
| `references/facets/` | The facet index and facet pages. |
| `references/guides/` | Separately loaded guide pages. |
| `scripts/` | Selected executable helpers, copied unchanged. |
| `assets/` | Selected supporting files and the interface icon, copied unchanged, and the generated progress register. |
| `agents/openai.yaml` | Host-facing display and invocation metadata. |

Directories appear only when needed, and `SKILL.md` and `agents/openai.yaml` are always present. Scripts, assets, and the icon keep the paths they have in the source, so `scripts/` and `assets/` are where a source conventionally puts them rather than a rule of the bundle. The progress register appears when the bundle contains at least one principle or guide page.

`SKILL.md` frontmatter carries the skill's `name`, `description`, and, when the manifest declares one, `license`. Under `metadata` it carries the skill's `version`, the `copyright` when declared, and `generated_by`, the Degardis version that built it. Every value taken from the manifest reads back exactly as the manifest states it. Its body is for the executing agent. `agents/openai.yaml` carries the manifest's interface fields in host-facing form and names the icon's path for both icon roles.

## Runtime behavior

The host starts from `SKILL.md`. The generated skill routes each outcome a request asks for to one task and does the chosen tasks one at a time, in the order the request states or else the order the manifest lists; a task may hand the work to another task under conditions its author stated. A request no task matches is reported rather than forced into one. Additional authored guidance is loaded only when it governs the situation. Conditional guidance and hand-offs apply when any one of their stated conditions holds; each condition is considered before the step that makes it relevant and is reconsidered when the situation changes.

Before an effect that cannot be freely revised within the task, the generated skill checks the applicable requirements. Before claiming completion, it checks that the requirements governing the completed work are satisfied. Reversible intermediate work does not require repeated checking merely because another intermediate result exists.

These are instruction-level guarantees, not external proof of agent behavior.

## Folder and ZIP details

Both forms give each file the same permissions; [Scripts](manual.md#scripts) states which files are executable. ZIP entries are stored uncompressed and record Unix permissions, so an archive's bytes do not depend on the host that built it and a reader that restores permissions restores the executable bits.

## Rebuilding

Do not edit a generated bundle; change the source and rebuild. [Building a bundle](manual.md#building-a-bundle) states how a rebuild replaces an existing folder or ZIP of the same skill and when its output is byte-identical.
