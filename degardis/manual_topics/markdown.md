### How a source file is read

Every construct you write is one Markdown file — `.md` or `.markdown` — read
under one rule:

> **The manifest selects its namespace. The file stem is its id. Frontmatter
> holds its fields. The body is its content.**

So `tasks/review-draft.md` is the task whose id is `review-draft`, and
`knowledge/audience.md` is the knowledge unit whose id is `audience`.

A file begins with frontmatter; everything after it is the body:

```markdown
---
kind: concept
title: What an audience changes
---

The reader's decision sets what belongs; their expertise sets only how it is worded.

Two properties of a reader matter, and they change different things. What the
reader has to decide sets the contents; what they already know sets the wording.
```

The opening `---` must be the first line, with a closing `---` before the body.
No source file declares `id`; rename the file to rename the construct.

Frontmatter holds the fields its construct's schema defines, and an unrecognized
field is reported as a warning, so the construct still compiles. Metadata another
tool owns goes in an `x-` field, such as `x-owner`: Degardis parses its value as
YAML and otherwise ignores it.

### What happens to the body

The compiler makes three mechanical changes when placing a body:

- **Heading levels shift.** The body becomes a section while preserving relative
  depth and heading text. Fenced code is unchanged.
- **Relative links are re-addressed.** Write a link the way your editor resolves
  it from the source file. The compiler rewrites its target from the generated
  page. Schemes, network paths, anchors, and link text are unchanged.
- **A hard-wrapped paragraph is folded back into one line.** Wrap your prose at
  any column. Code, tables, headings, lists, link definitions, and explicit line
  breaks keep their lines.

Text within a construct is never reordered.

### Inline references

Write `[[kind:target]]` in prose to link to a selected file. The link text is a
Markdown construct's title or another file's name:

```markdown
Read [[task:review]], [[principle:evidence]], and [[facet:python]].
Use [[guide:checklist]], [[asset:template.docx]], or
[[script:check.py]] when they apply.
```

`task`, `principle`, `guide`, and `facet` take bare ids. `asset` and `script`
take paths relative to their `assets/` and `scripts/` roots.

Tokens in frontmatter, code, or another link stay literal. A reference must name
a selected target.
