### The interface

`interface` is how a host displays and invokes the skill — the one part of a
source written for a person choosing a skill rather than for the agent running
one.

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
| `icon` | no | an SVG, PNG, or ICO inside the skill directory |
| `brand_color` | no | a six-digit hex colour such as `'#5B4B8A'` |

A `short_description` should be about 60 characters or fewer.

### The invocation placeholder

Every host spells an invocation differently — `$name`, `/name`, `@name`. Write
`{name}` where the skill is named, and each target renders it in its own syntax:

```yaml
default_prompt: Use {name} to summarize this material.
```

A prompt must not spell one host's prefix literally, and should name the skill.

### Icons

`interface.icon` names an image inside the skill directory. The compiler renders
it into the sizes a host asks for and writes them into the bundle, so the icon
does not need selecting under `content`.

An SVG carrying script or external references is refused, and so is a raster
source too large to convert.
