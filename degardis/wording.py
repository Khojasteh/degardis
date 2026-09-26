"""Every word the generated Markdown says that no source supplies.

A bundle is mostly the author's own material, moved to where it is needed. What
is left over is the compiler's own voice: the section headings, the sentence that
introduces a list, and the instruction that tells a reader what to do with the
page in front of them.

That voice is editorial and changes as one thing. Heading levels, link syntax,
path layout, and the order of sections are format, and change for other reasons.
They are kept apart so that rewording what a bundle says is one file to edit
rather than a renderer to read line by line, telling prose from syntax.

Everything here is short by design. The generated words sit between the reader
and the author's material, and every sentence of them is a sentence the author
did not write and the reader did not ask for.
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# The root
# --------------------------------------------------------------------------

REGISTER_HEADING = "Instruction register"
REGISTER_INSTRUCTIONS = (
    "Before any work, copy `{register}` into a re-readable private session state. "
    "Use only that copy as this run's instruction register, and keep every register "
    "fact in it: memory, notes, conversation text, and implicit tracking are not a "
    "register. Never edit the bundled form. The register is a standing gate for the "
    "whole run, not a setup checklist: reopen the copy after every new requester "
    "message, before any step a named condition governs, and before any completion "
    "claim."
    "\n\n"
    "In principle/guide rows, only `Verdict`, `Basis`, and `Read code` may change. "
    "`Conformance` rows may change, be added, or be removed."
    "\n\n"
    "`Verdict`: `-`, `pending`, or `required`. A row becomes named only when a page "
    "you have read references it; never name rows from predicted relevance. Leave "
    "unnamed rows untouched. Named rows are `pending` while their `Applies when` does "
    "not hold for current work, otherwise `required`. Record why in `Basis`, including "
    "the decision it serves; uncertainty is `required`. Whenever work, scope, or newly "
    "read material changes something a named condition depends on, recompute affected "
    "`Verdict` and `Basis` values. Also recompute before any step that could make a "
    "named condition true. Read every newly required page before dependent work continues."
    "\n\n"
    "`Read code`: `-`, or the code printed at the end of that page. Take a code only "
    "from the page itself after reading all of it; a remembered, guessed, reconstructed, "
    "or partial read yields no code. Rows may be updated together when each code was "
    "taken that way. Reset to `-` if the page changes or its `Basis` no longer holds "
    "for the decision at hand."
    "\n\n"
    "`Task`: the current task's `Id` and `Read code`; rewrite it whenever routing changes "
    "the task."
    "\n\n"
    "`Conformance` tracks governing requirements from purpose (`SKILL.md`), current task, "
    "current facets, and required principles/guides. Use bundle-relative `Page` paths. "
    "Give each independently checkable requirement/scope its own row; if unsplittable, "
    "use one exhaustive scope. Keep rows while governing work/retained effects. Reading "
    "is not conformance."
    "\n\n"
    "`Result`: `-`, `satisfied`, `not-applicable`, or `failed`. Checked rows give `Scope` "
    "and evidence/basis. If `Scope`, governed work, or evidence changes, first reset every "
    "affected `Result` to `-`; do not carry a prior result across changed work."
)

REGISTER_GATE_HEADING = "Gate"
REGISTER_GATE_INSTRUCTIONS = (
    "Continue only when named rows satisfy these rules and `Task` and every `required` row's "
    "`Read code` hold their page's code. Before non-revisable effects or delivery, reassess "
    "governing named conditions."
    "\n\n"
    "Before a non-revisable effect, reconcile its requirements. Those checkable beforehand must be "
    "`satisfied` or `not-applicable` with evidence or basis; afterward evaluate requirements needing "
    "evidence from the effect. Before any completion claim on any turn, recompute governing named "
    "conditions, reconcile all governing content, and evaluate every current/retained `Conformance` "
    "row against the current work and evidence. Completion requires each to be `satisfied` or "
    "`not-applicable`; `failed` or `-` rows bar only governed effects and completion and may be "
    "reported as limits/blockers."
    "\n\n"
    "If the instruction-register copy is lost or cannot be updated, stop and rebuild from a fresh copy "
    "by replaying navigation from root and re-deriving `Conformance` from governing content/current "
    "state; never reconstruct from memory. If exact recovery fails, report a blocker."
)

TASKS_HEADING = "Tasks"
TASKS_LEAD = (
    "Check tasks in order; choose the first task with a matching cue, read its page "
    "in full, then do it. When a later requester message changes the requested "
    "outcome, route the request as it now stands; otherwise keep the current task."
)
TASKS_SINGLE_LEAD = (
    "This skill has one task. Open its linked page and read it in full before doing "
    "the task."
)
TASK_ROUTE = "**[{title}]({link})**"
TASKS_UNMATCHED = (
    "If no task matches, say so and briefly identify the request. Do not choose "
    "the closest task."
)

FACETS_HEADING = "Facets"
FACETS_LEAD = (
    "Facets apply by situation, not task. Read `{index}`, then applicable facets."
)

# --------------------------------------------------------------------------
# A task page
# --------------------------------------------------------------------------

GOAL_HEADING = "Goal"
APPROACH_HEADING = "Approach"
KNOWLEDGE_HEADING = "What you need to know"
KNOWLEDGE_KIND_HEADINGS = {
    "concept": "Concepts",
    "fact": "Facts",
    "constraint": "Constraints",
    "guidance": "Guidance",
}

# --------------------------------------------------------------------------
# Facets index page
# --------------------------------------------------------------------------

FACET_INDEX_HEADING = "Which facets apply"
FACET_INDEX_LEAD = (
    "Use each facet's linked title and, when present, the text after it to decide whether "
    "that facet applies. Read every applicable facet and no others."
    "\n\n"
    "Recheck this index after every new requester message and before acting on newly "
    "introduced material, targets, environments, or other situations that could change "
    "which facets apply."
)

FACET_ROW = "[{title}]({link})"
FACET_ROW_DESCRIBED = "[{title}]({link}) — {description}"

# --------------------------------------------------------------------------
# Principles
# --------------------------------------------------------------------------

PRINCIPLES_HEADING = "Principles"
PRINCIPLES_LEAD = (
    "Set each principle's `Verdict` in your instruction register, then read every "
    "`required` principle before continuing."
)

PRINCIPLE_ROW = "[{title}]({link})"
PRINCIPLE_ROW_CONDITIONAL = "{activation}: [{title}]({link})"

# --------------------------------------------------------------------------
# Guides
# --------------------------------------------------------------------------

GUIDES_HEADING = "Guides"
GUIDES_LEAD = (
    "Set each guide's `Verdict` in your instruction register, then read every "
    "`required` guide before continuing."
)

GUIDE_ROW = "[{title}]({link})"
GUIDE_ROW_CONDITIONAL = "{activation}: [{title}]({link})"

# --------------------------------------------------------------------------
# Principle and guide pages
# --------------------------------------------------------------------------

READ_CODE_LINE = (
    "Read code: `{code}`. Record it as this page's `Read code` in your "
    "instruction register."
)

# --------------------------------------------------------------------------
# Instruction register asset
# --------------------------------------------------------------------------

TASK_RECORD_HEADING = "Task"
TASK_RECORD_COLUMNS = ("Id", "Read code")
REGISTER_COLUMNS = ("Id", "Applies when", "Verdict", "Basis", "Read code")
CONFORMANCE_HEADING = "Conformance"
CONFORMANCE_COLUMNS = ("Page", "Requirement", "Scope", "Result", "Evidence")

REGISTER_EMPTY = "-"
REGISTER_UNCONDITIONAL = "always"
