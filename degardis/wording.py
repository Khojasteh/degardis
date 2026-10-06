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
    "that none exists, use a session scratchpad or another reopenable session-only medium. Keep "
    "each record it asks for, whether a register, ledger, or account, separate from every other. "
    "Never hold working state in recall, conversation text, or implicit tracking."
)

REGISTER_HEADING = "Progress register"

# The progress-register protocol, written for a bundle with every feature, as
# paragraphs of pieces. A string is always said. A `(feature, with, without)`
# piece says `with` when the bundle has that feature and `without` when it does
# not, so a paragraph that is only about a missing feature says nothing and is
# left out. The features are `principles`, `guides`, `facets`, and `handoffs`;
# `pages` is principles or guides, `loads` is pages or facets, and `conditions`
# is pages or hand-offs.
WORKING_PROTOCOL = (
    (
        "Before anything further, copy `{register}` into re-readable working state and keep that "
        "copy current for the whole session, across requester messages and deliveries. Record "
        "every gate value and its evidence in it. Write each change as it happens; never "
        "defer or pause updates. What it does not show did not happen: a page whose row lacks "
        "its code is unread, and a task not marked `done` is unfinished.",
    ),
    (
        "Reopen it after each requester message",
        (
            "conditions",
            "; after relevant work, scope, material, or evidence changes, before the next ",
            "",
        ),
        ("pages", "named-", ""),
        ("conditions", "condition-dependent action;", ""),
        " and before every non-revisable effect, delivery, or completion claim. Do not reopen "
        "again if nothing changed. Non-revisable means not undoable in-run; delivery returns an "
        "outcome; a completion claim declares one complete. Reread this section whenever it is "
        "no longer in view.",
    ),
    (
        (
            "pages",
            "For {page_kind} rows, (`Id`, `Applicability`) is unique; only `Verdict`, `Basis`, "
            "and `Read code` may change. A row is named only when an already-read page refers to "
            "its page; an unnamed row keeps `-` as its `Verdict` and `Basis`.",
            "",
        ),
    ),
    (
        (
            "pages",
            "`Verdict` is `-`, `pending`, or `required`: a named row is `pending` while "
            "inapplicable, otherwise `required`; uncertainty means `required`. `Basis` states why "
            "and the decision served. Recompute affected rows when inputs change and before a "
            "condition could become true. Read newly required pages before dependent work.",
            "",
        ),
    ),
    (
        "`Read code` is `-` or the code closing a page you read completely. On reaching it, "
        "before any work from that page, record it ",
        ("pages", "on every row of that page, whatever its `Verdict`, or, for a task page, ", ""),
        "on the route row it serves, and add the page's `Conformance` rows. Page changes require "
        "reset and reread.",
        (
            "pages",
            " After a `Basis` change, reassess understanding for the current decision; if "
            "unclear or uncertain, reset and reread.",
            "",
        ),
        " Guessed, reconstructed, partial-read, or recalled codes are invalid.",
        ("loads", " Never combine a task page with other pages in one read.", ""),
    ),
    (
        "`Route` has one row per task occurrence. Assign an immutable unique `Occurrence`; `Id` "
        "names its task and immutable `Basis` names its requested outcome",
        (
            "handoffs",
            ", or its sending occurrence and the hand-off condition that held (`always` for an "
            "unconditional hand-off)",
            "",
        ),
        ". The first `Status: -` row is current. Never remove or replace rows; ",
        (
            "handoffs",
            "only `Read code`, `Status`, and `Waits for` change. `Waits for` lists prerequisite "
            "occurrences or `-`. Order unfinished rows by dependencies, then requested order.",
            "only `Read code` and `Status` change.",
        ),
        " Add new outcomes in execution order. Put requester refinements that leave the basis "
        "true in `Requester` conformance rows.",
    ),
    (
        "`Status` is `-`, ",
        ("handoffs", "`suspended`, ", ""),
        "`done`, `incomplete`, or `dropped`. ",
        (
            "handoffs",
            "Suspend for recorded prerequisites; use `incomplete` for other stops.",
            "Use `incomplete` for stops.",
        ),
        " Set `done` only after producing the outcome",
        ("handoffs", ", clearing its waits,", ""),
        " and setting all governing conformance to `satisfied` or `not-applicable`, before "
        "delivering it as complete. Reading",
        ("handoffs", " or handing off", ""),
        " is not completion. Drop a row only when its basis no longer holds under governing "
        "instructions",
        ("handoffs", ", never solely because it hands off", ""),
        ". `done` and `dropped` are terminal. Resume `incomplete` as `-` only after clearing its "
        "stop",
        ("handoffs", " and rechecking prerequisites", ""),
        ".",
    ),
    (
        (
            "handoffs",
            "For a hand-off, reuse an occurrence responsible for the same result and state, or add "
            "one, before opening its page. A prerequisite suspends its sender: record the needed "
            "result in `Conformance`, scoped to the sender's `Occurrence`, put the target in "
            "`Waits for`, and order it first. Never create a cyclic wait. On return, evaluate that "
            "result's conformance row and clear only waits whose requirements are `satisfied` or "
            "`not-applicable`. Once all waits clear, resume the same sender as `-` before "
            "unrelated work; target completion does not satisfy sender acceptance. An unavailable "
            "result or cycle blocks dependent work; keep unmet requirements and mark the waiting "
            "sender `incomplete` when stopping. Open a follow-on's page only after the sender is "
            "`done`. Instead-of work permits `dropped` only if the sender's basis no longer "
            "holds; otherwise preserve its unfinished outcome.",
            "",
        ),
    ),
    (
        "`Conformance` covers requester instructions, `SKILL.md`",
        (
            "pages",
            ", the current {task_kinds}, and required {page_kinds}.",
            ", and the current {task_kinds}.",
        ),
        " Add each page's rows when you read it, `SKILL.md`'s on copying, and the requester's as "
        "given. Use one row per checkable requirement/scope, or one exhaustive row if "
        "unsplittable; use a bundle-relative `Page`, or `Requester`. Keep rows governing work or "
        "retained effects. Reading is not conformance. `Result` is `-`, `satisfied`, "
        "`not-applicable`, or `failed`; checked rows include scope and evidence/basis. Reset "
        "affected results when scope, work, or evidence changes.",
    ),
    (
        "If the register is missing or uneditable, stop and rebuild: take a fresh copy, reread "
        "`SKILL.md` and pages in retained route",
        ("loads", "/navigation", ""),
        " history, then rederive route and conformance from the conversation and retained "
        "effects. Never reconstruct unread content or codes from recall. If ",
        ("pages", "named rows, ", ""),
        "route history, scopes, and supported results cannot be recovered exactly, report a "
        "blocker.",
    ),
    (
        "At each reopen, reconcile the register first. Missing codes permit only register updates "
        "and loading required pages, including requirements discovered during loading. Record "
        "codes and conformance before governed work. Before task work, ",
        (
            "pages",
            "named rows governing the action must follow these rules, required pages must hold "
            "valid codes, and ",
            "",
        ),
        "the current occurrence must hold its basis and task code. Unmet requirements block only "
        "actions they govern",
        ("handoffs", ", not a prerequisite's independently permitted work", ""),
        ". Before a non-revisable effect, its precheckable requirements must be `satisfied` or "
        "`not-applicable`; check effect-dependent requirements afterward.",
    ),
    (
        "Before delivery, ",
        ("conditions", "recompute conditions, ", ""),
        "evaluate every governing or retained conformance row, and record the delivered rows' "
        "status. An occurrence is complete only when `done`; whole-request completion requires "
        "every row `done` or `dropped` and all governing or retained conformance `satisfied` or "
        "`not-applicable`. A `failed` or `-` result bars completion and the effects it governs; ",
        ("handoffs", "suspension, dropping, and", "dropping and"),
        " code-loading clear none. Report unresolved work as such. Never end a turn with an "
        "unrecorded change or a read task row still at `-`.",
    ),
)

# The words the protocol's `{page_kind}`, `{page_kinds}`, and `{task_kinds}`
# stand for, each beside the feature that ships that kind. A term names only
# the kinds the bundle ships, joined by `PROTOCOL_TERM_JOINER`; tasks are always
# shipped.
PROTOCOL_TERMS = {
    "page_kind": (("principles", "principle"), ("guides", "guide")),
    "page_kinds": (("principles", "principles"), ("guides", "guides")),
    "task_kinds": (("tasks", "task"), ("facets", "facets")),
}
PROTOCOL_TERM_JOINER = "/"

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
    "task; one with conditions applies when any holds, at the point it names. "
    "Reassess conditions as work changes. Reuse a route occurrence responsible for "
    "the needed result and state, or add one, before continuing. Entering the target "
    "does not complete the sender."
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
    "Principles govern the whole run. Your progress register lists when each applies, "
    "under `Applicability`. Read each one that applies before continuing, and any other "
    "as soon as it applies."
)

# --------------------------------------------------------------------------
# Guides
# --------------------------------------------------------------------------

GUIDES_HEADING = "Guides"
GUIDES_LEAD = (
    "Read each guide that applies before continuing, and any other as soon as it applies."
)

# --------------------------------------------------------------------------
# Principle and guide pages
# --------------------------------------------------------------------------

READ_CODE_LINE = "Read code: `{code}`"

# --------------------------------------------------------------------------
# Progress register asset
# --------------------------------------------------------------------------

REGISTER_TITLE = REGISTER_HEADING + " ({name}/{version})"
ROUTE_HEADING = "Route"
ROUTE_COLUMNS = ("Occurrence", "Id", "Basis", "Read code", "Status")
# Only a bundle with hand-offs has a task that waits for another.
ROUTE_WAITS_COLUMN = "Waits for"
REGISTER_COLUMNS = ("Id", "Applicability", "Verdict", "Basis", "Read code")
CONFORMANCE_HEADING = "Conformance"
CONFORMANCE_COLUMNS = ("Page", "Requirement", "Scope", "Result", "Evidence")

REGISTER_EMPTY = "-"
REGISTER_UNCONDITIONAL = "always"
