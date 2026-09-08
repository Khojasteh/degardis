### Heuristics

A heuristic helps an agent choose among options that are already valid. Name one
on a `decide` or a `gate` step, and nowhere else.

| Field | Required | Meaning |
| --- | --- | --- |
| `question` | Yes | Choice the heuristic helps make. |
| `advice` | Yes | Non-empty mapping of named advice items. |
| `title` | No | Reader-facing title. |
| `references` | No | Supporting Markdown. |

```yaml
question: How much detail does this reader need?
advice:
  reader-decision:
    prefer: Prefer the detail that changes what the reader decides.
    because: Detail a reader cannot act on costs attention and adds nothing.
  qualification-first:
    when: length(result.inspection.gaps) > 0
    prefer: Prefer stating a qualification over dropping it to save space.
    caution: A qualification restated in every section reads as hedging.
```

Each advice item has a required `prefer` and optional `when`, `because`, and
`caution`. Write `prefer` as the option to lean toward, `because` as the reason
it holds, and `caution` as the case where it stops holding. `when` is a DExpr
condition, not prose: the advice is offered only where it is true, so use it to
withhold advice that does not apply rather than to describe when it does.

The limit is strict, and it is what makes advice safe to offer. A heuristic
cannot authorize an action, prohibit one, or prove that a requirement was met.
Naming heuristics on any other step form is reported, and so is naming one in a
`verify`. Where the guidance must be followed, it is not advice—write it as a
policy provision or a rule.

A heuristic renders only on the decision or gate that named it. It is not
available to the run generally, so name it at each choice it should inform.
