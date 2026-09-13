### How knowledge reaches a page

Knowledge reaches a task in only two ways:

```yaml
# task frontmatter
knowledge:
- source-material
- order-findings
```

```yaml
# knowledge frontmatter
requires:
- audience
```

A task receives its direct knowledge plus all transitive `requires`. Direct units keep task order; required units follow in first-introduced order; grouping by knowledge kind happens afterward.

Prose creates no dependency. Requirement chains may not cycle. Selected knowledge that no task reaches warns and is omitted from generated task pages. A unit reached by several tasks is copied into each closure; inspection reports the resulting duplication cost.
