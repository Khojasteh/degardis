### Interface metadata

`interface` is what a host shows a person choosing between skills. The
top-level `description` is for an agent deciding whether the skill applies;
these fields are for the browsing human beside it.

| Field | Required | Meaning |
| --- | --- | --- |
| `display_name` | Yes | Human-readable name shown by a host. |
| `short_description` | Yes | Short host-facing summary, at most 60 characters. |
| `default_prompt` | Yes | Suggested invocation containing `{name}`. |
| `icon` | No | SVG or supported raster image used for bundle icons. |
| `brand_color` | No | Six-digit hexadecimal color, such as `'#5B4B8A'`. |

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  default_prompt: Use {name} to summarize this material.
  icon: assets/logo.svg
  brand_color: '#5B4B8A'
```

A host lists many skills at once and shows about sixty characters of each, so a
`short_description` past that limit is one the reader never finishes.

Write `{name}` in `default_prompt` exactly, and write it instead of one host's
own invocation syntax. Each target replaces the placeholder with the skill name
spelled the way that host expects, so a prompt that hardcodes `$my-skill` or
`/my-skill` is correct on one host and wrong on the next. A `default_prompt`
without the placeholder is reported, and so is one that spells a host prefix.

`brand_color` is six hexadecimal digits after a `#`, and YAML reads `#` as the
start of a comment, so quote it. [Icons](#icons) covers what `icon` accepts.
