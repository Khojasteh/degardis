### The source folder

`degardis build` turns a source folder into a separate bundle. Edit the source,
not the bundle; Degardis does not reconstruct source from generated output, and a
command pointed at a bundle is reported rather than compiled again.

`skill.yaml` is the only file the compiler reads as YAML. Every construct is
Markdown, and anything else the skill ships is a script or an asset, copied
unchanged.

```text
my-skill/
  skill.yaml
  tasks/
  principles/
  knowledge/
  facets/
  guides/
```

`degardis init NAME` writes this tree with one valid task. Add `scripts/` and
`assets/` when needed.

These directory names are conventional: manifest globs select each namespace,
and may select subdirectories.

Everything the skill ships must be inside the source. A build output may not be
the source, contain it, or sit inside it; use a separate directory such as
`.artifacts`.

### What it builds

```text
my-skill/
  SKILL.md
  references/tasks/<task>.md
  references/principles/<principle>.md
  references/facets/index.md
  references/facets/<facet>.md
  references/guides/...
  scripts/...
  assets/...
  agents/openai.yaml
```

Directories appear only when needed. Nothing else is written: no build report,
plan, closure, source map, or coverage file.

`SKILL.md` is loaded for every request. Its sections appear in this order; empty
sections are omitted:

1. the purpose
2. **Required reading** — present when the skill has principles, guides, or facets
3. **Principles** — the skill's unconditional principles, followed by those with
   activation conditions, if any
4. **Facets** — where the facet index is, when the skill has facets
5. **Tasks** — one entry per task, with that task's recognition cues

Everything above the routing holds whatever the task, and an agent that has
chosen its task leaves the root.

Required reading tells the agent to track every page the bundle sends it to,
with the condition under which the page is required, the basis for judging that
condition, and its reading status. A page carrying no condition of its own is
required.

The agent then reads one task page containing that task's complete knowledge
closure. Principles and guides remain linked pages behind it, and the facet
index is the only lookup page.
