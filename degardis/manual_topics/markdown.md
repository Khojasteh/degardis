### How a source file is read

Each construct is one `.md` or `.markdown` file:

> The manifest selects its namespace. The file stem is its id. Frontmatter holds its fields. The body is its content.

```markdown
---
kind: concept
title: Audience
---

The audience determines what the result must explain.
```

Files are UTF-8; a leading byte-order mark is ignored. The opening `---` must be the first line and a closing `---` must precede the body. Do not declare `id`; rename the file to rename the construct.

Frontmatter accepts only fields defined for that construct. Unknown fields warn but still compile. Metadata owned by another tool may use `x-` fields such as `x-owner`; Degardis reads the YAML value and otherwise ignores it.

### Body handling

When authored Markdown is placed on a generated page, Degardis only:

- shifts heading levels while preserving relative depth and text;
- turns inline references into links;
- folds hard-wrapped prose paragraphs into one line.

Code, tables, lists, explicit line breaks, link definitions, authored links, and authored order are preserved.

### Inline references

Use `[[kind:target]]` in prose to link to selected content:

```markdown
Read [[task:review]], [[principle:evidence]], or [[facet:python]].
Use [[guide:checklist]], [[asset:template.docx]], or [[script:check.py]].
```

`task`, `principle`, `facet`, and `guide` targets are bare ids. An `asset` or `script` target is the file's source-relative path or any trailing part of it made of whole segments: `check.py` and `lint/check.py` both name `scripts/lint/check.py`. A target that ends more than one selected file of its kind is refused; write more of the path. Tokens inside frontmatter, code, or another Markdown link remain literal; indentation that places a line in a list is not code. Every target must be selected into the bundle. An inline reference to a principle or guide shows only its title; the page's activation still decides when it is read.

### Links

Link to bundle content only through inline references. A Markdown link or image, a reference definition, or an HTML `href` or `src` whose destination is a relative or absolute path is refused, because the text lands on a page in another directory. Links to external addresses, such as `https:` or `mailto:`, and anchors on the same page are kept as written. A link inside code is a sample and is not checked.
