"""Every word the generated Markdown says that no skill source supplies.

A bundle is mostly the author's own commands, rendered. What is left over is the
compiler's own voice: the section headings, the sentence that introduces each
list, the labels a generated node carries, and the phrases that turn a declared
prohibition into a command an agent can act on rather than an instruction to do
the thing that is forbidden.

That voice is editorial and changes as one thing. The heading levels, the
punctuation, the node-label algorithm, and the order of sections are format, and
change for other reasons. They are kept apart so that rewording what a bundle
says is one file to edit rather than a renderer to read line by line, telling
prose from syntax.

Some labels here are load-bearing rather than editorial. `REQUIRED`,
`PROHIBITED`, `VERIFY`, `STATE_UPDATE`, `PRODUCES`, `SUPPLIES`, `ON_SUCCESS`,
and `ON_FAILURE` name the generated roles the load-bearing-reference check
treats as execution, so an outbound link can never appear under one. Renaming
one renames what that check looks for; the check reads these names rather than
repeating them.
"""

from __future__ import annotations


# Recovery is stated as resuming rather than as a procedure: the compiler cannot
# know what a host's reads offer, and naming line ranges or an end-of-file signal
# would turn a missing tool into a blocked run.
MODULE_READING = (
    "A node is named `n-<id>`, and a node in another module is named "
    "`<module>:n-<id>` — read `execution/<module>.md` and continue at that "
    "node. Enter a module only at the node you were sent to; a module has no "
    "entry of its own, and its first node is not one.\n"
    "\n"
    "Read the exact relative path, and do not infer a module's contents from "
    "its path or title. If a read returns only part of the module, resume from "
    "where it stopped and keep reading until the module's whole text has been "
    "read, then act on it. If the module cannot be read, or its remaining text "
    "cannot be retrieved, return `blocked`."
)

# Shared generated labels.
CONTRACT_HEADING = "Execution contract"
CONTRACT_SCOPE = (
    "Execute instructions in this file or in an execution module named by "
    "an explicit load instruction."
)

START_HEADING = "Start"
# The one-route skill states where to begin. Several routes state a choice, and
# the lead has to say what the choice is made from: the request, and nothing the
# skill has done yet, because nothing has.
START_SINGLE = "Start at {target}"
START_LEAD = "Choose the matching entrypoint from the current request:"
START_OTHERWISE = "Otherwise"
# What an unrecognized request costs, when the source declared no route for one.
# It names the request and the routes rather than only refusing, so a reader can
# tell a skill that does not serve this work from one whose routing is wrong.
START_UNMATCHED = (
    "If none matches, return `blocked`, naming what the request asked for and"
    " the entrypoints that did not match it."
)

CONTEXT_HEADING = "Context"
CONTEXT_LEAD = (
    "This applies throughout the run, whichever steps you take. It improves how "
    "you work and how the result reads; where it meets a command, the command "
    "decides."
)

PROFILES_HEADING = "Profiles"
PROFILES_LEAD = (
    "Profiles provide additional guidance for recurring situations. "
    "`profiles/index.md` lists the ones available here. Opening a profile that "
    "matches the work in front of you can make that work quicker and its result "
    "better suited to it."
)

PROFILE_INDEX_HEADING = "Profile lookup"
PROFILE_INDEX_LEAD = (
    "Use each profile's title, and its description where one is given, to decide "
    "whether it applies. Load every applicable profile and no others."
)

WORKFLOW_HEADING = "Workflow: {title}"
WORKFLOW_HEADING_PART = "Workflow: {title} ({part}/{total})"
WORKFLOW_ID = "Workflow ID:"
WORKFLOW_PURPOSE = "Purpose:"
WORKFLOW_INPUTS = "Inputs:"
WORKFLOW_OUTCOMES = "Outcomes:"
# A defaulted value exists from the workflow's first node, so the header is
# where its reader meets it: an agent that reaches a reader having skipped the
# step that produces one has to learn the value from the module it is already
# holding, and every module of a workflow carries this header.
WORKFLOW_DEFAULTS = "Defaults until produced:"
WORKFLOW_DEFAULT = "`{name}: {type}` = `{value}`"
WORKFLOW_ENTRY = "Entry node:"
WORKFLOW_NO_INPUTS = "none"

# A generated node's own fields.
READS = "Reads"
PRODUCES = "Produces:"
SUPPLIES = "Supplies:"
REQUIRED = "Required:"
PROHIBITED = "Prohibited:"
VERIFY = "Verify:"
ACTIVE = "Active:"
STATE_UPDATE = "State update:"
INITIALIZE_FRAME = "Open the {frame} in state `{state}`."
STATE_SET = "set `state.{name}` from {binding}"
STATE_CLEAR = "clear `state.{name}`"
CONSIDER = "Consider:"
CONTEXT_NOTE = "Context - {id}:"
CONTEXT_NOTE_LINK = "full note"
CHOOSE_ONE = "Choose exactly one:"
GATE_STATES = "Reach exactly one state:"
RETURN_LINE = "This node ends the workflow. It has no successor."

ON_SUCCESS = "On success: continue at `{label}` - {command}"
ON_FAILURE = "On failure: return `blocked`, naming the item that failed."

# The command a prohibition renders as. A prohibition's own sentence names the
# thing not to do, which as a heading would read as an instruction to do it.
PROHIBITION_COMMAND = "Do not {command}"

# The heading a check node states where one construct placed several items
# here. A lone item is its own heading; two or more need a sentence over them,
# and it names the boundary rather than the construct, because which construct
# is speaking is provenance a run cannot act on and `inspect` already carries
# it. The items are what the agent acts on, and they render beneath.
CHECK_GROUP = {
    "before": "Satisfy every obligation below before performing this step.",
    "after": "Satisfy every obligation below now that this step is performed.",
    "before-return": "Satisfy every obligation below before this workflow returns.",
}

# Generated reference pages.
PAGE_RATIONALE = "Rationale"
PAGE_POINTS = "Points"
PAGE_FURTHER = "Further reading"
