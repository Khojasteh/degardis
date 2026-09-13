### Names and references

An id is a file stem, and it is lowercase letters, digits, and single hyphens:
`review-draft`, `source-material`, `meeting-transcript`.

Ids are unique within a construct namespace, even in different subdirectories:
the stem is the identity and the path is not. A task and a knowledge unit may
share a stem, since they are different namespaces. Two knowledge units of
different kinds may not: kind is classification, not identity.

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

A reference must name a selected file in its namespace. A list must not name
the same id twice.
