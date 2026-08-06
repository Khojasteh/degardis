# Artifact format

`degardis build` requires an output root. By default it writes one
self-contained folder per selected skill:

```text
.artifacts/<skill-name>/
```

Add `--zip` to write a `.zip` archive per skill instead:

```text
.artifacts/<skill-name>.zip
```

The output root contains one named folder or ZIP per selected skill. `SKILL.md`
and its companion directories sit directly inside that folder, or at the root of
the ZIP. There is no extra skill-name folder and no target-specific wrapper.

## Bundle contents

```text
SKILL.md
references/
  entries/*.md
  workflows/*.md
  profiles/*.md
scripts/
  ...
assets/
  ...
agents/
  openai.yaml
```

Degardis emits only the directories that have content. Declared icon sources
produce `assets/icon-small.png`, `assets/icon-large.png`, or both, and the
generated interface metadata points to those PNGs rather than to the authored
source path.

A bundle holds exactly one skill's content. There are no dependency skill
directories and no links to related skills. `references/` holds only
compiler-generated entries, supporting workflows, and selected profiles.

Generated `SKILL.md` frontmatter includes metadata for the skill version and
the Degardis version that produced it. This provenance travels with both
folder and ZIP artifacts.

`agents/openai.yaml` provides OpenAI interface metadata: display name,
description, icon paths, and default prompt.

ZIP metadata marks files under `scripts/` as executable. Folder builds copy
their bytes but do not change host filesystem permissions.

## Replace an artifact

For each selected skill, Degardis stages the complete new artifact before
replacing the matching `<skill-name>/` and `<skill-name>.zip` paths. If the
replacement fails, Degardis restores that skill's previous matching artifacts.
Artifacts for unselected skills and other entries in the output root remain
unchanged.

Replacement is atomic per skill, not per command. If a multi-skill build fails
partway through, earlier skills stay updated, the failing skill is restored,
and later skills are untouched. If restoration also fails, the error reports
the temporary backup location. Degardis rejects an output directory that
overlaps a selected skill's source directory.

## Install an uncompressed bundle

An uncompressed bundle can be staged for review or built directly into an
agent's skill directory.

> [!WARNING]
> Review a third-party skill's instructions and scripts before installing it;
> skills can contain executable code.

1. Choose the project or personal skill directory:

   | Agent   | Project skill directory                                         | Personal skill directory                                               |
   | ------- | --------------------------------------------------------------- | ---------------------------------------------------------------------- |
   | Claude  | `.claude/skills/<skill-name>/`                                 | `~/.claude/skills/<skill-name>/`                                       |
   | Codex   | `.agents/skills/<skill-name>/`                                 | `~/.agents/skills/<skill-name>/`                                       |
   | Copilot | `.github/skills/<skill-name>/`, `.claude/skills/<skill-name>/`, or `.agents/skills/<skill-name>/` | `~/.copilot/skills/<skill-name>/` or `~/.agents/skills/<skill-name>/` |
   | Cursor  | `.cursor/skills/<skill-name>/` or `.agents/skills/<skill-name>/` | `~/.cursor/skills/<skill-name>/` or `~/.agents/skills/<skill-name>/`   |
   | Roo     | `.roo/skills/<skill-name>/` or `.agents/skills/<skill-name>/`    | `~/.roo/skills/<skill-name>/` or `~/.agents/skills/<skill-name>/`      |

   The cross-agent `.agents/skills` location is also recognized by Copilot,
   Cursor, and Roo. Use it when one checked-in installation should serve those
   agents as well as Codex. Claude uses `.claude/skills`.

   Host documentation: [Claude](https://code.claude.com/docs/en/skills),
   [Codex](https://learn.chatgpt.com/docs/build-skills),
   [Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills),
   [Cursor](https://cursor.com/docs/skills), and
   [Roo](https://roocodeinc.github.io/Roo-Code/features/skills/).

2. Either build to `.artifacts` and copy or symlink the generated skill
   folder, or set `--output` to the parent skill directory to build and install
   in one step:

   ```console
   degardis build examples/structured-summary --output .agents/skills
   degardis build examples/structured-summary --output .claude/skills
   degardis build examples/structured-summary --output .github/skills
   degardis build examples/structured-summary --output .cursor/skills
   degardis build examples/structured-summary --output .roo/skills
   degardis build examples/structured-summary --output ~/.agents/skills
   degardis build examples/structured-summary --output ~/.claude/skills
   ```

   These commands create `<skill-name>/` beneath the output directory.
   Relative paths target the current workspace; `~/` targets the current
   user's home directory. Building directly into one of these locations
   replaces any existing folder or ZIP for that skill name.

3. Do not use `--zip` for a direct filesystem installation. Filesystem-based
   agents expect an uncompressed `<skill-name>/SKILL.md` folder; a ZIP placed
   in their skill directory is not installed.

4. For ChatGPT, `--zip` produces an archive for upload. Open
   [Skills in ChatGPT](https://chatgpt.com/skills), select the **+** button,
   choose **Upload from your computer**, and upload the archive as-is.
   Availability and workspace permissions vary; see the
   [ChatGPT skills documentation](https://help.openai.com/en/articles/20001066-skills-in-chatgpt/).

`~/` is your home directory: `/home/<you>/` on Linux, `/Users/<you>/` on
macOS, and `C:\Users\<you>\` on Windows (`%USERPROFILE%`).
