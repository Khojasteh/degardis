### YAML the compiler accepts

`skill.yaml` and every frontmatter block are read under a narrow YAML profile:
mappings, lists, strings, integers, finite numbers, booleans, and null. Nothing
else.

Everything else YAML can do is refused at the line that wrote it:

| Refused | Form |
| --- | --- |
| `&anchor` and `*alias` | reuse of a node declared elsewhere |
| `<<:` merge keys | fields merged in from another mapping |
| `!!tag` type tags | an explicit type this format does not carry |
| a bare date | a value read as a timestamp rather than as text |
| `.inf`, `.nan` | a number that is not finite |
| a repeated field | the same field name given twice |
| a non-string field name | a field name that is not text |

A field name is always read as text, so a field spelled `on` is the field `on`
and not the boolean true.

Some values parse exactly as YAML says and still surprise their author. Those
keep their text and are warned about beside the line:

| Warned |
| --- |
| `yes`, `no`, `on`, `off` |
| `08`, `1.50` |
| `1:30` |

Quote the value to keep it as text.

A file must parse to a mapping of fields.
