### `action`

Use an action for ordinary work: read something, write something, run a helper,
or produce a result. It performs one thing and then continues.

| Field | Required | Meaning |
| --- | --- | --- |
| `action` | Yes | Complete instruction. |
| `next` | Yes | Next step identifier. |
| `uses` | No | Values the action reads. |
| `produces` | No | Mapping of values the action creates. |
| `resource` | No | One selected file operation. |

```yaml
inspect-material:
  action: Inspect the supplied material for its subjects and limitations.
  uses: [input.material]
  produces:
    inspection:
      record: material-inspection
  next: write-summary
```

`uses` lists the value references the action reads, and each name in `produces`
declares a value that later steps read as `result.<name>`. Both are declarations
rather than descriptions: `uses` is what makes a value count as read, and a
produced value nothing later reads is reported.

Where a branch can skip this action, give each produced value a `default` so
later steps can read it whichever way the run went.

An action is the only step form that can reach a file. Give it a `resource` when
it must run a script, read a reference, or copy or fill an asset.
