# Reference

Use this page to look up Degardis's current CLI, discovery rules, source
schemas, and Python API. For a first build, follow
[Getting started](getting-started.md); for a guided source example, use
[Authoring skills](authoring-guide.md).

## CLI

Degardis has five commands. `build` is the only one that creates or replaces
anything; the others read source and report. Each section below opens with the
reader the command is written for.

### Paths

`list`, `validate`, `agent`, and `build` each take one or more paths. Each path
may name a skill directory or a collection directory; see
[Discovery](#discovery). These paths expand `~` and environment variables, and a
relative path is resolved from the current working directory.

`explain` is the exception. It takes check codes instead of paths and reads no
source at all.

### Exit status

Reports and build paths go to standard output. Warnings and `[ERROR]` messages
go to standard error.

| Status | Meaning |
| --- | --- |
| 0 | The command completed. |
| 1 | Invalid source, selection, path, or filesystem operation. Degardis reports the problem without a Python traceback. |
| 2 | Invalid command syntax. The command prints its usage. |

### `degardis list PATH [PATH ...]`

For a person surveying what is on disk. Creates nothing.

Lists each selected skill's title, manifest name, version, description,
available profiles, whether it includes scripts, license, copyright, and
absolute source path. Missing optional legal metadata is reported as
`Not specified`; a skill with no profiles reports `None`. It does not validate
the full source, execute scripts, or create output.

### `degardis validate PATH [PATH ...]`

For a person or a CI job asking whether a skill passes. Creates nothing.

Checks discovery, manifests, entries, workflows, profiles, generated
artifact-path collisions, and generated links for the selected skills. It
creates no artifact and does not run bundled scripts.

One run reports every problem it can reach. Validation does not stop at the
first problem, either inside a file or across files, so you can repair a whole
skill from a single report.

A problem that still builds is reported as a warning rather than an error.
Warnings cover, among others:

- unrecognized fields in the manifest, `interface`, `content`, entries,
  workflows, workflow steps, and profiles;
- YAML values that can load as something other than the text you wrote;
- an omitted field whose default changes the built bundle, such as an entry
  `title` or `priority` (see
  [Optional fields that carry a behavioral default](#optional-fields-that-carry-a-behavioral-default));
- a workflow that ships but that no `use` chain reaches.

For the full list of codes this version can report, see
[`degardis explain`](#degardis-explain-code-code-).

The report marks each skill as a pass or a failure and lists its messages
below it. Each message ends with the check that reported it, in parentheses:

```text
Validation

[PASS] Alpha (alpha)
       Warning: <skill-path>/entries/rule-one.yaml:
                unrecognized entry fields ignored: bogus_field (entry.unknown-field)

Summary: 1 passed, 0 failed, 0 errors, 1 warning, 1 total.
Run `degardis explain CODE [CODE ...]` for the checks behind the codes above.
```

Paths in the report are absolute; `<skill-path>` stands in for one here. A
message carries a line number as well when the check knows one.

Pass the codes to [`degardis explain`](#degardis-explain-code-code-), together
or one at a time, to learn why those checks matter. The final summary counts
passed, failed, and total skills, plus any errors and warnings.

Status is 0 when every skill passes, and 1 when any skill fails.

### `degardis agent PATH [PATH ...]`

For an AI agent that needs everything about a skill at once. Creates nothing.

Reports everything an agent needs to review, repair, and budget the selected
skills, with every error and warning aggregated in one run. It creates no
output artifact and executes no bundled script.

Its reader pays for every token, so the output is line-oriented and terse:

- identifiers omit the skill-name prefix, which the header states once;
- paths are relative to the root named in the header;
- sizes are the bytes of the *generated* Markdown, which is what an agent
  loads;
- nothing is wrapped into prose, and listed rows are aligned into columns.

The layout is stable: a release may add a section, a check code, or an entry
kind, but does not change the shape of a line an earlier release printed.
`degardis agent -h` documents the shape of every line the report can print, for
the agents that consume it.

The report is not written for a person. To read one yourself, `list` shows a
skill's metadata in readable form and `validate` gives the pass or fail.

Options:

- `--only DIMENSION[,DIMENSION...]`: report the named sections instead of the
  default set. Repeat the option or comma-separate names to combine them.
- `--all`: report every section.
- `--profile [SKILL:]PROFILE`: measure and inventory the bundle this profile
  selection would build, using the same selector grammar and the same errors as
  `build`. Without it, the report describes a bundle with no profile, exactly as
  an unqualified `build` produces one.
- `--baseline REF`: also measure each selected skill as the git revision `REF`
  has it, and report the difference in the `budget` section. See
  [Comparing against a revision](#comparing-against-a-revision).

Sections, in the order they are rendered. Every skill block opens with `skill`,
whatever the selection, so multi-skill output stays unambiguous:

| Section | Default | Reports |
| --- | --- | --- |
| `skill` | yes | name, version, title, root, id namespace, description length, primary workflow, and content counts |
| `identity` | | the full description, license, and copyright |
| `budget` | yes | the generated `SKILL.md` size for the selected profiles, and the on-demand weight of entries, supporting workflows, and selected profiles |
| `workflows` | yes | each workflow, marked `primary` for the primary workflow, with the step that reaches a supporting one, or `unreached` |
| `entries` | | each entry's local id, kind, priority, source path, and generated size |
| `profiles` | | each profile's name, whether the selection includes it, source path, and generated size |
| `scripts`, `assets` | | selected source paths and sizes |
| `outputs` | | every file a build would write, with its size and permission bits |
| `diagnostics` | yes | aggregated errors and warnings |

The `skill` section reports how long the description is. The `identity` section
reports the description itself, and replaces the length line when both sections
are selected.

`outputs` and `budget` describe the bundle the current `--profile` selection
would produce, so both agree with `build` under the same selector without
anything being written to disk.

The `budget` section measures the whole generated `SKILL.md` and, separately, its
body without the YAML frontmatter — the prompt itself.

#### Comparing against a revision

`--baseline REF` measures each selected skill twice, once as your working copy
has it and once as the git revision `REF` has it, and reports the difference.

```console
degardis agent path/to/skill --only budget --baseline HEAD
```

```text
body  SKILL.md 1524B 50L | text 1285B 40L 164w | profiles none
refs  entries 1099B | workflows 492B | profiles 0B
base  HEAD SKILL.md 1524B 50L | text 1285B 40L 164w | entries 1043B | workflows 492B | profiles 0B
delta SKILL.md +0B +0L | text +0B +0L +0w | entries +56B | workflows +0B | profiles +0B
```

`base` repeats the sizes from `body` and `refs`, in that order, as `REF` has
them. `delta` gives your copy minus `REF`, and every number carries a sign, so a
size that did not change reads `+0`. The run above is an edit that added 56 bytes
to an entry and nothing to the always-loaded `SKILL.md`.

`--profile` applies to both sides, and the two can disagree. Where `REF` has no
profile the selector matches, nothing is selected there, so the `delta` carries
the whole cost of a profile added since — both the bytes it puts in `SKILL.md` and
its own reference weight. A selector matching nothing in your working copy is an
error, exactly as it is for `build`.

`REF` is anything `git rev-parse` accepts: `HEAD`, `HEAD~3`, a branch, a tag, or
a commit id. Degardis reads the revision without checking it out, so your working
tree, index, and stash are left as they are, and measuring an edit never requires
stashing it or switching branches first.

Where there is nothing to compare against, `base` says so and no `delta`
follows:

| Reported | Meaning |
| --- | --- |
| `absent` | `REF` has no skill at that path, as for a skill added or renamed since |
| `unmeasured` | `REF` has the skill, but no `SKILL.md` can be generated from it |

Errors and warnings in `REF` are not reported and do not affect the exit status,
which continues to reflect only the skills you selected. `--baseline` needs
`budget` among the selected sections and reports an error when `--only` leaves it
out.

Diagnostics use one fixed line shape, so an agent can locate a finding without
parsing prose:

```
error <path>[:<line>] <code> <message>
warn  <path>[:<line>] <code> <message>
```

`<path>` is relative to the skill root, or `-` when the diagnostic concerns the
skill as a whole rather than a file. `<line>` appears only where the check
knows one.

`<code>` names the check, not its wording. Every code reads as
`<namespace>.<check>`. The namespace is the construct the check concerns:
`manifest`, `interface`, `content`, `entry`, `workflow`, `profile`, `output`,
`yaml`, `icon`, or `source`. The check is written as hyphenated words, with one
exception: where it names a field of the source, it spells that field exactly as
the key does. The check for a missing `short_description` is therefore
`interface.missing-short_description`, keeping the underscore of the key. If you
know the key, you can write the code without looking it up. Pass any reported
code to [`degardis explain`](#degardis-explain-code-code-) for the check behind
it.

`agent` exits with status 0 when no errors are found and status 1 when any
selected skill has one or more errors, whichever sections were selected.

### `degardis explain CODE [CODE ...]`

For a person or agent holding a diagnostic code. Reads no skill source and
creates nothing.

Explains each code given: what triggers the check, why it matters, and a failing
and a passing example of the source it concerns.

```console
degardis explain yaml.altered-scalar
degardis explain entry.missing-priority entry.missing-title workflow.unreachable
```

Give as many codes as you like. A report usually names several, and one run
explains all of them, so an agent repairing a skill needs one call rather than
one per code. Codes are explained in the order given, separated by a blank line,
and each block opens with its code on a line of its own. A code repeated in the
same run is explained once.

Every code any check can report has an entry. An unrecognized code exits with
status 1 and lists every code this version knows, grouped by namespace. You
therefore need no separate index to find the codes. When a run mixes known and
unknown codes, the known ones are still explained on standard output, and the
unknown ones are named together on standard error.

Each entry is written by hand for the person or agent reading it, not derived
from the check itself. It states what a one-line message cannot: what goes
wrong in the built bundle when the check fires, and what corrected source looks
like.

### `degardis build PATH [PATH ...] --output PATH`

Produces the installable bundle. This is the only command that writes files.

Builds one uncompressed skill folder per selected skill by default, or one
`.zip` archive per skill with `--zip`.

Options:

- `--output PATH`: required output root.
- `--zip`: write a `.zip` archive per skill instead of an uncompressed folder.
- `--profile PROFILE`: include a match in every selected skill.
- `--profile SKILL:PROFILE`: include one selected skill's profile.
- `--profile all`: include every selected skill's profiles.
- `--profile SKILL:all`: include every profile owned by one selected skill.

You may repeat `--profile`. Four rules govern how selectors resolve:

- A build that supplies no selector includes no profile. Nothing in the
  manifest adds one; only `--profile` does.
- An unqualified selector that several selected skills define includes that
  profile in each of them.
- A named selector that matches no selected skill is an error.
- `--profile all` stays valid when the selected skills define no profiles. It
  then builds them without adding any profile.

An uncompressed build installs the selected skills directly when `--output` is
an agent's project or personal skill directory, such as `.agents/skills`,
`.claude/skills`, `~/.agents/skills`, or `~/.claude/skills`. Degardis creates
one `<skill-name>/` child inside that directory. A ZIP file placed in such a
directory is not an installed skill; `--zip` instead produces archives ready to
upload to ChatGPT.

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
output path is resolved from the current working directory.

On success, the command reports each skill with the absolute path of its
generated folder or archive and the measurements of its generated `SKILL.md`,
then closes with a summary. The measurement gives total bytes and lines first,
then the body bytes, lines, and words, which exclude the frontmatter. It
reflects the profiles this build included, so it matches what `degardis agent`
reports for the same `--profile` selection.

Generated text is written with `\n` line endings on every platform, so the same
source produces the same bundle bytes wherever it is built.

## Discovery

A path that contains `skill.yaml` selects that skill. Any other path is treated
as a collection: Degardis searches it recursively and selects every descendant
directory that contains `skill.yaml`. Once discovery finds a skill directory, it
does not search inside that skill for more skills.

Degardis ignores a duplicate path, but rejects the same skill name found at two
different paths. A missing path, a path that is not a directory, and a directory
with no skills below it are each an error.

Degardis commands read source, never generated output. A directory that holds a
root `SKILL.md` and no `skill.yaml` is a built bundle. Degardis refuses such a
directory, a collection that contains one, and a `.zip` archive, and the error
says which one it found.

This check matters because a bundle may ship a Markdown template as an asset.
Without the check, discovery would continue into the bundle, treat that
template as a skill, and report a pass for a skill you never named.

## `skill.yaml`

| Field              | Required | Meaning                                                                                        |
| ------------------ | -------- | ---------------------------------------------------------------------------------------------- |
| `name`             | yes      | Lowercase hyphenated name; must match directory                                                |
| `title`            | no       | Human-readable heading; derived from `name` when omitted                                       |
| `format_version`   | yes      | Integer source-format version; `degardis -h` names the versions this compiler accepts           |
| `version`          | yes      | Non-empty skill version; emitted in `SKILL.md` metadata but not used for dependency resolution |
| `license`          | no       | Non-empty license name or bundled license-file reference                                       |
| `copyright`        | no       | Non-empty copyright notice                                                                     |
| `description`      | yes      | Runtime selection description, at most 1024 characters                                         |
| `primary_workflow` | yes      | ID of a workflow in this skill                                                                 |
| `content`          | yes      | Globs that select the entry, workflow, profile, script, and asset files the skill ships        |
| `interface`        | yes      | Agent-facing display metadata                                                                  |

Unlisted skill fields are ignored with a warning.

`name` is 1–64 lowercase letters, digits, or single hyphens, must match its
directory name, and cannot be `all`.

`format_version` says which source contract your manifest is written to, and
which versions are accepted is a property of the compiler you have installed
rather than of your source. Run `degardis -h` to see them; it names them in the
epilog beside the examples, and that announcement is authoritative where it and
this page could differ. Declaring a version it does not name fails `validate`,
`agent`, and `build` with `manifest.unsupported-format_version`.

A compiler can accept more than one version. A release that introduces a new
source format keeps accepting the formats before it, so source that builds today
keeps building after an upgrade. Declare the newest version the announcement
names in new source, and leave an existing manifest on the version it already
declares until you have a reason to move it.

### Content configuration

`content` says which files the skill ships. It has five keys:

| Key         | Selects                                              |
| ----------- | ---------------------------------------------------- |
| `entries`   | entry sources, written in YAML                       |
| `workflows` | workflow sources, written in YAML                    |
| `profiles`  | profile sources, written in YAML                     |
| `scripts`   | executable helpers, copied into the bundle unchanged |
| `assets`    | supporting files, copied into the bundle unchanged   |

Each key takes a list of glob patterns, and each pattern must be a non-empty
string. Any other `content` key is ignored, with a warning.

No key has a default. A key you leave out means the skill ships no content of
that kind, and Degardis looks for none. Nothing is included because it happens
to sit in a directory with a familiar name; the manifest alone decides.

Every skill therefore needs at least `workflows`. Without it, no workflow is
loaded, the primary workflow cannot be found, and validation fails.

Two mistakes leave content out of the bundle without the bundle showing it, so
Degardis reports both as errors:

- a pattern that matches nothing in the skill directory, an exclusion included
  (`content.unmatched-pattern`);
- a key you declared that selects no file in the end, for example because an
  exclusion removed everything it selected (`content.empty-selection`).

A pattern cannot point outside the skill directory. Degardis copies each
selected script and asset to the same relative path in the output. In ZIP
output, scripts are marked executable.

`profiles` must select profile sources only. A profile's Markdown detail files
are not profile sources: the profile names them in `details_files`, and a
pattern that also matches them, such as `profiles/**/*`, fails. Write
`profiles/*.yaml` instead.

#### How patterns are matched

Patterns use `/` as their only separator, on every platform. Names are compared
exactly, upper and lower case included, even on Windows and macOS, where the
filesystem itself ignores case. If the directory is named `entries`, the pattern
`Entries/*.yaml` matches nothing and is reported as
`content.unmatched-pattern`. The same source therefore selects the same files on
every computer.

Within one name, `*` matches any run of characters and `?` matches one. As a
whole segment, `**` matches any number of directories, including none, so
`assets/**/*` selects everything under `assets/` at any depth. `**` does not
descend into a symbolic link, so a link pointing back at one of its own parent
directories cannot make matching run forever.

Start a pattern with `!` to exclude the files it matches. Degardis reads a list
from top to bottom. An exclusion drops the files that the patterns above it
selected, and a pattern below the exclusion can select a file again:

```yaml
content:
  assets:
  - assets/**/*
  - "!assets/drafts/**/*"
  - assets/drafts/keep.md
```

Always put quotes around a pattern that starts with `!`. Without them, YAML
treats it as a tag, and the manifest does not load.

An exclusion that matches a directory drops every selected file inside it. This
is why `!assets/drafts` and `!assets/drafts/**` do the same thing.

An exclusion matches from the skill directory downwards, like every other
pattern. To exclude a file at any depth, write `!assets/**/*.tmp`, not `!*.tmp`.

Degardis excludes two kinds of path on its own: anything hidden, and anything
inside a directory whose name starts with a dot. A dot on a file's own name does
not count, so `assets/**/*` still selects `assets/.gitignore`.

To include something Degardis excluded this way, name that file or directory in
the pattern instead of matching it with a wildcard:

```yaml
content:
  assets:
  - assets/**/*       # by design, skips assets/.vscode/
  - assets/.vscode/*  # selects it again
```

No pattern selects these files, and naming them explicitly does not change that:

- Python bytecode, which Python generates from the skill's own scripts.
- The files an operating system creates for itself, such as a thumbnail cache
  or a folder setting.

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

Unlisted `interface` fields are ignored with a warning.

Icon paths must be relative to the skill directory, but may resolve outside it
so several skills can reuse one source image. Builds convert populated roles
to self-contained PNG files under `assets/` and emit only the standard
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

Unlisted entry fields are ignored with a warning.

The kinds this compiler knows are `principle`, `policy`, `heuristic`,
`pattern`, `constraint`, and `rule`. This list is not closed. A kind outside it
produces a warning rather than an error, and the entry still compiles with the
kind it declares, so source written for a later compiler also builds on this
one. An empty or non-string `kind` is an error.

Entries render in ascending `(priority, kind, id)` order. `priority` has no
required range and need not be unique; only the relative order matters.

Two ordering cases produce a warning, because in both the compiler chooses the
order instead of the author:

- An omitted `priority` defaults to `100`. Any smaller value an author chose
  sorts above it, so the entry lands last.
- Entries that share a priority fall back to a sort by kind, then by id.

Generated filenames are derived from IDs and must not collide, including
case-insensitive collisions.

### Optional fields that carry a behavioral default

Most optional fields simply omit output when absent. These change what the
build produces, so leaving one out is reported as a warning naming the default
that was substituted:

| Field | Default when omitted |
| --- | --- |
| entry `title` | the entry `id`, which is what the always-loaded reference index then shows |
| entry `kind` | `rule`, which changes the generated filename, the sort order, and the recorded kind |
| entry `priority` | `100`, sorting the entry below every authored priority |
| workflow `title` | the workflow `id`, used as the link text in the supporting-workflow index |
| primary workflow `description` | nothing, leaving the generated body with no statement of what the skill does |
| a step's `instruction` | nothing, rendering the step as a heading alone; `use` steps are exempt |

The manifest `title` is the exception: its default is derived from `name` and
is usually correct, so it is not warned about. `degardis agent` marks it as
derived instead.

## Workflow schema

| Field         | Required | Type             | Meaning                                       |
| ------------- | -------- | ---------------- | ----------------------------------------------|
| `id`          | yes      | non-empty string | Unique workflow identifier                    |
| `steps`       | yes      | list             | Ordered string or mapping steps               |
| `title`       | no       | string           | Supporting-workflow heading; defaults to `id` |
| `description` | no       | string           | Purpose shown before the generated steps      |

Unlisted workflow fields are ignored with a warning.

A string step must be non-empty. A mapping step accepts `id`, `action`,
`instruction`, `when`, and `use`, each as a non-empty string.

Unlisted step fields are ignored with a warning.

A step must define at least one of `use`, `action`, `id`, or `instruction`.
`use` may be combined with `id` or `when`, but not with `action` or
`instruction`, and must reference a workflow ID in the same skill. Cross-skill
and unknown references are invalid.

A workflow that no chain of `use` steps reaches from the primary workflow is
reported as a warning. It still builds and still appears in the generated
supporting-workflow index, but nothing invokes it.

## Profile schema

Degardis finds profile sources through `content.profiles`, in the same way it
finds every other kind of content. A skill whose manifest has no
`content.profiles` key has no profiles.

Profiles are the one kind of content a bundle does not have to carry. A build
includes only the profiles its `--profile` selectors name, and includes none
when you name none. The manifest says which profiles exist; the build command
says which of them ship.

| Field           | Required | Type                      | Meaning                                       |
| --------------- | -------- | ------------------------- | --------------------------------------------- |
| `name`          | yes      | non-empty string          | Profile name; must match its `.yaml` filename |
| `label`         | yes      | non-empty string          | Heading in the generated profile reference    |
| `description`   | yes      | string, 1–1024 characters | Selection guidance shown from `SKILL.md`      |
| `instructions`  | yes      | non-empty list of strings | Profile-specific instructions                 |
| `details`       | no       | Markdown string           | Additional generated reference content        |
| `details_files` | no       | non-empty list of strings | Markdown files relative to the profile source |

Unlisted profile fields are ignored with a warning.

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
accepted by repeated CLI `--profile` options. `None` and an empty list both
build without any profile. `as_zip=True` returns paths to ZIP archives instead
of bundle directories.

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
