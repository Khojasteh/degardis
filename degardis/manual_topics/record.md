### Records

A record gives one result several named parts. Use it when later work needs to
read or pass individual parts instead of treating the whole result as one value.

| Field | Required | Meaning |
| --- | --- | --- |
| `fields` | Yes | Non-empty mapping of declared values. |
| `title` | No | Reader-facing record title. |

```yaml
title: Material inspection
fields:
  subjects:
    type: {list: string}
    description: The distinct subjects the material covers.
  gaps:
    type: {list: string}
    description: Missing context that limits the result.
```

Each field is an ordinary value declaration, so it names `type` or `record` and
may add a `description`. Field names follow the identifier spelling, and an
expression reads one with a dot: `result.inspection.gaps`.

Use a record where the parts are read separately. Where a result has only one
part, declare that type directly; where two results are never read together,
produce two values rather than one record holding both.
