### Icons

`interface.icon` names one image, and a build renders it into the two icon
assets a host displays. Give the path relative to the skill directory:

```yaml
interface:
  icon: assets/logo.svg
```

A relative path is what makes one build behave like the next; an absolute path
names a file that exists on one machine only, and is reported. The path must
name a file that exists and that decodes as an image—an SVG whose markup parses,
or a raster format with usable dimensions.

| Limit | Value |
| --- | --- |
| Source file size | 10 MiB. |
| Source image size | 64 megapixels. |

An SVG icon is held to one more rule, because a host renders it where the
person browsing skills is looking. These are refused:

| Refused in an SVG icon | Why |
| --- | --- |
| A `script` element. | A bundle icon must execute nothing. |
| A `foreignObject` element. | It embeds content the renderer does not control. |
| An external `href`. | The icon would fetch something when it is displayed. |
| An external CSS `url()`. | The same, through a stylesheet. |

A reference that stays inside the file is fine: an `href` beginning with `#` or
with `data:image/`, and a CSS `url()` naming `#` or `data:`. Draw the icon as
self-contained markup, and convert any text to paths, because the renderer is
given no system fonts.

An icon is optional. A skill without one still builds, and the host shows it
under its `display_name`.
