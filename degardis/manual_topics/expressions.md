### Expressions

DExpr is the small expression language used by a branch case, a `when` or
`unless` condition, and an expression verification. It reads declared values and
nothing else: it runs no script, calls no tool, and changes nothing.

A reference names a namespace and then the value, with a dot for a record field
and brackets for a list position, as in `result.inspection.gaps[0]`.

| Written | Written by | Holds |
| --- | --- | --- |
| `input.<name>` | The caller. | An input to the current workflow. |
| `result.<name>` | An action's `produces`, or a call's `as`. | A value an earlier step produced. |
| `decision.<step-id>` | The `decide` step it names. | That step's choice, as an enum of its choice names. |
| `gate.<step-id>` | The `gate` step it names. | That gate's finding, as an enum of its state names. |
| `call.<step-id>` | The `use` step it names. | The outcome received, as an enum of the outcomes that step maps. |
| `state.<name>` | The protocol frame the reading hook belongs to. | That protocol's state data. |

Because each namespace has exactly one writer, the compiler can tell whether a
value exists yet. Reading a value some path to that point has not produced is
reported, and so is reading one the workflow never declares.

| Written | Meaning |
| --- | --- |
| `"text"`, `12`, `true`, `false`, `null` | Literals. |
| `["brief", "detailed"]` | A list literal; every item must be one type. |
| `==` `!=` `<` `<=` `>` `>=` | Comparison. |
| `in`, `not in` | Membership in a list. |
| `or`, then `and`, then `not` | Combination, loosest binding first. |
| `( )` | Grouping. |
| `exists(v)` | Whether an optional value is present. |
| `length(v)` | The length of a string or a list. |
| `contains(v, item)` | Whether text holds text, or a list holds an item. |

Write an enum member as a quoted string: `decision.choose-depth == "brief"`.
A bare word is read as the start of a value reference, so it does not parse.
A comparison does not chain; join two of them with `and` instead.

Types are checked before the skill ships. Comparing a string with an integer,
mixing types in one list literal, taking the `length` of something that has
none, testing a name that is not one of an enum's members, or writing a
non-boolean where a condition belongs is each reported.

The compiler warns when Boolean literals and operators make a condition or a
later branch case statically unreachable.

An optional value must be guarded by `exists` earlier in the same expression,
so that the guard short-circuits before anything reads the value:

```yaml
when: exists(result.inspection) and length(result.inspection.gaps) > 0
```
