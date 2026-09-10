### Attention budgets

An agent pays for a skill in what it has to read. Degardis holds the generated
skill to two limits, so that no single load asks for more than a host can be
relied on to take in at once.

| Limit | Size | Applies to |
| --- | --- | --- |
| Root budget | 8 KiB | The generated `SKILL.md`. |
| Module budget | 16 KiB | One generated execution module, and any one node in it. |

#### The root budget

`SKILL.md` is the control plane. It contains no workflow or workflow body.
Before selecting a route, it gives the agent the generated run context and the
entrypoint table. A table row contains an entrypoint's condition, the load to
perform, and the command of the entry node that load reaches.

The root is the smaller limit because every skill selection loads that control
plane. Its fixed generated sections leave authors only a few sources of growth:
entrypoint conditions and supplied values, the copied command of each entry
node, and summaries for [guidance](#guidance) bound at the manifest. Several
entrypoints and manifest-level guidance cost every activation. If the root runs
over, begin with the copied entry-node command; it is the only workflow text
the root repeats.

When the root budget runs over, revise the source design in this order:

- Shorten entrypoint conditions and entry-node commands. Say the one thing each
  performs, and move reasoning into a heuristic and background into a reference.
- Bind requirements at the narrowest scope that works. A policy bound at the
  manifest is carried everywhere; bound at the steps that need it, it is carried
  where it is enforced.
- Move background out of commands and into references, guidance, or profiles,
  which are loaded only when they are wanted.

These changes reduce the material every activation asks its reader to hold in
mind. A root-budget finding is a review of that control plane.

#### The module budget

An execution module is loaded only on the route that reaches it. Its limit is a
constraint on the compiler's layout, not a capacity that authors apportion
among modules. The planner chooses module boundaries and node ordering to
minimize the cost of complete execution paths. Spare bytes in one module do not
improve a skill, and changing a workflow to create them can make the paths an
agent reads worse.

Read a module-budget warning as a failed fit, then identify why it failed. A
`render.node-budget` warning names a node that cannot be partitioned: its
command or the requirements bound to that step are the only source-level
material that may need revision. A `render.module-budget` warning without it
means that the repeated workflow header leaves no room to place a node. Moving
nodes between modules cannot repair either case. Keep necessary content; revise
it only when the command, binding, or workflow description can become clearer
without changing what the skill requires. Module results are not a score for
the source: leave their layout to the compiler and respond only to the material
a warning identifies.
