### The source folder

A source has one `skill.yaml` manifest plus authored files selected by it. Constructs are Markdown; scripts and assets are shipped files.

```text
my-skill/
  skill.yaml
  tasks/
  knowledge/
  principles/
  facets/
  guides/
  scripts/
  assets/
```

`degardis init NAME` creates a minimal valid source. The directories above are conventional, not required; manifest patterns decide which namespace each selected file belongs to and may select subdirectories.

Every selected file, and the interface icon, must be inside the source. Source and output paths may not overlap. Generated bundles are output only and cannot be used as source input; one inside a directory of skills is passed over.

### What it builds

```text
my-skill/
  SKILL.md
  references/tasks/...
  references/principles/...
  references/facets/...
  references/guides/...
  scripts/...
  assets/...
  agents/openai.yaml
```

Directories appear only when needed. Scripts and assets keep the paths they have in the source, so `scripts/` and `assets/` appear where the source uses them. Builds emit no plan, closure, source map, coverage file, or build report.

`SKILL.md` is the bundle entry point. It identifies the skill, carries its skill-wide guidance, and routes requests to the appropriate task-specific and situational guidance.
