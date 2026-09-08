### Selectors

Policies, rules, and protocol hooks use `match` to say exactly where a
requirement applies. A selector reads only metadata the source already
declares—never a title, a description, a command, or a filename—so what a
requirement constrains cannot drift as prose is reworded, and you can see from
the source which work you have selected.

```yaml
match:
  forms: [action, call]
  subjects: [summary.write, publication.*]
  effects: [workspace.write]
  calls: [report-gaps]
  outcomes: [delivered]
```

| Key | Matches |
| --- | --- |
| `forms` | `action`, `branch`, `decision`, `gate`, `call`, `pattern`, or `return`. |
| `subjects` | A step's `subjects` tags; `name.*` also matches `name` and anything under it. |
| `effects` | A step's `effects` tags; `name.*` also matches `name` and anything under it. |
| `calls` | `use` steps that call the named workflow. |
| `outcomes` | `return` steps that return the named outcome. |
| `all` | `{all: true}` by itself, selecting all work in scope. |

Entries within one key are alternatives, and every key you populate must match.
The selector above finds work that is an action or a call, *and* carries one of
those subjects, *and* writes the workspace, and so on. To widen a selector,
remove a key rather than adding entries to it.

Two form names differ from the step field that declares them: write `call` for a
`use` step and `decision` for a `decide` step. The selector names the kind of
node the compiler generates, and those two read better where a requirement is
enforced.

Selecting on tags is what makes a requirement independent of any one workflow: a
requirement that names tags keeps applying as steps are added, renamed, or
moved, where one naming step ids would not. [Subjects and effects](#subjects-and-effects)
covers the tags themselves.
