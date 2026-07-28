# Concepts

Degardis separates editable skill sources from generated bundles:

```text
skill source -> validate -> select profiles -> render and copy -> folder or ZIP
```

Validation checks the source structure and generated references. A build then
selects any requested profiles, renders agent-readable Markdown and interface
metadata, copies declared scripts and assets, and replaces the matching
artifact in the output root. The source remains the authoritative version.

## Skill

A skill is Degardis's top-level unit. It is independently buildable,
installable, and usable:

```text
skill-name/
  skill.yaml
  entries/
  workflows/
  profiles/
  scripts/
  assets/
```

The manifest supplies the source-format version, skill name, title, skill
version, description, primary workflow, content patterns, optional profile
configuration, and agent-facing interface metadata. The format version selects
the compiler contract; the skill version identifies the authored content and
is not dependency resolution metadata.

The compiler owns the generated `references/` directory. It contains rendered
entries, supporting workflows, and selected profiles. Author-provided Markdown
that should pass through unchanged belongs under `assets/`, not
`references/`.

Skills have no build-time relationships or dependencies. Selecting one skill
selects exactly that skill. Degardis controls the bundle it emits, but the
agent host decides when and how to use an installed skill at runtime.

Directories containing skills are optional, human-facing collections. Degardis
recursively discovers descendant directories with a `skill.yaml`, so
collections may use intermediate directories to organize their skills.

Once a skill is found, discovery does not search inside it. The collection
itself has no manifest, metadata, routing rules, or artifact.

## Entry

An entry is a focused rule, principle, policy, heuristic, pattern, or
constraint. Entries are rendered as Markdown references so the primary
`SKILL.md` stays concise. The optional manifest `entry_kinds` field records the
kinds an author intends to use; it does not limit the compiler's supported
kinds.

## Workflow

A workflow is an ordered procedure. One workflow is named as
`primary_workflow` and rendered into `SKILL.md`; other workflows become
references. A `use:` step may call a workflow in the same skill. Cross-skill
workflow calls are invalid because another skill may not be installed.

## Profile

A profile adds environment-specific instructions at build time. A skill can
define defaults, while `--profile` selects explicit profiles. Profiles remain
inside the owning skill's bundle. If any explicit selector is supplied, it
replaces manifest defaults for that build.

## Scripts and assets

Scripts and assets are files a skill ships alongside its instructions:
scripts are executable helpers, assets are supporting files such as templates,
examples, data, or media. Both are copied into the bundle at the same relative
path they have in the skill source. ZIP metadata additionally marks scripts
executable; folder builds do not alter host filesystem permissions. Neither
kind is parsed or rendered—they pass through byte-for-byte.

## Bundle

Degardis produces one self-contained, agent-agnostic output per skill: an
uncompressed folder, or a `.zip` archive with `--zip`. Every build requires an
output root. `SKILL.md` sits at the output's own root; there is no per-agent
layout or wrapper folder. With `--output .artifacts`, installation is a
separate copy or symlink step. When `--output` names an agent's project or
personal skill directory, an uncompressed build writes each skill directly
into its installed location. ZIP output remains a distributable artifact
rather than a filesystem installation.

For each selected skill, Degardis replaces the two matching artifact paths:
`<skill-name>/` and `<skill-name>.zip`. This removes stale output when changing
formats while preserving artifacts for unselected skills and other entries in
the output root. Replacement is transactional per skill: Degardis stages the
new artifact, backs up existing matching artifacts, and restores them if
installation fails. In a multi-skill command, replacements completed before a
later failure remain committed.
