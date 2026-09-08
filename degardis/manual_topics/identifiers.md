### Identifiers and references

A selected file's name without `.yaml` is the identifier of the construct it
defines, so `workflows/write-summary.yaml` defines the workflow
`write-summary`. That identifier is the name every other file uses to refer to
it.

Identifiers use lowercase letters, digits, and single hyphens: `write-summary`
is valid, `Write_Summary` and `write--summary` are not. The same spelling rule
applies to step ids, outcome names, choice and state names, value names, enum
members, and record field names. The skill's own name is spelled the same way,
and must match the source directory name.

Moving a file without changing its stem keeps its identifier. Renaming its stem
changes the identifier, and every reference to it must be updated in the same
change.

Four rules govern how constructs find each other.

| Rule | What it prevents |
| --- | --- |
| A referenced identifier must be selected by a content pattern. | Naming a file the skill does not ship. |
| A reference must name the kind expected in that position. | Naming a rule where a policy belongs, or the reverse. |
| Two selected files of one kind may not share a stem. | Two constructs answering to one name. |
| Every selected construct must be reached. | Shipping a file nothing executes, calls, or binds. |

The last rule is the one authors meet most often. A policy no scope binds, a
workflow no reached step calls, a pattern no step applies, and a heuristic no
decision names are each reported. Delete it, or bind it where it belongs.

One more rule concerns prose rather than structure. Where a reached construct's
own text uses a selected identifier as a bare word, that is warned about: an
agent reading the sentence cannot tell the name from the words around it. Put
the identifier in backticks, or reword the sentence. This is worth watching
when an identifier is also an ordinary word—a workflow named `review` turns
every sentence containing "review" into a candidate.
