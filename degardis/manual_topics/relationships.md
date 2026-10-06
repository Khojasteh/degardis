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

A task page carries its direct knowledge plus all transitive `requires`. Direct units keep task order, and required units follow in the order requirements first introduce them; the page then groups units by kind, keeping this order within each kind.

Prose creates no dependency. Requirement chains may not cycle. Selected knowledge that no task reaches warns and is omitted from generated task pages. A unit reached by several tasks is copied into each closure; inspection reports the resulting duplication cost.

### How guides reach a page

A task or facet owns each guide its `guides` field names, a guide owns each guide its `requires` names, and each owns each guide its inline references make it own. Its page lists them at its foot, unconditional ones first; within each group, the guides it names come first, then those its inline references own, in the order its page first references them. Each guide is listed once, and never on its own page. Ownership does not pass along: a guide's requirements are listed on its page, not on its owners'. Guide requirement chains may not cycle.

### Conditions

Each `applicability` item is one condition, and the list applies when any of its items holds; conditions that must all hold belong in one item. An omitted list applies unconditionally. Items keep their authored order.

A hand-off's or guide's conditions appear beside its link, never on the target page. The agent reassesses conditions as the work changes and reads an applicable principle or guide before continuing the work it governs.
