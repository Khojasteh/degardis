### Resources

`resource` is how a workflow action reaches a file the skill ships. It contains
exactly one operation and a path relative to the skill directory:

```yaml
list-headings:
  action: List the headings the material already has.
  resource:
    run: scripts/list-headings.py
  next: choose-depth
```

| Operation | Reaches | Use it to |
| --- | --- | --- |
| `run` | `scripts/` | Execute a selected helper. |
| `read` | `references/` or `assets/` | Read a document the step needs. |
| `copy` | `assets/` | Place a file where the work needs it. |
| `fill` | `assets/` | Complete a template with the work's own content. |

Naming zero, two, or an unsupported operation is reported, and so is a path that
is absolute, escapes the skill directory, or sits outside the area its operation
allows.

Selection and use have to agree in both directions. A resource an action names
must be selected by a `content` pattern, or the built skill would instruct the
agent to open a file it does not ship. A file selected under `scripts` or
`assets` that no reached action names is reported too, because the bundle would
carry a file no route reaches. References are the exception: they are reached
through the `references` field of a pattern, heuristic, guidance, or profile
file as well as through a `read` resource.
