### Entrypoints

`entrypoints` names every kind of request the skill serves, and the workflow
that serves each one. The agent chooses between them from the request alone,
before it reads any workflow, so a skill that does several kinds of work says so
here instead of working out which applies after it has already started.

| Field | Required | Meaning |
| --- | --- | --- |
| `when` | Yes, except on the last route | Sentence stating when this route applies. |
| `target` | Yes | [Workflow](#workflows) the route enters, by file stem. |
| `with` | No | Literal [values](#supplied-values) filling the target's inputs. |

```yaml
entrypoints:
  audit:
    when: The request asks whether existing material is accurate.
    target: audit-material
  gaps:
    when: The request asks what the material leaves out.
    target: report-gaps
  summarize:
    target: compose
```

Routes are tried in the order you write them, and the first whose sentence
matches is the one taken, so write the narrower condition above the broader one.
Write each `when` about the request itself. The agent has nothing else yet, so a
condition it would first have to inspect, calculate, or look up belongs in the
workflow instead, as a [gate](#gate) or a [decision](#decide).

The last route may leave `when` out, and is then the route taken when no other
matched—where `otherwise` sits in a [branch](#branch). Nothing else marks it: a
route with no condition is taken whatever the request says, so nothing written
after one could be reached, and leaving `when` out anywhere else is reported.
Give every route a `when` instead, and a request that matches none of them stops
the run rather than starting the nearest thing to it.

`with` fills the target's inputs. Supply a `literal`, since no step has run when
the route is chosen and there is no earlier value to read; supplying `from` is
reported. An input you leave out is one the agent establishes from the request.
Two routes can therefore enter one workflow, each supplying the input that tells
it which of them it was entered by.

What a route supplies is stated on that route, beside the module and node it
leads to, because both routes into one workflow arrive at the same node and it
cannot say which of them arrived. Only the name and the value appear there; the
entered workflow states the input's type on its own header.
