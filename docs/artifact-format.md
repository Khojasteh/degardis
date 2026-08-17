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
execution/
  *.md
profiles/
  index.md
  <profile-page>.md
references/
  patterns/*.md
  heuristics/*.md
  guidance/*.md
  ...any Markdown selected by content.references
scripts/
  ...
assets/
  ...
agents/
  openai.yaml
```

Degardis emits only directories that have content. A bundle holds exactly one
skill.

### `SKILL.md` is the control plane

The generated root stays small: it states the execution contract and then loads
the primary workflow's module at a named entry node. It does not inline every
reachable workflow or enumerate every profile.

Required workflow bodies live under `execution/`, named `<workflow>-01.md`
onwards. A workflow can span numbered parts, and
each part's heading says which it is, as `(2/3)`; only the part holding the
workflow's entry node names one. Boundaries and the order of independent nodes
can differ from source order to reduce reading along execution paths. Every
transition still points forward within its workflow. See
[the portable execution contract](concepts.md#the-portable-execution-contract).

### `profiles/` is optional auxiliary guidance

Profiles are outside the execution graph. `profiles/index.md` lists every profile
the bundle ships, each linked to a page carrying its advisory points and any
bundled guide text. Missing, unread, or deleted profiles never block execution
and never change requirements, validity, verification, or failure behavior.

### `references/` is non-binding support

Selected `content.references` files are copied at their source-relative paths,
beside a generated page for each reached pattern, heuristic, and guidance unit
that carries reference material of its own.

Generated Markdown links are relative to the page containing them, so links
from execution modules and auxiliary pages resolve within the installed bundle.

Required behavior never depends on `references/`. Deleting the whole tree leaves
every requirement in place.

### Scripts, assets, and icons

References, scripts, and assets are copied byte for byte to the same relative
path they occupy in the source. Neither kind is parsed or rendered.

A declared `interface.icon` is rasterized into `assets/icon-small.png` and
`assets/icon-large.png`, and the generated interface metadata points at those
PNGs rather than at the authored source path.

ZIP metadata marks files under `scripts/` as executable. Folder builds copy
their bytes but do not change host filesystem permissions.

### `agents/openai.yaml`

This file provides OpenAI interface metadata: display name, short description,
generated icon paths, brand color, and default prompt. Each field appears only
where the manifest declared it, and the default prompt's `{name}` placeholder is
rendered in the invocation syntax that target expects.

### Reproducible bytes

Generated text is written with `\n` line endings on every platform, and an
archive records a fixed entry timestamp, so the same source produces the same
bundle bytes wherever it is built. Nothing in the bundle depends on the machine
that built it, and no source-map or coverage file is emitted beside it.

## Replace an artifact

> [!WARNING]
> A build replaces the matching `<skill-name>/` folder and `<skill-name>.zip` in
> the output root. Point `--output` at a throwaway directory such as
> `.artifacts` while you are editing, and at an agent skill directory only when
> you mean to install.

Every selected source is checked before anything is written, so a run that
reports a failure has changed nothing on the way to it.

A build replaces both the `<skill-name>/` folder and the `<skill-name>.zip` for
each selected skill, which removes stale output when you switch between the two
formats. Artifacts for unselected skills, and everything else in the output root,
stay as they were.

Replacement is atomic per skill, not per command. A failed replacement restores
that skill's previous artifacts, and names the temporary backup location if it
cannot. If a multi-skill build fails partway through, earlier skills stay
updated and later skills are untouched.

Degardis rejects an output directory that is the same as, contains, or is
contained by a selected skill's source directory.

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

4. For ChatGPT, `--zip` produces an archive for upload. Use the current
   [Skills in ChatGPT](https://chatgpt.com/skills) workflow to upload it.
   Availability, workspace permissions, and the ChatGPT interface vary; see the
   [ChatGPT skills documentation](https://help.openai.com/en/articles/20001066-skills-in-chatgpt/).
