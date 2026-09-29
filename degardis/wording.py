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

WORKING_STATE_HEADING = "Working state"
WORKING_STATE_INSTRUCTIONS = (
    "When this skill asks for re-readable working state, first inspect the host and tool-runtime "
    "capabilities and use any session-scoped state facility they expose. Only after establishing "
    "that none exists, use a session scratchpad or another reopenable session-only medium. Never "
    "hold working state in recall, conversation text, or implicit tracking."
)

REGISTER_HEADING = "Progress register"
REGISTER_INSTRUCTIONS = (
    "Before any other work, copy `{register}` into re-readable working state and keep that copy "
    "current for the whole session, across requester messages and deliveries. Record every gate "
    "value and its evidence in it. Write each change as it happens, before you read, decide, or "
    "produce anything further; never defer or pause updates. What it does not show did not happen: "
    "a page whose row lacks its code is unread, and a task not marked `done` is unfinished."
    "\n\n"
    "Reopen it after each requester message; after relevant work, scope, material, or evidence "
    "changes, before the next named-condition-dependent action; and before every non-revisable "
    "effect, delivery, or completion claim. Do not reopen again if nothing changed. Non-revisable "
    "means not undoable in-run; delivery returns an outcome; a completion claim declares one "
    "complete. Reread this section whenever it is no longer in view."
    "\n\n"
    "For principle/guide rows, (`Id`, `Applicability`) is unique; only `Verdict`, `Basis`, and "
    "`Read code` may change. A row is named only when an already-read page refers to its page; an "
    "unnamed row keeps `-` as its `Verdict` and `Basis`."
    "\n\n"
    "`Verdict` is `-`, `pending`, or `required`: a named row is `pending` while inapplicable, "
    "otherwise `required`; uncertainty means `required`. `Basis` states why and the decision "
    "served. Recompute affected rows when inputs change and before a condition could become true. "
    "Read newly required pages before dependent work."
    "\n\n"
    "`Read code` is `-` or the code closing a page you read completely. On reaching it, before any "
    "work from that page, record it on every row of that page, whatever its `Verdict`, or, for a "
    "task page, on the route row it serves, and add the page's `Conformance` rows. Page changes "
    "require reset and reread. After a `Basis` change, reassess understanding for the current "
    "decision; if unclear or uncertain, reset and reread. Guessed, reconstructed, partial-read, or "
    "recalled codes are invalid."
    "\n\n"
    "`Route` keeps one row per task occurrence, added when the task is chosen; the first "
    "`Status: -` row is current. A route row's `Basis` names the requested outcome it serves, or "
    "the hand-off that added it: the handing-off task and the condition that held, `always` if "
    "none. Never replace or remove a row or change its `Id` or `Basis`; only its `Read code` and "
    "`Status` change. When what is asked for changes, set `dropped` on each unfinished row whose "
    "basis no longer holds, reorder unfinished rows as needed, and add rows for new outcomes in "
    "execution order. A requester's answer or refinement that leaves a row's basis true, including "
    "an answer you asked for, goes in a `Requester` conformance row, never in that `Basis`. "
    "`Status` is `-`, `done`, `incomplete`, or `dropped`. Set `done` once the row's outcome is "
    "produced and every conformance row governing it is `satisfied` or `not-applicable`, before you "
    "deliver it or open another row's page. Set `incomplete` when you stop short of that, to report "
    "a limit or blocker or to await the requester, and `-` again when work on it resumes."
    "\n\n"
    "`Conformance` covers requester instructions, `SKILL.md`, the current task/facets, and required "
    "principles/guides. Add each page's rows when you read it, `SKILL.md`'s on copying, and the "
    "requester's as given. Use one row per checkable requirement/scope, or one exhaustive row if "
    "unsplittable; use a bundle-relative `Page`, or `Requester`. Keep rows governing work or "
    "retained effects. Reading is not conformance. `Result` is `-`, `satisfied`, `not-applicable`, "
    "or `failed`; checked rows include scope and evidence/basis. Reset affected results when scope, "
    "work, or evidence changes."
    "\n\n"
    "If the register is lost or uneditable, stop and rebuild: take a fresh copy, reread `SKILL.md` "
    "and pages in retained route/navigation history, then rederive route and conformance from the "
    "conversation and retained effects. Never reconstruct unread content or codes from recall. If "
    "named rows, route history, scopes, and supported results cannot be recovered exactly, report a "
    "blocker."
    "\n\n"
    "At each reopen, continue only if named rows follow these rules, required rows hold page codes, "
    "and the current route row, if any, holds its basis and task code. Before a non-revisable "
    "effect, precheckable requirements must be `satisfied` or `not-applicable`; evaluate "
    "effect-dependent requirements afterward."
    "\n\n"
    "Before delivery or completion, recompute conditions, evaluate all governing or retained "
    "conformance rows, and set the `Status` of each route row delivered. Completion requires all "
    "those rows to be `satisfied` or `not-applicable` and every route row `done` or `dropped`; a "
    "`failed` or `-` result bars only the effects it governs and completion, and may be reported as "
    "a limit or blocker. Never end your turn with a change unrecorded or a route row whose page you "
    "read still at `-`."
)

TASKS_HEADING = "Tasks"
TASKS_LEAD = (
    "A request may ask for more than one task's outcome. Give each outcome it asks "
    "for to the first task listed whose cue matches it; a cue matching nothing asked "
    "for chooses nothing. The chosen tasks are the route, in the order the request "
    "states, otherwise the order listed here. Do them one at a time: read each page "
    "in full before its task, give later tasks what earlier ones produced, and let "
    "each task do only its own outcome. When a later requester message, a hand-off, "
    "or the work changes what is asked for, revise the route; otherwise keep it."
)
TASKS_SINGLE_LEAD = (
    "This skill has one task. Open its linked page and read it in full before doing "
    "the task."
)
TASK_ROUTE = "**[{title}]({link})**"
TASKS_UNMATCHED = (
    "If no task matches an outcome the request asks for, this skill does not cover "
    "that outcome: do not give it to the closest task, and handle it as you would "
    "without this skill. If you leave it undone, say which outcome and why."
)

FACETS_HEADING = "Facets"
FACETS_LEAD = (
    "Facets apply by situation in front of you. Read `{index}`, then applicable facets."
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
# Links to principles, guides, and hand-off targets
# --------------------------------------------------------------------------

# One shape for every such link: the link first, then any conditions. A link
# with more than one condition ends with `LINK_ROW_CONDITIONS`, and its
# conditions follow as a list nested under it, one condition per item.
LINK_ROW = "[{title}]({link})"
LINK_ROW_CONDITIONAL = "[{title}]({link}) — Applicability: {condition}"
LINK_ROW_CONDITIONS = "[{title}]({link}) — Applicability:"

# --------------------------------------------------------------------------
# Hand-offs
# --------------------------------------------------------------------------

HANDOFFS_HEADING = "Hand-offs"
HANDOFFS_LEAD = (
    "A hand-off sends the work to another task. One with no condition follows this "
    "task; one with conditions applies when any of them holds, at the point that "
    "condition names. Reassess conditions as the work changes, and add an applying "
    "task to the route before continuing."
)

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

FACET_INDEX_UNCATEGORIZED = "Other"

FACET_ROW = "[{title}]({link})"
FACET_ROW_DESCRIBED = "[{title}]({link}) — {description}"

# --------------------------------------------------------------------------
# Principles
# --------------------------------------------------------------------------

PRINCIPLES_HEADING = "Principles"
PRINCIPLES_LEAD = (
    "Set each principle's `Verdict` in your progress register, then read every "
    "`required` principle and set its `Read code` before continuing."
)

# --------------------------------------------------------------------------
# Guides
# --------------------------------------------------------------------------

GUIDES_HEADING = "Guides"
GUIDES_LEAD = (
    "Set each guide's `Verdict` in your progress register, then read every "
    "`required` guide and set its `Read code` before continuing."
)

# --------------------------------------------------------------------------
# Principle and guide pages
# --------------------------------------------------------------------------

READ_CODE_LINE = (
    "Set `{code}` as this page's `Read code` in your progress register."
)

# --------------------------------------------------------------------------
# Progress register asset
# --------------------------------------------------------------------------

ROUTE_HEADING = "Route"
ROUTE_COLUMNS = ("Id", "Basis", "Read code", "Status")
REGISTER_COLUMNS = ("Id", "Applicability", "Verdict", "Basis", "Read code")
CONFORMANCE_HEADING = "Conformance"
CONFORMANCE_COLUMNS = ("Page", "Requirement", "Scope", "Result", "Evidence")

REGISTER_EMPTY = "-"
REGISTER_UNCONDITIONAL = "always"
