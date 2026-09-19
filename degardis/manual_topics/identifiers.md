### Names and references

An id is a file stem containing lowercase letters, digits, and single hyphens:
`review-draft`, `source-material`, `meeting-transcript`.

Use a short verb-object task id or noun phrase. Omit articles and sentence
grammar: prefer `review-draft` to `perform-a-review-of-the-draft` and
`unverified-claim` to `a-claim-not-verified`. Do not encode directory,
placement, or activation; they may change without changing identity.

Ids are unique within a namespace, including across subdirectories. Different
namespaces may share an id; knowledge kinds may not, because they share the
`knowledge` namespace.

Every reference field names one namespace, so a reference is a bare id:

```yaml
principles:
- evidence
- reporting
knowledge:
- source-material
- cite-the-source
```

A knowledge unit uses the same form for dependencies:

```yaml
requires:
- audience
```

A reference must name a selected file in its namespace, and a list may name an
id only once.
