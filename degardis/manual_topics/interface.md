### The interface

`interface` tells a host how to display and invoke the skill.

```yaml
interface:
  display_name: Structured Summary
  short_description: Turn material into a clear summary
  icon: assets/icon.svg
  default_prompt: Use structured-summary to summarize this material.
```

- `display_name` (required) — human-readable skill name; 64 characters max.
- `short_description` (required) — host list text; 64 characters max.
- `default_prompt` (required) — starting prompt a host inserts when a user invokes the skill; 1,024 characters max.
- `icon` (optional) — path of the skill's icon image inside the skill directory.

`default_prompt` should contain the skill's exact `name`. Write the name with no host invocation prefix such as `$` or `/`: a prefixed name is an error, because Degardis adds each target's prefix.

`interface.icon` selects the icon, which ships whether or not a `content.assets` pattern also matches it. The file must be an SVG, PNG, JPEG, or WebP image named by that suffix, and a raster file must be the image its suffix states. SVGs must be self-contained: no scripts, `foreignObject`, external references, or external CSS URLs. Internal fragments and inline `data:` images are allowed. The file may be at most 10 MiB and its image at most 67,108,864 pixels. Degardis does not rescale or convert the image, and one image serves every size a host shows.
