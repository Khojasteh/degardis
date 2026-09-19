### Assets

`content.assets` selects files a skill ships for any purpose other than running
them as scripts or opening them as guides. The compiler copies every asset byte
for byte.

This includes Markdown files: a `.md` asset remains an asset. Its frontmatter,
links, and text are not treated as a page or rewritten.

Link to an asset from authored Markdown where an agent needs it:

```markdown
Use [[asset:template.docx]] for the final document.
```

The inline target is relative to the `assets/` root. A selected asset that no
authored Markdown links to is reported as a warning, as an unreached script is.

The interface icon is the exception: `interface.icon` names it and the compiler
renders it into the bundle, so it does not need selecting.
