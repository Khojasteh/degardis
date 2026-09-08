### Supporting files

Three content keys select files rather than constructs, and each is reached a
different way.

| Kind | Is | Reached by |
| --- | --- | --- |
| Reference | Supporting Markdown. | A `read` resource, or the `references` field of a pattern, heuristic, guidance, or profile file. |
| Script | A selected executable helper. | A `run` resource on an action. |
| Asset | A supporting file such as a template or media. | A `read`, `copy`, or `fill` resource on an action. |

Select each one under `content` before anything names it, and make sure
something does name it: a selected script or asset no action reaches, and a
reference no route reaches, are each reported rather than shipped.

```yaml
content:
  references:
  - references/*.md
  scripts:
  - scripts/*.py
  assets:
  - assets/templates/*.md
```

Open each reference with a heading. The page that links it names the link by
that heading, so an agent reads what the document is before deciding to open
it; a reference that states none is linked by its path, and reported.

A reference is documentation, not instruction. Keep required work in a workflow,
policy, rule, protocol, or pattern, and let a reference carry the background,
the worked example, or the detail that would crowd a command. A command that
puts a link where the instruction belongs is reported, because an agent that
does not open the document would then be missing part of what it was told to do.
