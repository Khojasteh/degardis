### YAML the compiler accepts

`skill.yaml` and construct frontmatter accept mappings, lists, strings, integers, finite numbers, booleans, and null.

The following are refused:

| Form | Why |
| --- | --- |
| anchors/aliases (`&x`, `*x`) | node reuse |
| merge keys (`<<:`) | imported fields |
| explicit tags (`!!tag`) | unsupported types |
| bare dates | timestamp values |
| `.inf`, `.nan` | non-finite numbers |
| repeated fields | ambiguous value |
| non-string field names | field names must be text |

Field names are always text, so a key such as `on` remains the string `on`.

Values such as `yes`, `no`, `on`, `off`, `08`, `1.50`, or `1:30` are accepted with YAML semantics but warned because authors often intend text. Quote them to force strings.

Each manifest or frontmatter block must parse to a mapping.
