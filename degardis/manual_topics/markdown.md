### How a source file is read

Every construct you write is one Markdown file, read under one rule:

> **The manifest selects its namespace. The filename is its id. The frontmatter
> holds its fields. The body is its content.**

So `tasks/review-draft.md` is the task whose id is `review-draft`, and
`knowledge/audience.md` is the knowledge unit whose id is `audience`.

A file opens with a frontmatter block on its first line, holding the construct's
fields, and everything after it is the content:

```markdown
---
kind: concept
title: What an audience changes
---

The reader's decision sets what belongs; their expertise sets only how it is worded.

Two properties of a reader matter, and they change different things. What the
reader has to decide sets the contents; what they already know sets the wording.
```

A file must open with `---` and close that frontmatter block before its body.

No source file states an `id`; the filename carries the name. To rename a
construct, rename its file.

### What happens to the body

The compiler does exactly three mechanical things to a body when it places it on
a page:

- **Heading levels shift.** A unit written as its own document becomes a section
  of a task page, so its top heading is re-levelled to sit under the heading the
  page gave it. The relative depth you wrote is preserved, and no heading text
  changes. Headings inside fenced code blocks are left alone.
- **Relative links are re-addressed.** Write a link the way your editor resolves
  it — relative to the file you are writing. The compiler resolves it against
  your file and re-expresses it from wherever the text lands. Link text never
  changes, and a target naming a scheme, a network path, or an anchor is left
  exactly as written.
- **A hard-wrapped paragraph is folded back into one line.** Wrap your prose at
  whatever column suits you. Only running prose folds: code blocks, tables,
  headings, list markers, and link definitions keep every line where you put it,
  and a break you asked for — a line ending in two spaces, or in a backslash —
  stays.

The compiler also groups whole knowledge units by kind. It does not edit or
reorder text inside a unit, and it preserves author order among units of the
same kind.

### Inline references

Write `[[kind:target]]` anywhere in Markdown prose to link to another file the
bundle carries. The compiler supplies the Markdown target and uses the target's
title for Markdown or its filename for another file:

```markdown
Read [[task:review]], [[principle:evidence]], and [[profile:python]].
Use [[guide:checklist]], [[asset:template.docx]], or
[[script:check.py]] when they apply.
```

`task`, `principle`, `guide`, and `profile` take their bare ids. `asset`,
and `script` take paths relative to their own `assets/` and `scripts/` folders.

Tokens in frontmatter, inline code, fenced code, indented code, and another
Markdown link's label or destination stay literal.
A token must name a known, selected target.
