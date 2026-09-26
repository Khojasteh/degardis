### The interface

`interface` tells a host how to display and invoke the skill.

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  brand_color: '#5B4B8A'
  default_prompt: Use structured-summary to summarize this material.
```

| Field | Required | Rule |
| --- | --- | --- |
| `display_name` | yes | human-readable skill name |
| `short_description` | yes | host list text; 60 characters or fewer avoids a warning |
| `default_prompt` | yes | suggested invocation |
| `icon` | no | source image inside the skill directory |
| `brand_color` | no | six-digit hex color, for example `'#5B4B8A'` |

`default_prompt` should contain the skill's exact `name`, and a prompt that does not warns. Write the name with no host invocation prefix such as `$` or `/`: a prefixed name is an error, because Degardis adds each target's prefix.

Naming `interface.icon` ships the icon, so do not also select it under `content.assets`. SVG and raster sources are accepted. SVGs must be self-contained: no scripts, `foreignObject`, external references, or external CSS URLs. Internal fragments and inline `data:` images are allowed. Degardis does not rescale the image: an ICO uses its smallest image for the small role and largest for the large role; other sources supply the same rendered image to both roles.
