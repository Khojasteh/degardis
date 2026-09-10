## Declared values

Values carry information between steps. Declare them instead of asking an agent
to remember an earlier result: a declared value is one the compiler can check
is available, has the type its reader expects, and is actually read.

Workflow inputs, an action's produced values, record fields, pattern inputs, and
protocol state data all declare a value the same way. A declaration is a mapping
naming exactly one of `type` or `record`, with an optional `description`; an
action's produced values and protocol state data add an optional `default`:

```yaml
title:
  type: string
count:
  type: integer
depth:
  type: {enum: [brief, detailed]}
headings:
  type: {list: string}
formats:
  type: {list: {enum: [plain, markdown]}}
inspection:
  record: material-inspection
  description: What the material was found to contain.
optional-note:
  type: {optional: string}
```

`record: material-inspection` is the short form of `type: {record:
material-inspection}`; both say the same thing, and a produced value is usually
a record.

| Type | Written | Holds |
| --- | --- | --- |
| Scalar | `string`, `integer`, `number`, `boolean` | One value. |
| Enum | `{enum: [brief, detailed]}` | One of the names listed. |
| List | `{list: string}` | Any number of items of one type. |
| Record | `{record: material-inspection}` | The fields that record declares. |
| Optional | `{optional: string}` | That type, or nothing. |

An enum names one or more lowercase-hyphenated members and may not name one
twice. A list item may be any type except an optional one, so a list of records
is allowed and a list of possibly-absent items is not. An optional type cannot
wrap another optional type.

Choose the smallest type that says what you mean. A scalar where a reader needs
one fact; an enum where the choice is fixed and later work branches on it; a
record where several results travel together; an optional only where the value
genuinely may be absent, because every reader of an optional must guard it
first.

A value must be available on every path that reaches a reader of it. Where a
stage is optional—a branch runs it or skips it—the value that stage produces is
unavailable past the join, and reading it there is reported. Give the value a
`default` and it is available from the workflow's first step, holding what you
wrote until a step produces something else:

```yaml
address-compatibility:
  action: Name each consumer the change reaches and the control answering it.
  produces:
    compatibility-controls:
      type: {list: string}
      default: []
      description: Each consumer the screen named with its control, empty where
        the screen ruled compatibility out.
  next: join
```

Write the default rather than an extra step whose only job is to record the
empty case. The declaration is where the empty case belongs, beside the
description it has to agree with, and the generated workflow states it in every
one of its modules, so an agent that skipped the producing step reads the value
from the file it is already holding.

A `default` is a literal of the declared type. A list takes a list, an enum
takes one of its own members, and an empty list stands for any list, including a
list of records. An optional value takes no default, because it is already
absent where nothing produced it; a record takes none, because a record has no
literal form. Where two steps produce one value, either both declare the same
default or neither declares one.

A produced value and a protocol state field are the two declarations that take a
`default`, and it means the same thing at both: the value this holds before
anything wrote it. A state field's frame holds it from the moment the frame
opens. The other three declarations take none, because nothing about them can go
unwritten—a workflow input is always supplied by whatever entered the workflow,
and a record field and a pattern input travel with the value bound to them.
