# Concepts

Degardis separates editable skill sources from generated bundles:

```text
skill source -> validate -> select profiles -> render and copy -> folder or ZIP
```

Validation checks the structure of the source and the references the compiler
will generate. A build then selects requested profiles, renders agent-readable
Markdown and interface metadata, copies declared scripts and assets, and
replaces the matching artifact in the output directory. The source remains the
authoritative version.

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

The manifest supplies:

- the source-format version,
- the skill name, title, and version,
- a description that helps an agent decide when to use the skill,
- the primary workflow,
- the content patterns,
- optional profile configuration,
- agent-facing interface metadata.

The format version selects the compiler contract. The skill version identifies
the authored content; it is not dependency-resolution metadata.

The compiler owns the generated `references/` directory. It contains rendered
entries, supporting workflows, and selected profiles. Author-provided Markdown
that should pass through unchanged belongs under `assets/`, not under
`references/`.

Skills have no build-time dependencies. Selecting one skill selects exactly
that skill. Degardis controls the bundle it emits, but the agent host decides
how to use an installed skill at runtime.

A directory that contains skills is an optional, human-facing collection.
Degardis discovers all descendant directories that contain a `skill.yaml`, so
you can use intermediate directories to organize your skills.

Once discovery finds a skill directory, it does not search inside it. The
collection itself has no manifest, metadata, routing rules, or artifact.

## Entry

An entry is a focused piece of guidance. Common kinds include:

- `principle` — a core idea that shapes every decision;
- `policy` — a rule that limits or requires specific behavior;
- `heuristic` — a practical guideline for ambiguous situations;
- `pattern` — a repeatable way to solve a common problem;
- `constraint` — a hard boundary the output must respect;
- `rule` — a clear directive that controls behavior.

Entries render as Markdown references so the primary `SKILL.md` stays short.
An entry file sets its own kind, so a skill's kinds come from the entries it
actually contains.

## Workflow

A workflow is an ordered procedure. One workflow is named as
`primary_workflow` and rendered into `SKILL.md`. Other workflows become
reference files. A `use:` step may call another workflow in the same skill.
Cross-skill workflow calls are invalid because the other skill may not be
installed.

## Profile

A profile adds environment-specific instructions at build time, such as a
different audience, format, technology, or environment. Profiles stay inside
the owning skill's bundle.

A skill can define defaults, while `--profile` selects explicit profiles. If
any explicit selector is supplied, it replaces manifest defaults for that
build.

## Scripts and assets

Scripts and assets are files a skill ships alongside its instructions.
Scripts are executable helpers. Assets are supporting files such as templates,
examples, data, or media.

Both are copied into the bundle at the same relative path they have in the
source. ZIP metadata marks scripts as executable; folder builds do not change
host filesystem permissions. Neither kind is parsed or rendered. They pass
through byte-for-byte.

## Bundle

Degardis produces one self-contained, agent-agnostic output per skill: a
folder by default, or a `.zip` archive with `--zip`.

Every build requires an output root. `SKILL.md` sits at the output's own root;
there is no per-agent layout or wrapper folder. With `--output .artifacts`,
installation is a separate copy or symlink step. When `--output` names an
agent's project or personal skill directory, an uncompressed build writes each
skill directly into its installed location. A ZIP file is a distributable
artifact, not a filesystem installation.

For each selected skill, Degardis replaces the matching `<skill-name>/` and
`<skill-name>.zip` paths. Replacing both removes stale output when you switch
between formats. Artifacts for unselected skills, and every other entry in the
output root, stay as they were.

Replacement is transactional per skill. Degardis stages the new artifact, backs
up the existing matching artifacts, and restores them if the replacement fails.
In a multi-skill command, replacements that completed before a later failure
stay committed.
