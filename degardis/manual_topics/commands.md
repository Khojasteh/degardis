### Commands

A command is the sentence an agent reads and performs. Workflow steps, policy
provisions, rules, protocol hooks, and pattern procedure items all carry one,
and the compiler places each where it is enforced. What you write is what the
agent is told to do, so write the instruction and not the topic.

Many commands become the heading an agent skims, and every generated heading is
checked for two conditions. Write every command to meet them:

| Condition | Failing | Passing |
| --- | --- | --- |
| At least two words. | `Report` | `Report the result.` |
| Closes with `.`, `?`, `!`, or `:`. | `Review the draft` | `Review the draft.` |

A heading that reads as a topic invites an agent to guess the content instead
of performing the action, which is why a bare noun phrase is refused. State the
action, the check, the choice, or the return the step performs:

```yaml
inspect-material:
  action: Inspect the supplied material for its subjects and limitations.
  next: write-summary
```

The same holds for a prohibition. Write what must not be done, in full:
`prohibit: Publish a claim the supplied material does not support.`

A command carries execution, so it may not carry a link. An outbound
reference—a Markdown link, or a bare path such as `references/style.md`—is
supplementary documentation, and putting one in a command, a requirement, a
verification, a state update, or a supplied value is reported. Name a document
through the fields that exist for it: `resource` on an action, or `references`
on a pattern, heuristic, guidance, or profile file. Keep the instruction itself complete
without the document, so an agent that never opens it still knows what to do.
