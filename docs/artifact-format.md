# Bundles

`degardis build` produces one self-contained bundle per selected skill: a folder by default, or a ZIP with `--zip`.

```text
.artifacts/<skill-name>/
.artifacts/<skill-name>.zip
```

The folder and ZIP contain the same skill content. Use the form your host accepts. An output directory holds one form per skill: building either form removes the other, so build a folder and a ZIP of the same skill into separate directories.

## Contents

| Location | Purpose |
| --- | --- |
| `SKILL.md` | Host metadata, skill-wide guidance, and task routing. |
| `references/tasks/` | One page per task with that task's complete knowledge closure. |
| `references/principles/` | Separately loaded principle pages. |
| `references/facets/` | The facet index and facet pages. |
| `references/guides/` | Separately loaded guide pages. |
| The selected script's or asset's source path, conventionally under `scripts/` or `assets/` | Selected executable helpers and supporting files, copied unchanged. |
| `assets/` | Generated skill support assets. |
| `agents/openai.yaml` | Host-facing display and invocation metadata. |

Directories appear only when needed. `SKILL.md` and `agents/openai.yaml` are always present. Generated support assets are conditional: interface icons are included when configured, and an instruction-register asset is included when the bundle contains at least one principle or guide page.

`SKILL.md` frontmatter carries the skill's `name` and `description`, plus version and rights metadata when available, and every value reads back exactly as the manifest states it. Its body is for the executing agent. `agents/openai.yaml` carries the manifest's interface fields in host-facing form.

## Runtime behavior

The host starts from `SKILL.md`. The generated skill routes a request to at most one task, reporting a request no task matches rather than forcing it into one, and loads additional authored guidance only when it governs the situation. Conditional guidance is considered before the step that makes it relevant and is reconsidered when the situation changes.

Before an effect that cannot be freely revised within the task, the generated skill checks the applicable requirements. Before claiming completion, it checks that the requirements governing the completed work are satisfied. Reversible intermediate work does not require repeated checking merely because another intermediate result exists.

These are instruction-level guarantees, not external proof of agent behavior. Degardis validates bundle integrity, not behavioral success.

## Folder and ZIP details

A folder build suits filesystem-based hosts; a ZIP suits upload-based hosts. In both forms, the files `content.scripts` selects are executable, wherever they sit, and every other file is not, whatever permissions the source files have.

## Rebuilding

A rebuild replaces whichever of the folder and ZIP with the same skill name is in the output directory, so build into a staging directory rather than a live agent skill directory. Source validation completes before writing begins. Each skill artifact is replaced atomically; if writing one skill fails, its previous artifact remains unchanged, while siblings already completed remain available.

The same source and compiler version produce byte-identical output across hosts. Do not edit generated bundles; update the source and rebuild.
