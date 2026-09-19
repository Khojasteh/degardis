### The interface

`interface` tells a host how to display and invoke the skill.

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  brand_color: '#5B4B8A'
  default_prompt: Use {name} to summarize this material.
```

| Field | Required | What it is |
| --- | --- | --- |
| `display_name` | yes | the skill's human-readable name; heads the generated `SKILL.md` |
| `short_description` | yes | what a host shows in a list, about 60 characters |
| `default_prompt` | yes | the invocation a host offers |
| `icon` | no | an SVG, or a raster image such as PNG or ICO, inside the skill directory |
| `brand_color` | no | a six-digit hex colour such as `'#5B4B8A'` |

### The invocation placeholder

Write `{name}` where the skill invocation belongs, and the compiler renders it
in the host's own invocation syntax:

```yaml
default_prompt: Use {name} to summarize this material.
```

A prompt that spells a host prefix literally, such as `$summarize` or
`/summarize`, is refused: it would reach every other host verbatim. A prompt
that names no skill at all is reported as a warning.

### Icons

`interface.icon` names an image inside the source: an SVG, or a raster image
such as PNG or ICO. Naming it here is what ships it, so do not select the icon
under `content`.

The compiler converts that image to PNG for the small and large roles a host
asks for, and ships both. Nothing is rescaled: an ICO carrying several sizes
gives its smallest image to the small role and its largest to the large one, and
any other source gives the same image to both.

An SVG has to be self-contained, because what ships is the PNG the compiler
rendered from it. A `script` or `foreignObject` element, an `href` that is
neither an internal `#` fragment nor an inline `data:` image, and a CSS `url()`
pointing outside the file are each refused: the first two describe behaviour a
rasterizer never runs, and the rest would make the rendered icon depend on a
file or a network the build cannot promise. A raster source too large to convert
is refused as well.
