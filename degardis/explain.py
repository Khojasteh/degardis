"""What each check code means, for a reader who has the package but not its source.

Every diagnostic carries a code and one line of message. The line is enough to
locate the problem; it is not enough to decide whether the problem matters, or
what the source should say instead. This table answers both, and is written by
hand rather than derived from the checks: a check knows the condition it tests,
not why an author should care.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import fill


@dataclass(frozen=True)
class CheckExplanation:
    """One check code, in the terms an author or agent has to act on."""

    trigger: str
    impact: str
    failing: str
    passing: str


# Keyed by check code, grouped by the namespace the code belongs to. Every code
# any check can report has an entry here; tests hold this table to that.
CHECKS: dict[str, CheckExplanation] = {
    # source: reading the file at all
    "source.invalid-yaml": CheckExplanation(
        trigger=(
            "A manifest, entry, workflow, or profile file does not parse as YAML."
        ),
        impact=(
            "Nothing in the file reaches the bundle. The message names the line "
            "and what YAML did with the text, which is usually an unquoted value "
            "holding a character YAML reserves."
        ),
        failing="rule: Report the outcome: pass or fail",
        passing='rule: "Report the outcome: pass or fail"',
    ),
    "source.unreadable": CheckExplanation(
        trigger=(
            "A skill manifest cannot be loaded at all, or a profile source cannot "
            "be decoded: skill.yaml is missing, declares no name, names a "
            "directory other than its own, or the file cannot be read as UTF-8."
        ),
        impact=(
            "The skill is reported without inspecting any of its content, so no "
            "other check runs and every count reads as empty."
        ),
        failing="# summary/skill.yaml\nname: structured-summary",
        passing="# structured-summary/skill.yaml\nname: structured-summary",
    ),
    # yaml: text that survives parsing as something other than what was written
    "yaml.altered-scalar": CheckExplanation(
        trigger=(
            "An unquoted value is not the text written in the file, because YAML "
            "read part of it as syntax: an anchor (&), an alias (*), a tag (!), "
            "or a comment (#) starting inside the value."
        ),
        impact=(
            "The entry silently carries less text than the file shows, or other "
            "text entirely. Nothing fails, and the generated skill states "
            "something the author never wrote."
        ),
        failing="scope: Applies to #42 and later revisions",
        passing='scope: "Applies to #42 and later revisions"',
    ),
    "yaml.ambiguous-scalar": CheckExplanation(
        trigger=(
            "An unquoted value is one of YAML's boolean or null spellings: true, "
            "false, yes, no, on, off, null, ~, .nan, .inf, or -.inf."
        ),
        impact=(
            "The value loads as a boolean or null instead of text, so a field "
            "that should read as a word is reported as the wrong type, or is "
            "treated as absent."
        ),
        failing="kind: no",
        passing='kind: "no"',
    ),
    "yaml.numeric-scalar": CheckExplanation(
        trigger=(
            "An unquoted value is a number whose text does not survive loading: "
            "a leading zero, or a decimal with a trailing zero."
        ),
        impact=(
            "The generated skill shows the number YAML built, not the one the "
            "file holds: 007 becomes 7 and 1.10 becomes 1.1."
        ),
        failing="version: 1.10",
        passing='version: "1.10"',
    ),
    "yaml.sexagesimal-scalar": CheckExplanation(
        trigger=(
            "An unquoted value is digits separated by colons, such as a clock "
            "time or a duration."
        ),
        impact=(
            "YAML reads it as a base-60 number, so 10:30 loads as 630 and the "
            "text is gone."
        ),
        failing="constraint: 10:30",
        passing='constraint: "10:30"',
    ),
    "yaml.duplicate-key": CheckExplanation(
        trigger="One mapping holds the same key twice.",
        impact=(
            "YAML keeps the last value and discards the earlier one without "
            "failing, so an edit that looks applied has no effect."
        ),
        failing="version: 1.0.0\ndescription: Summarize a document.\nversion: 1.1.0",
        passing="version: 1.1.0\ndescription: Summarize a document.",
    ),
    # manifest: skill.yaml itself
    "manifest.invalid-name": CheckExplanation(
        trigger=(
            "The manifest name is not 1-64 lowercase letters, digits, and single "
            "hyphens, or it is the reserved name all."
        ),
        impact=(
            "The name is the skill's directory, its id namespace, and its "
            "selector, so nothing addresses the skill reliably until it is valid."
        ),
        failing="name: Structured_Summary",
        passing="name: structured-summary",
    ),
    "manifest.invalid-type": CheckExplanation(
        trigger=(
            "A manifest field holds the wrong type: format_version is not an "
            "integer, title, license, or copyright is not a non-empty string, or "
            "profiles, profiles.defaults, or interface is not the mapping or list "
            "the schema states."
        ),
        impact=(
            "The field cannot be used as declared, so the build stops rather than "
            "guessing what the value was meant to be."
        ),
        failing="format_version: '1'",
        passing="format_version: 1",
    ),
    "manifest.missing-version": CheckExplanation(
        trigger="The manifest has no version, or its version is empty.",
        impact=(
            "The generated SKILL.md records no version, so an installed skill "
            "cannot be told apart from an earlier build of itself."
        ),
        failing="name: structured-summary",
        passing="name: structured-summary\nversion: 1.0.0",
    ),
    "manifest.missing-description": CheckExplanation(
        trigger="The manifest has no description, or its description is empty.",
        impact=(
            "The description is what an agent reads to decide whether to load the "
            "skill at all. Without it the skill ships and is never selected."
        ),
        failing="name: structured-summary",
        passing=(
            "name: structured-summary\n"
            "description: Summarize a long document into a fixed structure."
        ),
    ),
    "manifest.missing-primary_workflow": CheckExplanation(
        trigger=(
            "The manifest has no primary_workflow, or its primary_workflow is "
            "empty."
        ),
        impact=(
            "The primary workflow is the body of the generated SKILL.md. Without "
            "one there is nothing for the skill to instruct."
        ),
        failing="name: structured-summary",
        passing="name: structured-summary\nprimary_workflow: structured-summary.main",
    ),
    "manifest.unsupported-format-version": CheckExplanation(
        trigger=(
            "The manifest declares a source format_version this compiler does not "
            "support."
        ),
        impact=(
            "The source was written for a different compiler. Building it here "
            "would apply the wrong rules to fields this version does not know."
        ),
        failing="format_version: 2",
        passing="format_version: 1",
    ),
    "manifest.description-length": CheckExplanation(
        trigger="The manifest description is longer than 1024 characters.",
        impact=(
            "The description is loaded on every routing decision, so its length "
            "is a cost every session pays. The limit keeps that cost bounded."
        ),
        failing="description: A very long paragraph of more than 1024 characters ...",
        passing=(
            "description: Summarize a long document into a fixed structure, for "
            "review or handoff."
        ),
    ),
    "manifest.unknown-field": CheckExplanation(
        trigger="The manifest holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so anything it was meant to configure has no "
            "effect. A typo in a field name reads exactly like this."
        ),
        failing="descripton: Summarize a document.",
        passing="description: Summarize a document.",
    ),
    "manifest.derived-field": CheckExplanation(
        trigger=(
            "The manifest declares a field the compiler derives from the skill's "
            "own content, such as entry_kinds."
        ),
        impact=(
            "The declared value is ignored and the derived one is used, so the "
            "manifest states something the bundle does not honor. Remove the "
            "field to keep the source honest about what it controls."
        ),
        failing="entry_kinds:\n  - rule\n  - policy",
        passing="# entry_kinds is derived from the entries themselves",
    ),
    "manifest.unknown-profiles-field": CheckExplanation(
        trigger=(
            "The manifest profiles mapping holds a field other than directory or "
            "defaults."
        ),
        impact=(
            "The field is ignored, so a profile directory or default selection it "
            "was meant to change stays at its default."
        ),
        failing="profiles:\n  default: detailed",
        passing="profiles:\n  defaults:\n    - detailed",
    ),
    # interface: the agent-facing display metadata
    "interface.missing-display_name": CheckExplanation(
        trigger="The manifest interface has no display_name.",
        impact=(
            "The agent host has no name to show for the skill, so the bundle is "
            "incomplete for the interfaces that require one."
        ),
        failing="interface:\n  short_description: Summarize a document for review",
        passing=(
            "interface:\n"
            "  display_name: Structured Summary\n"
            "  short_description: Summarize a document for review"
        ),
    ),
    "interface.missing-short_description": CheckExplanation(
        trigger="The manifest interface has no short_description.",
        impact=(
            "The interface has no one-line summary to present beside the skill's "
            "name."
        ),
        failing="interface:\n  display_name: Structured Summary",
        passing=(
            "interface:\n"
            "  display_name: Structured Summary\n"
            "  short_description: Summarize a document for review"
        ),
    ),
    "interface.missing-default_prompt": CheckExplanation(
        trigger="The manifest interface has no default_prompt.",
        impact=(
            "The interface can offer no suggested invocation, so a reader has to "
            "guess how to start the skill."
        ),
        failing="interface:\n  display_name: Structured Summary",
        passing=(
            "interface:\n"
            "  display_name: Structured Summary\n"
            "  default_prompt: $structured-summary this report"
        ),
    ),
    "interface.invalid-type": CheckExplanation(
        trigger=(
            "An interface field that must be a non-empty string is empty or holds "
            "another type: display_name, short_description, default_prompt, or "
            "brand_color."
        ),
        impact=(
            "The value cannot be presented as declared, so the build stops rather "
            "than emitting an interface the host cannot render."
        ),
        failing="interface:\n  display_name: ''",
        passing="interface:\n  display_name: Structured Summary",
    ),
    "interface.short-description-length": CheckExplanation(
        trigger=(
            "The interface short_description is outside 25-64 characters, the "
            "range agent interfaces display without truncating."
        ),
        impact=(
            "A shorter one says too little to choose the skill by; a longer one is "
            "cut off where the host runs out of room."
        ),
        failing="interface:\n  short_description: Summarize",
        passing="interface:\n  short_description: Summarize a document for review",
    ),
    "interface.default-prompt-token": CheckExplanation(
        trigger=(
            "The interface default_prompt does not contain the exact "
            "$<skill-name> token."
        ),
        impact=(
            "The suggested invocation does not name the skill it invokes, so "
            "following it starts something else."
        ),
        failing="interface:\n  default_prompt: Summarize this report",
        passing="interface:\n  default_prompt: $structured-summary this report",
    ),
    "interface.unknown-field": CheckExplanation(
        trigger="The interface mapping holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so the display detail it was meant to set is "
            "absent from the built bundle."
        ),
        failing="interface:\n  icon_medium: assets/icon.png",
        passing="interface:\n  icon_small: assets/icon.png",
    ),
    # content: which source files the skill compiles
    "content.invalid-type": CheckExplanation(
        trigger=(
            "The manifest content is not a mapping, or one of entries, workflows, "
            "scripts, or assets is not a list of non-empty glob strings, or holds "
            "a pattern that is only the ! exclusion marker."
        ),
        impact=(
            "The compiler cannot tell which files belong to the skill, so it "
            "collects none of them for that group."
        ),
        failing="content:\n  entries: entries/*.yaml",
        passing="content:\n  entries:\n    - entries/*.yaml",
    ),
    "content.outside-skill": CheckExplanation(
        trigger=(
            "A content glob, or a file it matches, resolves outside the skill "
            "directory."
        ),
        impact=(
            "A skill must be self-contained to be installable. A source outside "
            "the directory would be missing from the bundle wherever it is built."
        ),
        failing="content:\n  assets:\n    - ../shared/logo.png",
        passing="content:\n  assets:\n    - assets/logo.png",
    ),
    "content.unknown-field": CheckExplanation(
        trigger=(
            "The content mapping holds a field other than entries, workflows, "
            "scripts, or assets."
        ),
        impact=(
            "The field is ignored, so files it was meant to include are left out "
            "of the bundle while the manifest appears to name them."
        ),
        failing="content:\n  references:\n    - references/*.md",
        passing="content:\n  assets:\n    - references/*.md",
    ),
    # entry: one behavioral entry file
    "entry.missing-id": CheckExplanation(
        trigger="An entry has no id, or its id is empty.",
        impact=(
            "The id names the entry's generated reference file and is how "
            "everything else addresses it. Without one the entry cannot be "
            "compiled at all."
        ),
        failing="rule: State the outcome before the detail.",
        passing=(
            "id: structured-summary.outcome-first\n"
            "rule: State the outcome before the detail."
        ),
    ),
    "entry.missing-rule": CheckExplanation(
        trigger="An entry has no rule, or its rule is empty.",
        impact=(
            "The rule is the behavior the entry establishes. An entry without one "
            "costs tokens to load and instructs nothing."
        ),
        failing="id: structured-summary.outcome-first",
        passing=(
            "id: structured-summary.outcome-first\n"
            "rule: State the outcome before the detail."
        ),
    ),
    "entry.missing-title": CheckExplanation(
        trigger="An entry declares no title.",
        impact=(
            "The always-loaded reference index falls back to showing the entry id, "
            "so a reader chooses between entries by identifier instead of meaning."
        ),
        failing="id: structured-summary.outcome-first",
        passing="id: structured-summary.outcome-first\ntitle: State the outcome first",
    ),
    "entry.missing-kind": CheckExplanation(
        trigger="An entry declares no kind.",
        impact=(
            "The entry compiles as kind rule, which changes its generated "
            "filename, its sort position, and the kind the bundle records."
        ),
        failing="id: structured-summary.outcome-first",
        passing="id: structured-summary.outcome-first\nkind: principle",
    ),
    "entry.unknown-kind": CheckExplanation(
        trigger=(
            "An entry declares a kind outside the set this compiler knows: "
            "principle, policy, heuristic, pattern, constraint, rule."
        ),
        impact=(
            "The entry still compiles with the kind it declares, so source written "
            "for a later compiler builds here. Check the spelling: a typo behaves "
            "the same way."
        ),
        failing="kind: guideline",
        passing="kind: heuristic",
    ),
    "entry.invalid-type": CheckExplanation(
        trigger=(
            "An entry field holds the wrong type: a text field such as title, "
            "rationale, scope, or constraint is not a string, priority is not an "
            "integer, or a list field such as require, allow, reject, conditions, "
            "exceptions, or examples is not a list of non-empty strings."
        ),
        impact=(
            "The field cannot be rendered as declared, so the build stops instead "
            "of emitting a reference whose shape does not match the schema."
        ),
        failing="priority: high\nrequire: Cite the source",
        passing="priority: 10\nrequire:\n  - Cite the source",
    ),
    "entry.no-priorities": CheckExplanation(
        trigger="The skill has entries and none of them declares a priority.",
        impact=(
            "The reference index is ordered by kind then id, which is the "
            "compiler's order rather than the author's. What a reader sees first "
            "is then an accident of naming."
        ),
        failing="# no entry declares a priority",
        passing="id: structured-summary.outcome-first\npriority: 10",
    ),
    "entry.missing-priority": CheckExplanation(
        trigger="Other entries declare a priority and this one does not.",
        impact=(
            "The entry takes the default 100 and sorts below every entry with a "
            "smaller declared priority, which is rarely where an author intended "
            "it."
        ),
        failing="id: structured-summary.cite-sources",
        passing="id: structured-summary.cite-sources\npriority: 20",
    ),
    "entry.duplicate-priority": CheckExplanation(
        trigger="Two or more entries declare the same priority.",
        impact=(
            "Their order falls back to kind then id, so renaming an entry silently "
            "reorders the index."
        ),
        failing="# both entries declare priority: 10",
        passing="# one declares priority: 10, the other priority: 20",
    ),
    "entry.duplicate-title": CheckExplanation(
        trigger="Two or more entries render the same title.",
        impact=(
            "The reference index lists both under one heading, so a reader cannot "
            "tell which entry to open."
        ),
        failing="# two entries titled: Report the outcome",
        passing="# Report the outcome, and Report the outcome of a retry",
    ),
    "entry.unknown-field": CheckExplanation(
        trigger="An entry holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so its content never reaches the generated "
            "reference. A misspelled schema field reads exactly like this."
        ),
        failing="requires:\n  - Cite the source",
        passing="require:\n  - Cite the source",
    ),
    # workflow: one workflow file and its steps
    "workflow.missing-id": CheckExplanation(
        trigger="A workflow has no id, or its id is empty.",
        impact=(
            "The id is how the manifest names the primary workflow and how use "
            "steps reach this one. Without it nothing can reference the workflow."
        ),
        failing="title: Review a summary",
        passing="id: structured-summary.review\ntitle: Review a summary",
    ),
    "workflow.missing-title": CheckExplanation(
        trigger="A workflow declares no title.",
        impact=(
            "The supporting-workflow index links to it by id, so the generated "
            "body offers an identifier where a description belongs."
        ),
        failing="id: structured-summary.review",
        passing="id: structured-summary.review\ntitle: Review a summary",
    ),
    "workflow.missing-description": CheckExplanation(
        trigger="The primary workflow declares no description.",
        impact=(
            "The generated SKILL.md opens with its steps and never states what the "
            "skill is for, which is the first thing its reader needs."
        ),
        failing="id: structured-summary.main",
        passing=(
            "id: structured-summary.main\n"
            "description: Turn a long document into a fixed summary structure."
        ),
    ),
    "workflow.missing-steps": CheckExplanation(
        trigger="A workflow has no steps, or its steps value is not a list.",
        impact=(
            "The steps are the workflow. Without a list there is nothing to "
            "render and nothing to follow."
        ),
        failing="id: structured-summary.review\nsteps: Read the draft",
        passing="id: structured-summary.review\nsteps:\n  - Read the draft",
    ),
    "workflow.invalid-type": CheckExplanation(
        trigger="A workflow title or description is not a string.",
        impact=(
            "The value cannot be rendered as declared, so the build stops rather "
            "than emitting a heading built from another type."
        ),
        failing="title:\n  - Review a summary",
        passing="title: Review a summary",
    ),
    "workflow.invalid-step": CheckExplanation(
        trigger=(
            "A step is not usable: it is an empty string, neither a string nor a "
            "mapping, holds an empty or non-string field, defines none of use, "
            "action, id, or instruction, or combines use with action or "
            "instruction."
        ),
        impact=(
            "The step cannot be rendered as an instruction, so the workflow would "
            "ship with a gap where an action belongs."
        ),
        failing=(
            "steps:\n"
            "  - use: structured-summary.review\n"
            "    instruction: Also check the tone"
        ),
        passing=(
            "steps:\n"
            "  - use: structured-summary.review\n"
            "  - instruction: Check the tone"
        ),
    ),
    "workflow.step-missing-instruction": CheckExplanation(
        trigger=(
            "A step defines neither instruction nor use, so it carries a heading "
            "with no direction."
        ),
        impact=(
            "The step renders as a heading alone. Its reader is told a phase "
            "exists but not what to do in it."
        ),
        failing="steps:\n  - action: Review",
        passing=(
            "steps:\n"
            "  - action: Review\n"
            "    instruction: Compare the summary against the source."
        ),
    ),
    "workflow.unknown-field": CheckExplanation(
        trigger="A workflow holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so anything it was meant to declare has no "
            "effect on the generated workflow."
        ),
        failing="step:\n  - Read the draft",
        passing="steps:\n  - Read the draft",
    ),
    "workflow.unknown-step-field": CheckExplanation(
        trigger=(
            "A step holds a field other than id, action, instruction, when, or "
            "use."
        ),
        impact=(
            "The field is ignored, so a condition or instruction it was meant to "
            "carry never reaches the generated step."
        ),
        failing="steps:\n  - action: Review\n    if: the draft changed",
        passing="steps:\n  - action: Review\n    when: the draft changed",
    ),
    "workflow.duplicate-id": CheckExplanation(
        trigger="Two workflow files declare the same id.",
        impact=(
            "A use step naming that id cannot say which workflow it means, and "
            "only one of the two would reach the bundle."
        ),
        failing="# workflows/review.yaml and workflows/check.yaml both declare\n"
        "id: structured-summary.review",
        passing="# review.yaml declares .review, check.yaml declares .check",
    ),
    "workflow.missing-primary": CheckExplanation(
        trigger=(
            "The manifest primary_workflow names an id no workflow in this skill "
            "declares."
        ),
        impact=(
            "The primary workflow becomes the body of the generated SKILL.md, so "
            "no bundle can be produced until the id resolves. Check the id "
            "spelling and that the content globs include the file."
        ),
        failing="primary_workflow: structured-summary.man",
        passing="primary_workflow: structured-summary.main",
    ),
    "workflow.unknown-reference": CheckExplanation(
        trigger=(
            "A step's use names a workflow id that does not exist in this skill, "
            "including an id that belongs to another skill."
        ),
        impact=(
            "A skill must be self-contained. The step would reference a workflow "
            "the installed bundle does not contain."
        ),
        failing="steps:\n  - use: other-skill.review",
        passing="steps:\n  - use: structured-summary.review",
    ),
    "workflow.unreachable": CheckExplanation(
        trigger=(
            "No chain of use steps reaches this workflow from the primary "
            "workflow."
        ),
        impact=(
            "The workflow still ships and still costs bytes in the "
            "supporting-workflow index, but nothing invokes it."
        ),
        failing="# workflows/review.yaml is never named by a use step",
        passing="steps:\n  - use: structured-summary.review",
    ),
    # profile: an optional profile source and its selection
    "profile.missing-name": CheckExplanation(
        trigger="A profile has no name, or its name is empty.",
        impact=(
            "The name is the profile's selector and its generated filename, so "
            "--profile cannot address it."
        ),
        failing="label: Detailed",
        passing="name: detailed\nlabel: Detailed",
    ),
    "profile.name-mismatch": CheckExplanation(
        trigger="A profile name is not the stem of its own filename.",
        impact=(
            "The selector an author reads from the filename would not match the "
            "one the profile declares, so --profile would appear to be wrong."
        ),
        failing="# profiles/detailed.yaml\nname: verbose",
        passing="# profiles/detailed.yaml\nname: detailed",
    ),
    "profile.invalid-name": CheckExplanation(
        trigger=(
            "A profile name is not 1-64 lowercase letters, digits, and single "
            "hyphens, or it is the reserved name all."
        ),
        impact=(
            "Profile names follow the same syntax as skill names because both are "
            "selectors; all is reserved for selecting every profile."
        ),
        failing="name: All",
        passing="name: detailed",
    ),
    "profile.missing-label": CheckExplanation(
        trigger="A profile has no label, or its label is empty.",
        impact=(
            "The label is the heading of the generated profile reference, so the "
            "generated file would open unnamed."
        ),
        failing="name: detailed",
        passing="name: detailed\nlabel: Detailed review",
    ),
    "profile.missing-description": CheckExplanation(
        trigger="A profile has no description, or its description is empty.",
        impact=(
            "The description is the guidance SKILL.md shows for choosing between "
            "profiles. Without it the profile ships and is never selected."
        ),
        failing="name: detailed",
        passing=(
            "name: detailed\n"
            "description: Use for a full review that names every finding."
        ),
    ),
    "profile.description-length": CheckExplanation(
        trigger=(
            "A profile description is empty or longer than 1024 characters."
        ),
        impact=(
            "Profile descriptions are read together when a profile is chosen, so "
            "each one's length is a cost paid on every selection."
        ),
        failing="description: A very long paragraph of more than 1024 characters ...",
        passing="description: Use for a full review that names every finding.",
    ),
    "profile.missing-instructions": CheckExplanation(
        trigger=(
            "A profile has no instructions, or its instructions are not a "
            "non-empty list of non-empty strings."
        ),
        impact=(
            "The instructions are what selecting the profile adds. Without them "
            "the profile changes nothing about the skill's behavior."
        ),
        failing="name: detailed\ninstructions: Name every finding",
        passing="name: detailed\ninstructions:\n  - Name every finding",
    ),
    "profile.invalid-type": CheckExplanation(
        trigger=(
            "A profile details value is not a string, or details_files is not a "
            "non-empty list of non-empty strings."
        ),
        impact=(
            "The additional reference content cannot be assembled, so the build "
            "stops rather than emitting a profile without the detail it declares."
        ),
        failing="details_files: references/detailed.md",
        passing="details_files:\n  - references/detailed.md",
    ),
    "profile.details-conflict": CheckExplanation(
        trigger="A profile declares both details and details_files.",
        impact=(
            "The two are mutually exclusive, so the source states two sources for "
            "one generated section and the build cannot choose between them."
        ),
        failing="details: Inline Markdown\ndetails_files:\n  - references/detailed.md",
        passing="details_files:\n  - references/detailed.md",
    ),
    "profile.detail-missing": CheckExplanation(
        trigger="A profile names a detail file that does not exist.",
        impact=(
            "The generated profile reference would be missing the content the "
            "profile promises. Paths are relative to the profile source."
        ),
        failing="details_files:\n  - references/detailled.md",
        passing="details_files:\n  - references/detailed.md",
    ),
    "profile.detail-not-markdown": CheckExplanation(
        trigger="A profile names a detail file without a .md extension.",
        impact=(
            "Detail files are appended to generated Markdown, so only Markdown "
            "sources can be included."
        ),
        failing="details_files:\n  - references/detailed.txt",
        passing="details_files:\n  - references/detailed.md",
    ),
    "profile.detail-outside-skill": CheckExplanation(
        trigger="A profile detail file resolves outside the skill directory.",
        impact=(
            "A skill must be self-contained. Content from outside the directory "
            "would be missing wherever the skill is built."
        ),
        failing="details_files:\n  - ../../shared/detailed.md",
        passing="details_files:\n  - references/detailed.md",
    ),
    "profile.detail-heading": CheckExplanation(
        trigger=(
            "A profile's details, or the Markdown of a detail file, contains a "
            "level-one heading."
        ),
        impact=(
            "Degardis writes the level-one heading of the generated profile "
            "reference itself, so a second one produces two competing titles in "
            "one file."
        ),
        failing="details: |\n  # Detailed review\n  Name every finding.",
        passing="details: |\n  ## Detailed review\n  Name every finding.",
    ),
    "profile.unknown-field": CheckExplanation(
        trigger="A profile holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so its content never reaches the generated "
            "profile reference."
        ),
        failing="instruction:\n  - Name every finding",
        passing="instructions:\n  - Name every finding",
    ),
    "profile.invalid-directory": CheckExplanation(
        trigger=(
            "The manifest profiles mapping is not a mapping, its directory is not "
            "a non-empty string, or the directory resolves outside the skill."
        ),
        impact=(
            "No profile source can be located, so the skill builds with no "
            "profiles even where profile files exist."
        ),
        failing="profiles:\n  directory: ../shared-profiles",
        passing="profiles:\n  directory: profiles",
    ),
    "profile.unknown-selector": CheckExplanation(
        trigger=(
            "A --profile selector matches no selected skill, or qualifies a skill "
            "the command did not select."
        ),
        impact=(
            "The build would quietly omit a profile the caller asked for, so the "
            "selector is rejected instead."
        ),
        failing="degardis build ./structured-summary --profile other-skill:detailed",
        passing="degardis build ./structured-summary --profile detailed",
    ),
    "profile.unsupported": CheckExplanation(
        trigger="A file that is not a .yaml source is loaded as a profile.",
        impact=(
            "Profiles are YAML sources. Any other file would be read with the "
            "wrong schema."
        ),
        failing="# profiles/detailed.json",
        passing="# profiles/detailed.yaml",
    ),
    # output: the files a build would write
    "output.path-collision": CheckExplanation(
        trigger=(
            "Two sources would be written to the same path in the bundle, "
            "compared without regard to letter case."
        ),
        impact=(
            "One file would overwrite the other, and which one survives depends on "
            "the filesystem. Entry and workflow ids, profile names, scripts, "
            "assets, and generated icons all claim paths in one namespace."
        ),
        failing="# entries/report.yaml declares id: demo.Report\n"
        "# entries/report-2.yaml declares id: demo.report",
        passing="# demo.report-outcome and demo.report-format",
    ),
    "output.invalid-filename": CheckExplanation(
        trigger=(
            "An entry or workflow id produces no filename at all once its skill "
            "and kind prefixes and unsupported characters are removed."
        ),
        impact=(
            "The generated reference has no file to be written to, so the entry or "
            "workflow cannot ship."
        ),
        failing="id: structured-summary.rule.",
        passing="id: structured-summary.rule.outcome-first",
    ),
    "output.render-failed": CheckExplanation(
        trigger=(
            "Generating SKILL.md from the resolved source raises once rendering "
            "starts, which is reported as a diagnostic rather than as a crash."
        ),
        impact=(
            "No bundle can be produced and no size can be measured. The message "
            "carries the underlying failure; in practice this is a manifest field "
            "such as license or copyright whose invalid type is already reported "
            "separately, since the primary workflow itself must already resolve "
            "before rendering is attempted."
        ),
        failing="license: 42",
        passing="license: MIT",
    ),
    "output.broken-reference": CheckExplanation(
        trigger=(
            "The generated SKILL.md links to a path the bundle would not write."
        ),
        impact=(
            "An installed skill would offer its reader a reference that cannot be "
            "opened. This checks generated output against the resolved source "
            "rather than one authored field, so report it with the source that "
            "produced it."
        ),
        failing="# SKILL.md links references/entries/outcome-first.md",
        passing="# the bundle writes references/entries/outcome-first.md",
    ),
    # icon: interface images
    "icon.invalid-path": CheckExplanation(
        trigger=(
            "An interface icon, icon_small, or icon_large is empty, is not a "
            "string, or is an absolute path."
        ),
        impact=(
            "Icon paths are read relative to the skill directory so one build "
            "behaves like the next. An absolute path names a file that exists on "
            "one machine."
        ),
        failing="interface:\n  icon: /home/author/logo.png",
        passing="interface:\n  icon: assets/logo.png",
    ),
    "icon.not-found": CheckExplanation(
        trigger="An interface icon path names a file that does not exist.",
        impact=(
            "The build converts each declared icon into the bundle, so there is "
            "nothing to convert. A path may resolve outside the skill directory, "
            "which lets several skills share one source image, so check the path "
            "as well as the file."
        ),
        failing="interface:\n  icon: assets/logo.png",
        passing="interface:\n  icon: assets/icon.png",
    ),
    "icon.unsupported": CheckExplanation(
        trigger=(
            "An interface icon cannot be decoded as an image: it is not a "
            "supported format, its SVG markup does not parse, or the image it "
            "carries has no usable dimensions."
        ),
        impact=(
            "Icons are converted to PNG at build time. A source that cannot be "
            "read stops the build rather than shipping a skill whose icons the "
            "host cannot render."
        ),
        failing="interface:\n  icon: assets/logo.pdf",
        passing="interface:\n  icon: assets/logo.svg",
    ),
    "icon.too-large": CheckExplanation(
        trigger=(
            "An interface icon source is over 10 MiB, or its image is over "
            "67,108,864 pixels."
        ),
        impact=(
            "Both limits bound what one build has to decode and what an installed "
            "bundle carries. Resize the source rather than relying on the "
            "conversion to shrink it."
        ),
        failing="interface:\n  icon: assets/photo-12000x9000.png",
        passing="interface:\n  icon: assets/icon-512x512.png",
    ),
    "icon.unsafe": CheckExplanation(
        trigger=(
            "An SVG icon carries a script element, a foreignObject element, an "
            "external href, or an external CSS url()."
        ),
        impact=(
            "A bundle is installed and rendered by someone else's agent host, so "
            "an icon that fetches or executes anything is a risk carried to every "
            "reader. Inline what the image needs, as markup or a data: URI."
        ),
        failing='<svg><image href="https://example.com/logo.png"/></svg>',
        passing='<svg><path d="M8 0 L16 16 H0 Z"/></svg>',
    ),
    "icon.unreadable": CheckExplanation(
        trigger=(
            "An interface icon's path itself fails to resolve at the filesystem "
            "level, before its bytes are ever opened - for example a symlink loop "
            "the operating system refuses to follow further."
        ),
        impact=(
            "The failure is in reaching the path rather than in the image it "
            "names: a source that resolves but cannot be opened or decoded is "
            "icon.unsupported instead. The message carries what the filesystem "
            "reported."
        ),
        failing="# assets/icon.png reached through a symlink loop the filesystem refuses to resolve",
        passing="# assets/icon.png reached through an ordinary path",
    ),
}


def explanation(code: str) -> CheckExplanation | None:
    """The entry for one check code, or None when the code is not known."""
    return CHECKS.get(code)


def known_codes() -> list[str]:
    return sorted(CHECKS)


def codes_by_namespace() -> dict[str, list[str]]:
    """Known codes grouped by the construct their namespace names."""
    grouped: dict[str, list[str]] = {}
    for code in known_codes():
        namespace, _, name = code.partition(".")
        grouped.setdefault(namespace, []).append(name)
    return grouped


def known_codes_message() -> str:
    """List every explainable code, one namespace at a time, for an error path."""
    lines = ["Known codes:"]
    for namespace, names in codes_by_namespace().items():
        codes = ", ".join(f"{namespace}.{name}" for name in names)
        lines.extend(
            fill(
                codes,
                width=100,
                initial_indent="  ",
                subsequent_indent="  ",
                break_long_words=False,
                break_on_hyphens=False,
            ).splitlines()
        )
    return "\n".join(lines)
