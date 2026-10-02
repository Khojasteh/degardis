### YAML the compiler accepts

`skill.yaml` and construct frontmatter accept mappings, lists, strings, integers, finite numbers, booleans, and null.

The following are refused:

- anchors and aliases (`&x`, `*x`), which reuse nodes;
- merge keys (`<<:`), which import fields;
- explicit tags (`!!tag`), which name unsupported types;
- bare dates, which become timestamps;
- `.inf` and `.nan`, which are non-finite numbers;
- repeated fields, whose value would be ambiguous; and
- non-string field names, because field names must be text.

Field names are always text, so a key such as `on` remains the string `on`.

Values such as `yes`, `no`, `on`, `off`, `08`, `1.50`, or `1:30` are accepted with YAML semantics but warned because authors often intend text. Quote them to force strings.

Each manifest or frontmatter block must parse to a mapping.
