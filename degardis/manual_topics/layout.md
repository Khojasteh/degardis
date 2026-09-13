### The source folder

The source is an ordinary folder that you edit and keep. `degardis build` turns
it into a separate bundle for an agent host. You never edit that bundle, and
Degardis does not reconstruct source from it. A command pointed at a bundle — a
directory holding `SKILL.md` and no `skill.yaml`, or a ZIP archive — is reported
rather than read.

`skill.yaml` sits at the top of the folder and is the only YAML file in the
source. Every construct is a Markdown file.

```text
my-skill/
  skill.yaml
  tasks/
  principles/
  knowledge/
  profiles/
  guides/
```

`degardis init NAME` writes this tree with one task that already validates and
builds. Add `scripts/` and `assets/` when you ship files of those kinds.

The manifest selects each namespace by glob, so these directory names are
convention. Subdirectories are fine where a pattern selects them; ids are still
file stems and stay unique across the whole namespace. A knowledge file's `kind`
frontmatter — `concept`, `fact`, `constraint`, or `guidance` — classifies it,
not its directory.

Two rules bound the folder. Everything the skill ships sits inside it: a file
selected or named from outside the skill directory is reported. And a build
output directory may not be the source directory, sit inside one, or contain
one, so build into a throwaway directory such as `.artifacts` while you work.

### What it builds

```text
my-skill/
  SKILL.md
  references/tasks/<task>.md
  references/principles/<principle>.md
  references/profiles/index.md
  references/profiles/<profile>.md
  references/guides/...
  scripts/...
  assets/...
  agents/openai.yaml
```

A directory appears only when the source needs it: a skill with no profile gets
no `references/profiles/`. Nothing else is written — no build report, no plan file, no
source map.

`SKILL.md` is loaded every time the skill is selected. It states what the skill
is for, the guidance every task shares, a pointer to the profile index, and the
router that matches a request to a task.

From there an agent reads one task page. That page carries the task's whole
knowledge closure, grouped by kind, so knowledge has no second hop. Principles
and guides remain separate pages when the root or task links to them. The profile
index is the only lookup the bundle keeps.
