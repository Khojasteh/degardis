# Reference

Use this page to look up Degardis's current CLI, discovery rules, source
schemas, and Python API. For a first build, follow
[Getting started](getting-started.md); for a guided source example, use
[Authoring skills](authoring-guide.md).

## CLI

All commands require one or more paths. Each path may name a skill directory
or a collection directory; see [Discovery](#discovery). CLI paths expand `~`
and environment variables. Relative paths are resolved from the current
working directory.

Completed commands return status 0. Reports and build paths are written to
standard output. Warnings and `[ERROR]` messages are written to standard error.
An invalid source, selection, path, or filesystem operation returns status 1
without a traceback. Invalid command syntax returns status 2 with command
usage.

### `degardis list PATH [PATH ...]`

Lists each selected skill's title, manifest name, version, description,
available profiles, whether it includes scripts, license, copyright, and
absolute source path. Missing optional legal metadata is reported as
`Not specified`; a skill with no profiles reports `None`. It does not apply
profile defaults, validate the full source, execute scripts, or create output.

### `degardis validate PATH [PATH ...]`

Validates discovery, manifests, entries, workflows, profiles, generated
artifact-path collisions, and generated links for the selected skills. It does
not execute bundled scripts. It also warns when the generated `SKILL.md`, using
manifest-default profiles, exceeds the recommended 500-line maximum. This
warning does not fail validation. The command creates no artifact. Each skill
is reported as a pass or failure, with validation messages grouped below it.
The final summary reports passed, failed, and total counts plus any warning
count. Success exits with status 0; any failed skill exits with status 1.

### `degardis build PATH [PATH ...] --output PATH`

Builds one uncompressed skill folder per selected skill by default, or one
`.zip` archive per skill with `--zip`.

Options:

- `--output PATH`: required output root.
- `--zip`: write a `.zip` archive per skill instead of an uncompressed folder.
- `--profile PROFILE`: include a match in every selected skill.
- `--profile SKILL:PROFILE`: include one selected skill's profile.
- `--profile all`: include every selected skill's profiles.
- `--profile SKILL:all`: include every profile owned by one selected skill.

The `--profile` option may be repeated. Providing one or more explicit
selectors replaces all manifest defaults for that build. An unqualified
selector that exists in several selected skills includes that profile in each
of them. A named selector that matches no selected skill is an error.
`--profile all` remains valid when selected skills define no profiles and
builds them without profile additions.

The build checks the generated `SKILL.md` using the profiles selected for
that build. More than 500 lines produces a warning but does not prevent
artifact creation. The warning is written to standard error after the
artifacts are built.

An uncompressed build installs the selected skills when `--output` is an
agent's project or personal skill directory, such as `.agents/skills`,
`.claude/skills`, `~/.agents/skills`, or `~/.claude/skills`. Degardis creates
one `<skill-name>/` child in that directory. ZIP files are not installed
skills in those locations; `--zip` instead produces archives ready for
direct upload to ChatGPT.

Before replacing output, Degardis validates every selected source and
resolves every requested profile. It then processes skills one at a time.

For each skill, Degardis stages the complete artifact, backs up any existing
`<skill-name>/` and `<skill-name>.zip`, and restores both if replacement
fails. If restoration itself fails, the error reports the temporary backup
location.

Replacement is atomic per skill, not for the whole command. In a multi-skill
build, successfully replaced skills remain updated if a later skill fails.
The failing skill is restored and skills not yet processed remain unchanged.
Other entries in the output root are always preserved.

For safety, Degardis rejects an output directory that is the same as,
contains, or is contained by a selected skill source directory. A relative
output path is resolved from the current working directory. On success, the
command reports every skill and the absolute path of its generated folder or
archive, followed by a summary.

## Discovery

A path containing `skill.yaml` selects that skill. Otherwise, Degardis selects
all descendant directories containing `skill.yaml`, recursively. Once discovery
finds a skill directory, it does not search inside that skill for additional
skills. Duplicate paths are ignored; duplicate names at different paths are
rejected. A missing path, a non-directory path, or a directory with no
descendant skills is an error.

## `skill.yaml`

| Field              | Required | Meaning                                                                                        |
| ------------------ | -------- | ---------------------------------------------------------------------------------------------- |
| `name`             | yes      | Lowercase hyphenated name; must match directory                                                |
| `title`            | no       | Human-readable heading; derived from `name` when omitted                                       |
| `format_version`   | yes      | Integer source-format version; the current compiler supports format 1                          |
| `version`          | yes      | Non-empty skill version; emitted in `SKILL.md` metadata but not used for dependency resolution |
| `license`          | no       | Non-empty license name or bundled license-file reference                                       |
| `copyright`        | no       | Non-empty copyright notice                                                                     |
| `description`      | yes      | Runtime selection description, at most 1024 characters                                         |
| `primary_workflow` | yes      | ID of a workflow in this skill                                                                 |
| `entry_kinds`      | no       | List of non-empty strings for author-facing inventory; does not restrict supported kinds       |
| `content`          | no       | Entry, workflow, script, and asset globs                                                       |
| `profiles`         | no       | Profile directory and defaults                                                                 |
| `interface`        | yes      | Agent-facing display metadata                                                                  |

`dependencies` is not supported.

`content` accepts only `entries`, `workflows`, `scripts`, and `assets`;
unknown fields are errors. Each value is a list of non-empty glob strings.
Default patterns are `entries/*.yaml`, `workflows/*.yaml`, `scripts/**/*`, and
`assets/**/*`. Patterns must stay inside the skill directory. Scripts and
assets are copied into the output at the same relative path they have in the
skill source; ZIP output marks scripts executable.

`name` is 1–64 lowercase letters, digits, or single hyphens, must match its
directory name, and cannot be `all`.

### Profile configuration

The optional manifest `profiles` mapping accepts:

| Field       | Required | Meaning                                                                             |
| ----------- | -------- | ----------------------------------------------------------------------------------- |
| `directory` | no       | Profile directory relative to the skill root; defaults to `profiles`                |
| `defaults`  | no       | Profiles used when a build has no explicit `--profile`; defaults to an empty list   |

The profile directory must stay inside the skill source. Supplying any explicit
profile selector replaces `defaults` for that build; it does not add to them.
Every default name must identify a profile in the same skill.

### Interface configuration

The required manifest `interface` mapping accepts:

| Field               | Required | Meaning                                                         |
| ------------------- | -------- | --------------------------------------------------------------- |
| `display_name`      | yes      | Non-empty name displayed by the agent host                      |
| `short_description` | yes      | Interface summary, 25–64 characters                             |
| `default_prompt`    | yes      | Suggested invocation containing the exact `$<skill-name>` token |
| `brand_color`       | no       | Non-empty agent-interface color value                           |
| `icon`              | no       | Fallback source image for both icon roles                       |
| `icon_small`        | no       | Source image for the small role; overrides `icon`               |
| `icon_large`        | no       | Source image for the large role; overrides `icon`               |

Icon paths must be relative to the skill directory, but may resolve outside it
so several skills can reuse one source image. Builds convert populated roles to
self-contained PNG files under `assets/` and emit only the standard
`icon_small` and `icon_large` paths in `agents/openai.yaml`.

SVG and Pillow-supported raster inputs are accepted. Non-ICO images retain
their source dimensions; ICO inputs use their smallest frame for the small
role and largest frame for the large role. An icon source may be at most
10 MiB and 67,108,864 pixels (64 × 1024²). Invalid images, SVG `<script>` or
`<foreignObject>` elements, external SVG references, and external CSS URLs
are rejected.

## Entry schema

| Field         | Required | Type             | Meaning                                       |
| ------------- | -------- | ---------------- | --------------------------------------------- |
| `id`          | yes      | non-empty string | Unique entry identifier                       |
| `rule`        | yes      | non-empty string | The behavior the entry establishes            |
| `title`       | no       | string           | Generated reference heading; defaults to `id` |
| `kind`        | no       | string           | Entry kind; defaults to `rule`                |
| `priority`    | no       | integer          | Sort priority; defaults to `100`              |
| `rationale`   | no       | string           | Why the rule exists                           |
| `scope`       | no       | string           | Where or when the rule applies                |
| `constraint`  | no       | string           | A bound the rule must respect                 |
| `require`     | no       | list of strings  | Behaviors the entry requires                  |
| `allow`       | no       | list of strings  | Explicitly permitted behavior                 |
| `reject`      | no       | list of strings  | Disallowed behavior                           |
| `conditions`  | no       | list of strings  | Conditions that qualify application           |
| `exceptions`  | no       | list of strings  | Explicit exceptions                           |
| `examples`    | no       | list of strings  | Short examples that clarify application       |

`kind` is one of `principle`, `policy`, `heuristic`, `pattern`, `constraint`,
or `rule`. Entries render in ascending `(priority, kind, id)` order.
Generated filenames are derived from IDs and must not collide, including
case-insensitive collisions.

## Workflow schema

| Field         | Required | Type             | Meaning                                       |
| ------------- | -------- | ---------------- | ----------------------------------------------|
| `id`          | yes      | non-empty string | Unique workflow identifier                    |
| `steps`       | yes      | list             | Ordered string or mapping steps               |
| `title`       | no       | string           | Supporting-workflow heading; defaults to `id` |
| `description` | no       | string           | Purpose shown before the generated steps      |

A string step must be non-empty. A mapping step accepts only `id`, `action`,
`instruction`, `when`, and `use`, each as a non-empty string. It must define at
least one of `use`, `action`, `id`, or `instruction`. `use` may be combined
with `id` or `when`, but not with `action` or `instruction`, and must reference
a workflow ID in the same skill. Cross-skill and unknown references are
invalid.

## Profile schema

| Field           | Required | Type                      | Meaning                                       |
| --------------- | -------- | ------------------------- | --------------------------------------------- |
| `name`          | yes      | non-empty string          | Profile name; must match its `.yaml` filename |
| `label`         | yes      | non-empty string          | Heading in the generated profile reference    |
| `description`   | yes      | string, 1–1024 characters | Selection guidance shown from `SKILL.md`      |
| `instructions`  | yes      | non-empty list of strings | Profile-specific instructions                 |
| `details`       | no       | Markdown string           | Additional generated reference content        |
| `details_files` | no       | non-empty list of strings | Markdown files relative to the profile source |

`details` and `details_files` are mutually exclusive. Detail files must stay
inside the skill directory and must have a `.md` extension. Combined details
must not contain a level-one heading because Degardis supplies that heading.
Profile names use the same syntax as skill names and cannot be `all`.

## Python API

```python
from pathlib import Path

from degardis.build import SkillCompiler, build_skills
from degardis.validate import validate

compiler = SkillCompiler(Path("examples/structured-summary"))
paths = compiler.build(
    Path(".artifacts"),
    profiles=["detailed"],
)

errors = validate(Path("examples/structured-summary"))

zipped = build_skills(
    Path("examples/structured-summary"),
    Path(".artifacts"),
    as_zip=True,
)
```

### `SkillCompiler(sources)`

Creates a reusable compiler for one source path or a list of source paths.
Sources follow the same explicit-skill and collection discovery rules as the
CLI. Discovery occurs when the compiler is created.

### `SkillCompiler.build(output, profiles=None, as_zip=False)`

Builds every selected skill and returns a `list[pathlib.Path]` containing one
output path per skill. `profiles` is a list containing the same selectors
accepted by repeated CLI `--profile` options. `None` applies manifest defaults;
an explicit list, including an empty list, replaces those defaults.
`as_zip=True` returns paths to ZIP archives instead of bundle directories.
If the selected profiles produce a `SKILL.md` longer than the recommended
500-line maximum, the method emits `degardis.model.DegardisWarning` and
continues building.

As with the CLI, replacement is atomic per skill rather than across the whole
call. A failed replacement restores that skill's previous folder and ZIP, but
skills completed earlier in the call remain updated. Other entries in `output`
are preserved. The method rejects output that overlaps a selected source.
Python API paths are `pathlib.Path` values and are not automatically expanded
for `~` or environment variables.

### `build_skills(sources, output_dir, profiles=None, as_zip=False)`

Convenience function with the same build behavior and return value as
`SkillCompiler.build`. Use `SkillCompiler` when building the same selected
sources more than once; use `build_skills` for a single build.

### `validate(sources)`

Validates one source path or a list of source paths without writing output.
Returns an empty `list[str]` when valid or one or more human-readable error
messages when invalid:

```python
errors = validate(Path("examples/structured-summary"))
if errors:
    raise SystemExit("\n".join(errors))
```

Expected source, discovery, filesystem, and decoding failures are returned as
error strings. Unexpected exceptions from compiler logic propagate so an
internal defect is not misreported as invalid authored source.

`SkillCompiler` and `build_skills` raise
`degardis.model.DegardisError`—a `ValueError` subclass—for invalid source,
selection, or output relationships. Filesystem operations may raise their
original `OSError` subclasses.
