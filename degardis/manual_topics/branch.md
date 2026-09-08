### `branch`

Use a branch when declared information—not the agent's judgment—chooses the
route. It has one `branch` field containing an ordered list. Each case has
`when` and `next`; the final case has `otherwise` alone.

```yaml
route:
  branch:
  - when: input.wide == true
    next: detailed
  - otherwise: brief
```

Cases render in the order you write them, and the agent is told to take the
route whose condition holds. Write conditions that cannot both be true at once,
so that route is never ambiguous, and let the final `otherwise` carry everything
they do not cover. That last case is what makes the step total: every path
leaving a branch has a destination, whatever the values turn out to be.

A branch records no choice of its own. There is no `branch.<step-id>` to read
later, because the values its conditions read are already available to whatever
comes next. Use a `decide` step when the agent must make the choice, and a
`gate` step when the choice must be recorded for a later check to read.
