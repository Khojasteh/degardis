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

Frontmatter accepts only fields defined for that construct. Unknown fields warn but still compile. Metadata owned by another tool may use `x-` fields such as `x-owner`; Degardis validates the YAML value and otherwise ignores it.

### Body handling

When authored Markdown is placed on a generated page, Degardis only:

- shifts heading levels while preserving relative depth and text;
- renders inline references as names or bundle paths;
- folds hard-wrapped prose paragraphs into one line.

Code, tables, lists, explicit line breaks, link definitions, authored links, and authored order are preserved.

Underlined headings shift too, and a shifted one is written with `#`. Markdown has no heading level below six, so a body whose headings would reach past it on its page warns; use fewer levels there.

### Inline references

Use `[[kind:target]]` in prose to reference selected content:

```markdown
Work through [[guide:checklist]] before release.
Fill in [[asset:template.docx]], then run [[script:check.py]].
```

`principle` and `guide` targets are bare ids. An `asset` or `script` target is the file's source-relative path or any trailing part of it made of whole segments: `check.py` and `lint/check.py` both name `scripts/lint/check.py`. A target that ends more than one selected file of its kind is refused; write more of the path. Tokens inside frontmatter, code, or another Markdown link remain literal; indentation that places a line in a list is not code. A `guide`, `asset`, or `script` target must be selected under its content key. A `principle` target must also be named in `skill.yaml`, because a principle the skill does not name gets no page. Any other kind is refused. Tasks and facets have no inline reference: send work to another task through a declared hand-off, and leave facet selection to the facet index.

A principle stands on its own, so its body may contain no inline reference of any kind; one is refused. Every other body may reference any kind. A guide referencing itself still renders but warns.

An `asset` or `script` reference renders as the file's bundle path in inline code, such as `scripts/check.py`. A `principle` reference renders as `principle:ID` in inline code and places nothing: `SKILL.md` lists every principle beside its conditions.

A `guide` reference renders as `guide:ID` in inline code and makes an owner of the guide: from a knowledge unit, every task whose page carries the unit; from a task, a facet, or a guide, that construct. The owner's page links the guide under **Guides**.

### Links

Refer to bundle content only through inline references. A Markdown link or image, a reference definition, or an HTML `href` or `src` whose destination is a relative or absolute path is refused, because the text lands on a page in another directory. Links to external addresses, such as `https:` or `mailto:`, and anchors on the same page are kept as written. A link inside code is a sample and is not checked.
