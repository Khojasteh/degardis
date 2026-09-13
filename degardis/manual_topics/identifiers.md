### Names and references

A construct id is its file stem and must contain lowercase letters, digits, and single hyphens: `review-draft`, `source-material`.

Ids are unique within a namespace, including across subdirectories. All knowledge kinds share the `knowledge` namespace; different construct namespaces may reuse the same id.

Reference fields that already name a namespace use bare ids:

```yaml
principles:
- evidence
knowledge:
- source-material
```

Knowledge dependencies use the same form:

```yaml
requires:
- audience
```

Every id in a reference list must name selected content and may appear only once in that list.
