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

START_HEADING = "Start"

PRINCIPLES_LEAD = (
    "Do not start a task until you have opened each principle in the following "
    "list and read its page in full."
)
PRINCIPLE_ROW = "[{title}]({link})"

CONDITIONAL_PRINCIPLES_LEAD = (
    "If a condition below holds at any point, do not continue until you have "
    "opened the linked principle and read its page in full."
)
CONDITIONAL_PRINCIPLE_ROW = (
    "**{activation}:** open and read [{title}]({link}) in full before continuing."
)

TASKS_LEAD = (
    "Take the first task below whose cues match the request. Do not start work "
    "until you have opened its linked page and read it in full."
)
TASKS_SINGLE_LEAD = (
    "This skill performs one task. Do not start work until you have opened its "
    "linked page and read it in full."
)
TASKS_UNMATCHED = (
    "If no task matches, say so and say what the request asked for, rather than "
    "taking the nearest task."
)
TASK_ROUTE = "**[{title}]({link})**"

PROFILES_HEADING = "Profiles"
PROFILES_LEAD = (
    "Profiles carry guidance that the situation calls for rather than the task. "
    "Before starting work, open and read `{index}`, then load every applicable "
    "profile and no others. Do not start work until you have read each loaded "
    "profile in full. A task never selects profiles for you."
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
TASK_PRINCIPLES_HEADING = "Principles"
TASK_PRINCIPLES_LEAD = (
    "Do not start this task until you have opened each principle in the following "
    "list and read its page in full."
)
TASK_CONDITIONAL_PRINCIPLES_LEAD = (
    "If a condition below holds at any point, do not continue until you have "
    "opened the linked principle and read its page in full."
)
GUIDES_HEADING = "Guides"
CONDITIONAL_GUIDES_LEAD = (
    "If a condition below holds at any point, do not continue until you have "
    "opened the linked guide and read its page in full."
)
CONDITIONAL_GUIDE_ROW = "[{title}]({link}) — {activation}"
UNCONDITIONAL_GUIDES_LEAD = (
    "Read these guides before starting this task. Open every linked page and "
    "read it in full before you begin."
)
GUIDE_ROW = "[{title}]({link})"


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------

PROFILE_INDEX_HEADING = "Profiles"
PROFILE_INDEX_LEAD = (
    "Use each profile's title, and its description where one is given, to decide "
    "whether it applies to the situation in front of you. Load every applicable "
    "profile and no others. Open every loaded profile and read its page in full "
    "before you continue."
)
PROFILE_ROW = "[{title}]({link})"
PROFILE_ROW_DESCRIBED = "[{title}]({link}) — {description}"
