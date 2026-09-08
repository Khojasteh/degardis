### Content selection

`content` is the skill's packing list. It accepts these keys. Each value is a
non-empty list of file patterns. A file that is not selected here is not part of
the skill, however conventionally it is named or placed.

| Key | Selects |
| --- | --- |
| `policies` | Policy YAML files. |
| `rules` | Rule YAML files. |
| `protocols` | Protocol YAML files. |
| `patterns` | Pattern YAML files. |
| `heuristics` | Heuristic YAML files. |
| `guidance` | Guidance YAML files. |
| `records` | Record YAML files. |
| `workflows` | Workflow YAML files. |
| `profiles` | Profile YAML files. |
| `references` | Supporting Markdown files. |
| `scripts` | Executable helper files. |
| `assets` | Supporting files such as templates and media. |

Patterns use `/` on every platform and match filenames exactly, including case.

| Pattern | Meaning |
| --- | --- |
| `*` | Any characters within one path segment. |
| `?` | One character within a path segment. |
| `[abc]` | One character from the listed set. |
| `**` | Any number of directory segments, including none. |
| `!pattern` | Remove files selected by earlier patterns. Quote it in YAML. |

Patterns run from top to bottom. A pattern after an exclusion can add a file
back:

```yaml
content:
  assets:
  - assets/**/*
  - "!assets/drafts/**/*"
  - assets/drafts/keep.md
```

Four rules catch a mistake here before it becomes a bundle that is quietly
missing something.

- Every skill selects one or more workflows.
- Every pattern must match at least one file that exists.
- Every key you include must end up selecting at least one file, so an
  exclusion that removes everything an earlier pattern found is reported.
- A key must select files its reader can read. A Markdown guide swept into
  `workflows` by a broad pattern is reported rather than parsed.

Patterns cannot leave the skill directory. Wildcards skip hidden and system
content unless you name it directly. Python bytecode and common operating-system
metadata are never selected.

Selecting a file and using it are separate steps. A script or asset that no
workflow action names as a resource is reported, and so is a resource an action
names that no pattern selects.
