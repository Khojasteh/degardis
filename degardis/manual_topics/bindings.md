### Supplied values

Where one part of a skill hands a value to another, you supply a binding. A
binding is a mapping with exactly one of `from` and `literal`:

```yaml
inspection: {from: result.inspection}
depth: {from: decision.choose-depth}
limit: {literal: 1}
```

`from` says "use the value already available here" and takes a value reference.
`literal` says "use this written value" and takes a non-empty string, a number,
a boolean, or null—never a list or a mapping. The two forms are tagged rather
than guessed, so a literal string that happens to look like a value name is
still a literal.

Bindings appear wherever a declared value is filled in:

| Where | Fills |
| --- | --- |
| `with` on an [entrypoint](#entrypoints) | The entered workflow's inputs. |
| `with` on a `use` step | The called workflow's inputs. |
| `with` on a `pattern` step | The pattern's inputs. |
| `with` on a `return` | The fields of that outcome's record. |
| `set` on a protocol hook | The state data the hook writes. |

Four rules hold everywhere a binding is read. A supplied value must be one the
destination declares; every declared value the destination requires must be
supplied; the supplied type must stand where the destination expects one—not a
different scalar, not a possibly-absent value where one must be present, and not
a literal outside a declared enum; and a call outcome may be captured with `as`
only when that outcome carries a record.

An entrypoint's `with` is literal-only, because nothing has run when a route is
chosen and so there is no value for `from` to name.

A `default`—on a value an action produces, or on protocol state data—is not a
binding. It is the written value itself, so it takes a list where the type is a
list, and it never reads another value. [Declared values](#declared-values)
covers what one may be.

The reverse rule is easy to miss: a value that is produced or captured and never
read is reported. Reading means a declared `uses` on an action, gate, or decide
step, a binding, or an expression—prose mentioning the value does not count. If
a result is worth producing, name where it is read; if nothing reads it, drop
it. The same unused-value check covers workflow inputs, pattern inputs, and
protocol state data.
