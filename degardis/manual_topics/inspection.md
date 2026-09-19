### Seeing what the compiler decided

`inspect` reports a compilation. It runs the same checks and uses the same exit
status as `validate`; `--only` and `--all` change output, not checking.

`--only composition` shows why each task page carries its knowledge and in what
order:

```console
degardis inspect my-skill --only composition
```

```text
review-draft -> references/tasks/review-draft.md
  direct      cite-the-source, audience, order-findings
  required    source-material
  concept     audience, source-material
  constraint  cite-the-source
  guidance    order-findings
```

`direct` is task-selected knowledge; `required` came through dependencies. Kind
rows show render order.

### Reading a row

Every report begins with `skill`: identity, root, description length, tasks,
selected-content counts, and generated sizes against page budgets.

| Row | Shape |
| --- | --- |
| `sources` | `KIND ID PATH BYTES`, where a knowledge file's KIND is its own kind |
| `tasks` | `ID "TITLE" PAGE BYTES N knowledge`, then the goal, one `when` row per recognition cue, then the guides and the principles the task names |
| `knowledge` | `ID kind=KIND BYTES requires=... tasks=...` |
| `principles` | `ID PATH BYTES activation=ACTIVATION -> PLACEMENTS page=PAGE` |
| `guides` | `ID PATH BYTES [ACTIVATION] -> OWNERS` |
| `facets` | `ID "TITLE" CATEGORY BYTES DESCRIPTION` |
| `outputs` | `PATH BYTES MODE`, one row per file a build would write, where MODE is the permission a ZIP records |
| `diagnostics` | `SEVERITY CODE LOCATION MESSAGE` |

An id is a file stem. An absent value reads `-` and an empty list reads `none`,
so no row goes missing.

On `knowledge`, `tasks` lists the pages carrying the unit. On `principles`, PATH
is the source, ACTIVATION is the principle's own condition and reads `always`
where it has none, PLACEMENTS are its skill or task owners with their
conditions, and PAGE is its generated page, or `-` for a principle no level
names. On `guides`, the condition belongs to the guide and omission means
unconditional, and OWNERS are the tasks and facets naming it, each qualified as
`task:ID` or `facet:ID`.

This report is the only machine interface; builds emit no build report, plan,
closure, source map, or coverage file.

### Reading a page without building

`--page` prints generated page text without writing a bundle:

```console
degardis inspect my-skill --page SKILL.md
degardis inspect my-skill --page references/tasks/review-draft.md
```

Use bundle paths such as `SKILL.md` or a PAGE reported by `inspect`, and repeat
the option or use commas for several pages. Unavailable paths are reported; if
no selected skill generates a requested path, the run fails and lists available
pages.

### Quality measures

`--only quality` measures the compiled result without changing it.

- **Orphan knowledge** reaches no task.
- **Near-duplicate** pairs may state the same thing twice, scored by the share
  of three-word runs their bodies have in common.
- **Duplicated bytes** measure knowledge copied into multiple task closures.
- **Constraint ratio** is the share of the knowledge tasks actually carry whose
  kind is `constraint`.
- **Startup bytes** is the generated root the agent loads for every request.
- **Minimum read bytes by task** adds the root and task page.
- **Headroom** is the smallest remaining root or task-page budget.

### Saying which source a result came from

```console
degardis inspect my-skill --only identity
```

The identity rows include a source fingerprint over the manifest, selected
files, and compiler version, normalized across hosts. Quote it with saved
results.
