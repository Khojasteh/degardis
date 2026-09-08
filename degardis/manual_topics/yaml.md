### YAML the compiler accepts

Sources use YAML mappings, lists, strings, integers, finite numbers, booleans,
and null.

Every string scalar must contain at least one non-whitespace character. This
includes strings nested in lists and mappings, such as commands, identifiers,
content patterns, references, and literal string values. Omit an optional field
instead of writing an empty string.

Use YAML comments for notes intended only for people maintaining the source.

Degardis reads a deliberately small part of YAML, so that what a file says is
what its reader sees. These constructions are refused outright:

| Rejected | Write instead |
| --- | --- |
| An anchor, an alias, or a merge key. | The value in full, in each place it belongs. |
| A type tag such as `!!str`. | A value whose plain spelling is already the type you mean. |
| The same field twice in one mapping. | One field, with the value you meant. |
| A non-string mapping field name. | A quoted string. |
| A bare date, which YAML reads as a timestamp. | The date quoted, such as `"2026-01-31"`. |
| A non-finite number. | A finite number, or text you quote. |

Other values are read as YAML reads them, which is not always as they look. A
plain scalar that changes meaning on load is warned about, so quote any text
that YAML could take for another type:

| Unquoted value | Loads as | Write |
| --- | --- | --- |
| `yes`, `no`, `on`, `off` | A boolean. Warned. | `"no"` |
| `1.10`, `007` | A number whose text does not survive: `1.1`, `7`. Warned. | `"1.10"` |
| `1:30` | A base-sixty number, not a clock time. Warned. | `"1:30"` |
| `true`, `false`, `null`, `~` | A boolean or nothing at all. | `"true"` |

```yaml
answer: "no"
version: "1.10"
duration: "1:30"
```

The last row is not warned about, because those spellings mean exactly what they
say wherever a boolean or an absent value belongs. Where text belongs, the field
is reported as invalid instead: `summary: true` reaches the reader as a boolean
rather than as the word, and a summary is required to be text.
