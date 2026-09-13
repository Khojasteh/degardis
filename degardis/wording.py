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

READING_HEADING = "Required reading"
READING_PARAGRAPHS = (
    "Maintain a session-local reading register for governing pages: path, "
    "applicability condition, dependencies, basis, and read status."
    "\n\n"
    "A page with no condition is always required. Reassess applicability when "
    "dependencies change, new information may affect it, or the prior judgment "
    "can no longer be justified. Treat uncertainty as required."
    "\n\n"
    "**Hard gate:** Before any request, task/stage change, decision, action, or "
    "output, reassess stale/unassessed entries and fully read every required "
    "unread page."
    "\n\n"
    "You are BLOCKED from proceeding until no required page is unread or "
    "unresolved. This gate is mandatory and cannot be deferred or bypassed."
    "\n\n"
    "Mark a page unread again when you can no longer state its requirements "
    "without reopening it."
)

TASKS_HEADING = "Tasks"
TASKS_LEAD = (
    "Take the first task below whose cues match the request. Do not start work "
    "until you have opened its linked page and read it in full."
)
TASKS_SINGLE_LEAD = (
    "This skill performs one task. Do not start work until you have opened its "
    "linked page and read it in full."
)
TASK_ROUTE = "**[{title}]({link})**"
TASKS_UNMATCHED = (
    "If no task matches, say so and say what the request asked for, rather than "
    "taking the nearest task."
)

FACETS_HEADING = "Facets"
FACETS_LEAD = (
    "Facets carry guidance that the situation calls for rather than the task. "
    "Before starting work, open and read `{index}`, then load every applicable "
    "facet and no others. Do not start work until you have read each loaded "
    "facet in full. A task never selects facets for you."
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

FACET_INDEX_HEADING = "Facets"
FACET_INDEX_LEAD = (
    "Use each facet's title, and its description where one is given, to decide "
    "whether it applies to the situation in front of you. Load every applicable "
    "facet and no others. Open every loaded facet and read its page in full "
    "before you continue."
)

FACET_ROW = "[{title}]({link})"
FACET_ROW_DESCRIBED = "[{title}]({link}) — {description}"

# --------------------------------------------------------------------------
# Principles
# --------------------------------------------------------------------------

PRINCIPLES_HEADING = "Principles"
PRINCIPLES_LEAD = (
    "Add every listed principle to your reading register. Text before `:` is "
    "its applicability condition; a row without one is unconditional."
)

PRINCIPLE_ROW = "[{title}]({link})"
PRINCIPLE_ROW_CONDITIONAL = "{activation}: [{title}]({link})"

# --------------------------------------------------------------------------
# Guides
# --------------------------------------------------------------------------

GUIDES_HEADING = "Guides"
GUIDES_LEAD = (
    "Add every listed guide to your reading register. Text before `:` is its "
    "applicability condition; a row without one is unconditional."
)

GUIDE_ROW = "[{title}]({link})"
GUIDE_ROW_CONDITIONAL = "{activation}: [{title}]({link})"
