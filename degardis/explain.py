"""What each check code means, for a reader who has the package but not its source.

Every diagnostic carries a code and one line of message. The line is enough to
locate the problem; it is not enough to decide whether the problem matters, or
what the source should say instead. This table answers both, and is written by
hand rather than derived from the checks: a check knows the condition it tests,
not why an author should care.

A code is `<namespace>.<check>`, and the check reads as hyphenated words with one
exception: where it names a field of the source, it spells that field exactly as
the key does. `interface.missing-short_description` and
`interface.short_description-length` both carry `short_description` because the
manifest key is `short_description`. A reader who knows the key can therefore
build the code rather than look it up.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import fill

from .model import CURRENT_FORMAT_VERSION


@dataclass(frozen=True)
class CheckExplanation:
    """One check code, in the terms an author or agent has to act on."""

    trigger: str
    impact: str
    failing: str
    passing: str


# Keyed by check code, grouped by the namespace the code belongs to. Every code
# any check can report has an explanation here; tests hold this table to that.
CHECKS: dict[str, CheckExplanation] = {
    # ------------------------------------------------------------ source
    "source.archive-input": CheckExplanation(
        trigger="A command was pointed at a .zip file rather than a directory.",
        impact=(
            "Degardis reads authored sources from a directory and writes "
            "archives; it never reads one back. The command stops rather than "
            "reporting an empty skill."
        ),
        failing="degardis validate .artifacts/structured-summary.zip",
        passing="degardis validate examples/structured-summary",
    ),
    "source.cross-kind-reference": CheckExplanation(
        trigger=(
            'A reference names a construct the manifest selects under a '
            'different content key: a rule where a policy is expected, or the '
            'reverse.'
        ),
        impact=(
            'The kinds are not interchangeable, because each has its own '
            'execution meaning. Name the id under the key that matches what '
            'you want bound.'
        ),
        failing='policies:\n- stay-in-scope   # selected by content.rules',
        passing='rules:\n- stay-in-scope',
    ),
    "source.duplicate-id": CheckExplanation(
        trigger=(
            'Two selected files of one construct kind have the same file '
            'stem.'
        ),
        impact=(
            "The stem is the construct's identity, so two files claiming one "
            'id leave every reference to it ambiguous. Rename one; moving a '
            'file keeps its id, and renaming it changes it.'
        ),
        failing='# rules/scope.yaml and rules/nested/scope.yaml',
        passing='# rules/scope.yaml and rules/nested/call-scope.yaml',
    ),
    "source.generated-bundle": CheckExplanation(
        trigger=(
            "A command was pointed at a directory holding SKILL.md and no "
            "skill.yaml, which is what a build writes rather than what an author "
            "edits."
        ),
        impact=(
            "The command stops instead of descending into the bundle, where it "
            "would find whatever skill.yaml a skill ships as a template asset "
            "and report a pass for a skill nobody named."
        ),
        failing="degardis validate .artifacts/structured-summary",
        passing="degardis validate examples/structured-summary",
    ),
    "source.invalid-name": CheckExplanation(
        trigger=(
            'A selected source filename is not lowercase letters, digits, and '
            'single hyphens.'
        ),
        impact=(
            "The file stem is the construct's id, so a stem that cannot be an "
            'id leaves the construct unnameable and every reference to it '
            'unresolvable. Rename the file; moving it later keeps the id, and '
            'renaming it changes the id.'
        ),
        failing='# rules/Preserve_Contract.yaml',
        passing='# rules/preserve-contract.yaml',
    ),
    "source.invalid-yaml": CheckExplanation(
        trigger=(
            "A manifest, rule, workflow, or profile file does not parse as "
            "YAML, parses as something other than a mapping of fields, or uses "
            "a non-string mapping field name."
        ),
        impact=(
            "Nothing in the file reaches the bundle. The message names the line "
            "and what YAML did with the text, which is usually an unquoted value "
            "holding a character YAML reserves."
        ),
        failing="rule: Report the outcome: pass or fail",
        passing='rule: "Report the outcome: pass or fail"',
    ),
    "source.rejected-yaml": CheckExplanation(
        trigger=(
            'A source uses YAML beyond the profile Format 2 accepts: an '
            'anchor, an alias, a merge key, a type tag, a bare date read as a '
            'timestamp, a non-finite number, a repeated field, or a non- '
            'string field name.'
        ),
        impact=(
            'Each of these makes the value the compiler reads differ from the '
            'text on the page, and the difference is invisible in review. '
            'Write the fields out, and quote a value YAML would read as '
            'another type.'
        ),
        failing='defaults: &base\n  phase: before\nprovision:\n  <<: *base',
        passing='provision:\n  phase: before',
    ),
    "source.unbound-construct": CheckExplanation(
        trigger=(
            'A selected construct is reached by nothing this run can execute.'
        ),
        impact=(
            'The bundle ships a page no agent meets. Either bind it — at the '
            'manifest, a workflow, or a step — or drop it from the content '
            'patterns so the bundle stops carrying it.'
        ),
        failing=(
            'content:\n  policies:\n  - policies/**/*.yaml   # and no scope names one'
        ),
        passing='policies:\n- request-authority',
    ),
    "source.unknown-reference": CheckExplanation(
        trigger=(
            'A manifest, workflow, or step names a construct id that no '
            'content pattern selects.'
        ),
        impact=(
            'Nothing resolves the reference, so whatever it was meant to bind '
            'is bound nowhere. Check the file stem and that a `content` '
            'pattern reaches its directory.'
        ),
        failing=(
            'primary_workflow: perform-task\ncontent:\n  workflows:\n  - workflows/deliver.yaml'
        ),
        passing=(
            'primary_workflow: deliver\ncontent:\n  workflows:\n  - workflows/deliver.yaml'
        ),
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
    "source.unsupported": CheckExplanation(
        trigger=(
            'A content pattern selected a file the construct reader cannot '
            'read, such as a Markdown guide swept in by a pattern meant for '
            'YAML.'
        ),
        impact=(
            'The file is not a construct source, so nothing in it is read. '
            'Narrow the pattern: `profiles/*.yaml` selects the profiles '
            'without their guide files, where `profiles/**/*` sweeps both in.'
        ),
        failing='content:\n  profiles:\n  - profiles/**/*',
        passing='content:\n  profiles:\n  - profiles/*.yaml',
    ),
    # -------------------------------------------------------------- yaml
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
        failing="confirm: no",
        passing='confirm: "no"',
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
        failing="rationale: Retry at 10:30",
        passing='rationale: "Retry at 10:30"',
    ),
    # ---------------------------------------------------------- manifest
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
    "manifest.duplicate-binding": CheckExplanation(
        trigger='A manifest binding list names one construct more than once.',
        impact=(
            'The second mention binds nothing the first did not, so it is '
            'either a typo or a leftover. Name each construct once.'
        ),
        failing='policies:\n- request-authority\n- request-authority',
        passing='policies:\n- request-authority',
    ),
    "manifest.invalid-format_version": CheckExplanation(
        trigger=(
            "The manifest declares a format_version integer of zero or "
            "below, before this versioning scheme begins."
        ),
        impact=(
            "No compiler, current or earlier, has ever read this value, so "
            "there is nothing to interpret or convert."
        ),
        failing="format_version: 0",
        passing=f"format_version: {CURRENT_FORMAT_VERSION}",
    ),
    "manifest.invalid-name": CheckExplanation(
        trigger=(
            "The manifest name is not 1-64 lowercase letters, digits, and single "
            "hyphens."
        ),
        impact=(
            "The name is the skill's directory and its selector, so nothing "
            "addresses the skill reliably until it is valid."
        ),
        failing="name: Structured_Summary",
        passing="name: structured-summary",
    ),
    "manifest.invalid-type": CheckExplanation(
        trigger=(
            "A manifest field holds the wrong type: format_version is not an "
            "integer, license or copyright is not a non-empty string, or "
            "interface is not the mapping the schema states."
        ),
        impact=(
            "The field cannot be used as declared, so the build stops rather than "
            "guessing what the value was meant to be."
        ),
        failing="format_version: '1'",
        passing="format_version: 1",
    ),
    "manifest.missing": CheckExplanation(
        trigger='A path selected as a skill holds no `skill.yaml`.',
        impact=(
            'There is no manifest to read, so nothing identifies the skill or '
            'selects its sources. Point the path at the skill directory, or '
            'at a collection directory that contains one.'
        ),
        failing='degardis validate ./skills/without-a-manifest',
        passing='degardis validate ./skills/perform-task   # holds skill.yaml',
    ),
    "manifest.missing-content": CheckExplanation(
        trigger="The manifest declares no content.",
        impact=(
            "Nothing selects the source files, so no construct is read and "
            "there is nothing to compile. Declare content, selecting at least "
            "the workflows."
        ),
        failing="name: example-skill\\nversion: 1.0.0",
        passing=(
            "name: example-skill\\nversion: 1.0.0\\ncontent:\\n  workflows:\\n"
            "  - workflows/**/*.yaml"
        ),
    ),
    "manifest.missing-description": CheckExplanation(
        trigger="The manifest declares no description.",
        impact=(
            "The description is what a host reads to decide whether to select "
            "the skill, and it opens the generated document. State what the "
            "skill does in one sentence."
        ),
        failing="name: example-skill\\nversion: 1.0.0",
        passing=(
            "name: example-skill\\nversion: 1.0.0\\n"
            "description: Perform one bounded task through a validated workflow."
        ),
    ),
    "manifest.missing-format_version": CheckExplanation(
        trigger="The manifest declares no format_version.",
        impact=(
            "Nothing establishes which source format the files are written in, "
            "so the compiler cannot choose the schemas to read them against. "
            f"Declare format_version: {CURRENT_FORMAT_VERSION}."
        ),
        failing="name: example-skill\\nversion: 1.0.0",
        passing=(
            f"name: example-skill\\nformat_version: {CURRENT_FORMAT_VERSION}\\n"
            "version: 1.0.0"
        ),
    ),
    "manifest.missing-interface": CheckExplanation(
        trigger="The manifest declares no interface.",
        impact=(
            "The bundle carries no display metadata, so a host has no name or "
            "summary to show. Declare interface with display_name, "
            "short_description, and default_prompt."
        ),
        failing="name: example-skill\\nversion: 1.0.0",
        passing=(
            "name: example-skill\\nversion: 1.0.0\\ninterface:\\n"
            "  display_name: Example Skill\\n"
            "  short_description: Perform one validated task\\n"
            "  default_prompt: Use {name} for this request."
        ),
    ),
    "manifest.missing-name": CheckExplanation(
        trigger='The manifest declares no name.',
        impact=(
            'Discovery identifies a skill by its manifest name before any '
            'other check runs, so without one nothing can be reported against '
            'it. Declare the name, matching the skill directory.'
        ),
        failing='format_version: 2\nversion: 1.0.0',
        passing='name: example-skill\nformat_version: 2\nversion: 1.0.0',
    ),
    "manifest.missing-primary_workflow": CheckExplanation(
        trigger="The manifest declares no primary_workflow.",
        impact=(
            "Nothing names the workflow a run enters, so the document has no "
            "entry point and no call order to render. Name the file stem of the "
            "workflow a run starts in."
        ),
        failing="name: example-skill\\nversion: 1.0.0",
        passing="name: example-skill\\nversion: 1.0.0\\nprimary_workflow: perform-task",
    ),
    "manifest.missing-version": CheckExplanation(
        trigger="The manifest declares no version.",
        impact=(
            "The bundle carries no release identity, so an installed skill "
            "cannot be told from the one it replaced. Declare the skill's own "
            "release version."
        ),
        failing="name: example-skill\\ndescription: Perform one bounded task.",
        passing=(
            "name: example-skill\\ndescription: Perform one bounded task.\\n"
            "version: 1.0.0"
        ),
    ),
    "manifest.name-mismatch": CheckExplanation(
        trigger='The manifest name and the skill directory name differ.',
        impact=(
            'A bundle is written to a directory named by the manifest, so the '
            'two disagreeing means the source directory and the artifact '
            'would not correspond. Rename one to match the other.'
        ),
        failing='# skills/example/skill.yaml\nname: sample-skill',
        passing='# skills/example/skill.yaml\nname: example',
    ),
    "manifest.obsolete-format_version": CheckExplanation(
        trigger=(
            "The manifest declares a source format_version older than this "
            f"installed compiler reads ({CURRENT_FORMAT_VERSION})."
        ),
        impact=(
            "An earlier format's sources never carried the typed inputs, "
            "declared outcomes, gates, and graph edges this one validates, "
            "so they are not derivable from it. The source should be rewritten."
        ),
        failing=f"format_version: {CURRENT_FORMAT_VERSION - 1}",
        passing=f"format_version: {CURRENT_FORMAT_VERSION}",
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
    "manifest.unreadable": CheckExplanation(
        trigger=(
            'Reading a manifest failed in a way no source check names, such '
            'as a filesystem or decoding error.'
        ),
        impact=(
            'The skill is reported as unreadable rather than crashing with a '
            'traceback. The message carries what the operating system said; '
            'the repair is usually permissions, encoding, or a partial copy.'
        ),
        failing='# skill.yaml written in UTF-16 with no BOM',
        passing='# skill.yaml written in UTF-8',
    ),
    "manifest.unsupported-format_version": CheckExplanation(
        trigger=(
            "The manifest declares a source format_version newer than this "
            "installed compiler reads."
        ),
        impact=(
            "The source was written for a later compiler. Install a newer "
            "degardis release to read it; this one would apply the wrong "
            "rules to fields this version does not know."
        ),
        failing=f"format_version: {CURRENT_FORMAT_VERSION + 1}",
        passing=f"format_version: {CURRENT_FORMAT_VERSION}",
    ),
    # --------------------------------------------------------- interface
    "interface.default_prompt-literal-token": CheckExplanation(
        trigger=(
            "The interface default_prompt spells one host's invocation syntax, "
            "such as $<skill-name> or /<skill-name>, where the {name} "
            "placeholder belongs."
        ),
        impact=(
            "The spelled syntax is emitted verbatim to every target, so the "
            "suggested invocation is wrong on each host that types a skill name "
            "differently, and the source cannot follow a host that changes its "
            "own."
        ),
        failing="interface:\n  default_prompt: Ask $structured-summary to summarize this",
        passing="interface:\n  default_prompt: Ask {name} to summarize this",
    ),
    "interface.default_prompt-token": CheckExplanation(
        trigger=(
            "The interface default_prompt does not contain the exact {name} "
            "placeholder, which each target replaces with the skill name in its "
            "own invocation syntax."
        ),
        impact=(
            "The suggested invocation does not name the skill it invokes, so "
            "following it starts something else. This is a warning: the bundle "
            "still builds, because a source written before the placeholder "
            "convention has to keep converting."
        ),
        failing="interface:\n  default_prompt: Summarize this report",
        passing="interface:\n  default_prompt: Use {name} to summarize this report",
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
    "interface.short_description-length": CheckExplanation(
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
    "interface.unknown-field": CheckExplanation(
        trigger="The interface mapping holds a field this compiler does not define.",
        impact=(
            "The field is ignored, so the display detail it was meant to set is "
            "absent from the built bundle."
        ),
        failing="interface:\n  icon_medium: assets/icon.png",
        passing="interface:\n  icon_small: assets/icon.png",
    ),
    # ----------------------------------------------------------- content
    "content.empty-selection": CheckExplanation(
        trigger=(
            "A content key the manifest declares resolves to no file, because "
            "its patterns select none or an exclusion removes them all."
        ),
        impact=(
            "Declaring the key states that the skill ships that content, and the "
            "bundle would ship none of it. Nothing else reports this: no rule, "
            "profile, script, or asset has to be referenced from anywhere, so "
            "one that never arrives simply disappears from the built skill. "
            "Leave the key out to ship none of that content on purpose."
        ),
        failing=(
            "content:\n"
            "  assets:\n"
            "    - assets/**/*\n"
            '    - "!assets/**/*"'
        ),
        passing="content:\n  assets:\n    - assets/**/*",
    ),
    "content.invalid-type": CheckExplanation(
        trigger=(
            "The manifest content is not a mapping, or one of rules, workflows, "
            "profiles, scripts, or assets is not a list of non-empty glob "
            "strings, or holds a pattern that is only the ! exclusion marker."
        ),
        impact=(
            "The compiler cannot tell which files belong to the skill, so it "
            "collects none of them for that group."
        ),
        failing="content:\n  rules: rules/*.yaml",
        passing="content:\n  rules:\n    - rules/*.yaml",
    ),
    "content.missing-workflows": CheckExplanation(
        trigger="The manifest's content selects no workflows.",
        impact=(
            "A skill with no workflow has no execution to render, so SKILL.md "
            "would have nothing to contain. Select at least one workflow "
            "pattern."
        ),
        failing="content:\\n  rules:\\n  - rules/**/*.yaml",
        passing=(
            "content:\\n  rules:\\n  - rules/**/*.yaml\\n  workflows:\\n"
            "  - workflows/**/*.yaml"
        ),
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
            "The content mapping holds a field other than rules, workflows, "
            "profiles, scripts, or assets."
        ),
        impact=(
            "The field is ignored, so files it was meant to include are left out "
            "of the bundle while the manifest appears to name them."
        ),
        failing="content:\n  references:\n    - references/*.md",
        passing="content:\n  assets:\n    - references/*.md",
    ),
    "content.unmatched-pattern": CheckExplanation(
        trigger=(
            "A content pattern names nothing that exists in the skill directory."
        ),
        impact=(
            "The pattern does nothing, and only this check says so: a selection "
            "that matches nothing leaves files out of the bundle, and an "
            "exclusion that matches nothing leaves files in it. Patterns are "
            "matched case-sensitively and separated by / on every platform, so "
            "check the spelling of each segment before the path itself."
        ),
        failing="content:\n  rules:\n    - rules/*.yml",
        passing="content:\n  rules:\n    - rules/*.yaml",
    ),
    # ------------------------------------------------------------ policy
    "policy.invalid-provision": CheckExplanation(
        trigger=(
            'A provision declares a field the provision schema does not have, '
            'no phase or an unknown one, no selector, or neither or both of '
            '`require` and `prohibit`.'
        ),
        impact=(
            'The provision is not read, so the boundary it states is bound '
            'nowhere. A provision declares phase, match, when, unless, '
            'exactly one of require and prohibit, and verify.'
        ),
        failing=(
            'provisions:\n  establish:\n    phase: before\n    require: Establish the authority.'
        ),
        passing=(
            'provisions:\n  establish:\n    phase: before\n    match:\n      effects: [external.*]\n    require: Establish the authority.'
        ),
    ),
    "policy.invalid-shape": CheckExplanation(
        trigger=(
            "A policy file gives a field a value of the wrong shape: a summary "
            "that is not a non-empty string, an empty provisions mapping, or a "
            "provision key that is not lowercase-hyphenated."
        ),
        impact=(
            "The policy is not read, so nothing it says is bound anywhere. A "
            "field that is absent rather than malformed reports its own check "
            "instead, naming the key: policy.missing-summary or "
            "policy.missing-provisions."
        ),
        failing="summary: Keep external effects within authority.\\nprovisions: {}",
        passing=(
            "summary: Keep external effects within authority.\\n"
            "provisions:\\n  establish-authority:\\n    phase: before\\n"
            "    match:\\n      effects: [external.*]\\n"
            "    require: Establish the authority for the external effect."
        ),
    ),
    "policy.missing-provisions": CheckExplanation(
        trigger="A policy file declares no provisions.",
        impact=(
            "A policy is its provisions: with none, nothing is bound at any "
            "node and the file constrains nothing. Declare at least one "
            "provision."
        ),
        failing="summary: Keep external effects within established authority.",
        passing=(
            "summary: Keep external effects within established authority.\\n"
            "provisions:\\n  establish-authority:\\n    phase: before\\n"
            "    match:\\n      effects: [external.*]\\n"
            "    require: Establish the authority for the external effect."
        ),
    ),
    "policy.missing-summary": CheckExplanation(
        trigger="A policy file declares no summary.",
        impact=(
            "Nothing states the boundary the provisions share, so a reader of "
            "the source cannot tell what authority they belong to. State the "
            "boundary in one sentence."
        ),
        failing="title: External action authority\\nprovisions:\\n  establish: ...",
        passing=(
            "summary: Keep external effects within established authority.\\n"
            "provisions:\\n  establish: ..."
        ),
    ),
    "policy.unknown-field": CheckExplanation(
        trigger="A policy file declares a field the policy schema does not have.",
        impact=(
            "The field is read by nothing, so whatever it was meant to say has "
            "no effect. A policy declares title, summary, and provisions."
        ),
        failing=(
            "summary: Keep external effects within authority.\\n"
            "prefer: The smallest external effect."
        ),
        passing="summary: Keep external effects within authority.",
    ),
    "policy.unlowered-provision": CheckExplanation(
        trigger=(
            'An active provision matched a reached node and reached no '
            'generated node. A `during` provision selecting only a decision, '
            'a gate, or a branch is the usual cause.'
        ),
        impact=(
            'The requirement is in no installed page, so the agent executing '
            'the skill is never told it. The message names the phase and the '
            'node form that refused it: a `during` item renders beside a '
            'command, so select an action, a call, a pattern, or a return, or '
            'move it to `before`.'
        ),
        failing='phase: during\nmatch:\n  forms: [gate]',
        passing='phase: before\nmatch:\n  forms: [gate]',
    ),
    "policy.unmatched-provision": CheckExplanation(
        trigger=(
            "A bound provision's selector matches no reachable node at its "
            'phase.'
        ),
        impact=(
            'Nothing enforces it: the policy is bound and the provision '
            'reaches no step. Usually the step is missing the subject or '
            'effect tag the selector names. This warns rather than fails, '
            'because shipping a provision before the step it will constrain '
            'is what mid-design work looks like; `--fail-on-warning` refuses '
            'it.'
        ),
        failing=(
            'match:\n  subjects: [checklist.write]   # no step declares it'
        ),
        passing='# on the step\nsubjects: [checklist.write]',
    ),
    # -------------------------------------------------------------- rule
    "rule.invalid-shape": CheckExplanation(
        trigger=(
            "A rule file gives a field a value of the wrong shape: a phase that "
            "is not one of the four, a match that is not a selector, both "
            "require and prohibit at once, or a malformed verification."
        ),
        impact=(
            "The rule is not read, so the conditional relation it states is "
            "enforced nowhere. A field that is absent rather than malformed "
            "reports its own check instead, naming the key: "
            "rule.missing-phase, rule.missing-match, or rule.missing-command."
        ),
        failing=(
            "summary: Keep the contract stable.\\nphase: eventually\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
        passing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.missing-command": CheckExplanation(
        trigger="A rule file declares neither require nor prohibit.",
        impact=(
            "One binding command is what makes a rule act, so a rule with "
            "neither states nothing for an agent to do. Declare exactly one of "
            "require and prohibit."
        ),
        failing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]"
        ),
        passing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.missing-match": CheckExplanation(
        trigger="A rule file declares no match.",
        impact=(
            "The selector is what says which nodes the rule applies to, so "
            "without it nothing selects the rule and it is enforced nowhere. "
            "Declare a selector, or {all: true} to bind every node in scope."
        ),
        failing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "require: Preserve the existing public contract."
        ),
        passing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.missing-phase": CheckExplanation(
        trigger="A rule file declares no phase.",
        impact=(
            "The phase is where the check sits relative to the node it "
            "constrains, so without it the compiler has nowhere to lower the "
            "rule. Declare before, during, after, or before-return."
        ),
        failing=(
            "summary: Keep the contract stable.\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
        passing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.missing-summary": CheckExplanation(
        trigger="A rule file declares no summary.",
        impact=(
            "Nothing states the relation the rule holds, so a reader of the "
            "source has only the command. State the condition and what it "
            "requires, in one sentence."
        ),
        failing="phase: before\\nrequire: Preserve the existing public contract.",
        passing=(
            "summary: A public contract stays stable unless the request "
            "authorizes a change.\\nphase: before\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.unknown-field": CheckExplanation(
        trigger="A rule file declares a field the rule schema does not have.",
        impact=(
            "The field is read by nothing. A preference is a heuristic, a "
            "reusable method is a pattern, and explanatory advice is guidance: "
            "none of them is a field of a rule."
        ),
        failing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract.\\n"
            "prefer: The smaller change."
        ),
        passing=(
            "summary: Keep the contract stable.\\nphase: before\\n"
            "match:\\n  subjects: [change.public-contract]\\n"
            "require: Preserve the existing public contract."
        ),
    ),
    "rule.unlowered": CheckExplanation(
        trigger=(
            'An active rule matched a reached node and reached no generated '
            'node. A `during` rule selecting only a decision, a gate, or a '
            'branch is the usual cause.'
        ),
        impact=(
            'The requirement is in no installed page. The message names the '
            'phase and the node form that refused it: a `during` rule renders '
            'beside a command, so select an action, a call, a pattern, or a '
            'return, or move it to `before` to check ahead of the choice.'
        ),
        failing='phase: during\nmatch:\n  forms: [decision]',
        passing='phase: before\nmatch:\n  forms: [decision]',
    ),
    "rule.unmatched": CheckExplanation(
        trigger=(
            "A bound rule's selector matches no reachable node at its phase."
        ),
        impact=(
            'Nothing triggers the rule, so the relation it states is enforced '
            'nowhere. Tag the step the rule is for, or narrow the selector to '
            'what the workflow actually declares. This warns rather than '
            'fails; `--fail-on-warning` refuses it.'
        ),
        failing='match:\n  outcomes: [never-returned]',
        passing='match:\n  outcomes: [completed]',
    ),
    # ---------------------------------------------------------- protocol
    "protocol.impossible-transition": CheckExplanation(
        trigger=(
            "A hook's `from` states cannot hold where it was lowered, or a "
            'frame closes where no accepting state is possible.'
        ),
        impact=(
            'The check is computed over the lowered graph, so this says the '
            'lifecycle cannot happen as written rather than that it might '
            'not. Widen `from` to every prior state the hook can meet, or add '
            'the hook that reaches an accepting state before the frame '
            'closes.'
        ),
        failing=(
            'hooks:\n  consume:\n    phase: before\n    from: [open]   # the state is still `clear` here'
        ),
        passing=(
            'hooks:\n  consume:\n    phase: before\n    from: [clear, open]'
        ),
    ),
    "protocol.invalid-hook": CheckExplanation(
        trigger=(
            'A hook declares a field the hook schema does not have, an '
            'invalid phase, a `match` on an `enter` or `exit` hook, no `from` '
            'states, or neither a command nor a verification.'
        ),
        impact=(
            'The hook is not read, so nothing carries its command or its '
            'state change. An `enter` or `exit` hook runs at the frame '
            'boundary and selects no node, which is why it takes no `match`.'
        ),
        failing=(
            'hooks:\n  open:\n    phase: enter\n    match:\n      all: true\n    from: [clear]\n    command: Open.'
        ),
        passing=(
            'hooks:\n  open:\n    phase: enter\n    from: [clear]\n    command: Open.'
        ),
    ),
    "protocol.invalid-shape": CheckExplanation(
        trigger=(
            "A protocol file gives a field a value of the wrong shape: a states "
            "or accepting list that is not lowercase-hyphenated names, or an "
            "empty hooks mapping."
        ),
        impact=(
            "The protocol is not read, so no lifecycle check is inserted "
            "anywhere. A field that is absent rather than malformed reports its "
            "own check instead, naming the key, such as "
            "protocol.missing-states or protocol.missing-hooks."
        ),
        failing=(
            "purpose: Keep a decision available.\\nstates: [Clear, Open]\\n"
            "initial: Clear\\naccepting: [Clear]"
        ),
        passing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear\\naccepting: [clear]"
        ),
    ),
    "protocol.invalid-state": CheckExplanation(
        trigger=(
            'A protocol names a state that is not declared, declares a state '
            'nothing can reach, sets or clears a data field it does not '
            'declare, or clears one that must always hold a value.'
        ),
        impact=(
            'The lifecycle cannot be checked: a state no hook moves to is a '
            'state the frame can never be in, and an undeclared field is one '
            'the compiler cannot carry. Declare every state and every data '
            'field the hooks use.'
        ),
        failing=(
            'states: [clear, open, spent]\ninitial: clear\naccepting: [clear]\nhooks:\n  retain:\n    to: open'
        ),
        passing=(
            'states: [clear, open]\ninitial: clear\naccepting: [clear]\nhooks:\n  retain:\n    to: open'
        ),
    ),
    "protocol.missing-accepting": CheckExplanation(
        trigger="A protocol file declares no accepting states.",
        impact=(
            "The accepting states are the ones a frame may close in, and the "
            "generated gate before frame close reads them. Without them no "
            "close is ever permitted. Name at least one declared state."
        ),
        failing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear"
        ),
        passing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear\\naccepting: [clear]"
        ),
    ),
    "protocol.missing-hooks": CheckExplanation(
        trigger="A protocol file declares no hooks.",
        impact=(
            "The hooks are what the compiler lowers into execution nodes, so a "
            "protocol with none constrains nothing anywhere. Declare at least "
            "one hook."
        ),
        failing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear\\naccepting: [clear]"
        ),
        passing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear\\naccepting: [clear]\\nhooks:\\n"
            "  retain-decision:\\n    phase: after\\n"
            "    match:\\n      subjects: [decision.open]\\n"
            "    from: [clear]\\n    command: Retain the decision basis.\\n"
            "    to: open"
        ),
    ),
    "protocol.missing-initial": CheckExplanation(
        trigger="A protocol file declares no initial state.",
        impact=(
            "Nothing says which state a frame opens in, so the compiler cannot "
            "establish what state is possible at any hook. Name one of the "
            "declared states."
        ),
        failing="purpose: Keep a decision available.\\nstates: [clear, open]",
        passing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear"
        ),
    ),
    "protocol.missing-purpose": CheckExplanation(
        trigger="A protocol file declares no purpose.",
        impact=(
            "Nothing states what the lifecycle is for, so a reader of the "
            "source cannot tell which obligation the states carry. State what "
            "stays open across boundaries, and why."
        ),
        failing="states: [clear, open]\\ninitial: clear\\naccepting: [clear]",
        passing=(
            "purpose: Keep a decision basis available until its consumer uses "
            "it.\\nstates: [clear, open]\\ninitial: clear\\naccepting: [clear]"
        ),
    ),
    "protocol.missing-states": CheckExplanation(
        trigger="A protocol file declares no states.",
        impact=(
            "The declared states are what a frame can hold, and every hook "
            "moves between them, so without them there is no lifecycle to "
            "check. Declare every state a frame can be in."
        ),
        failing="purpose: Keep a decision available.\\ninitial: clear",
        passing=(
            "purpose: Keep a decision available.\\nstates: [clear, open]\\n"
            "initial: clear"
        ),
    ),
    "protocol.unknown-field": CheckExplanation(
        trigger=(
            "A protocol file declares a field the protocol schema does not have."
        ),
        impact=(
            "The field is read by nothing. A protocol declares title, purpose, "
            "states, initial, accepting, data, and hooks."
        ),
        failing=(
            "purpose: Keep a decision available.\\nledger:\\n"
            "- Remember what is still open."
        ),
        passing="purpose: Keep a decision available.",
    ),
    "protocol.unlowered-hook": CheckExplanation(
        trigger='An active hook reached no generated node.',
        impact=(
            'Nothing carries its command or its state change. An `enter` or '
            '`exit` hook failing this is an error, because a frame that '
            'cannot open or close leaves the lifecycle broken; a `before` or '
            '`after` hook whose selector matched nothing warns.'
        ),
        failing=(
            'hooks:\n  retain:\n    phase: after\n    match:\n      subjects: [decision.open]   # no step declares it'
        ),
        passing='# on the step\nsubjects: [decision.open]',
    ),
    # ----------------------------------------------------------- pattern
    "pattern.invalid-procedure": CheckExplanation(
        trigger=(
            'A procedure item declares a field it does not have, or no '
            'command.'
        ),
        impact=(
            'The item is not read, so the step selecting the pattern expands '
            'one node short. A procedure item declares command, uses, subjects, '
            'and effects: it does not branch, call, return, or produce a value. '
            'Use a workflow where reusable behavior needs those.'
        ),
        failing=(
            'procedure:\n  inspect:\n    command: Inspect the owner.\n    next: choose-plan'
        ),
        passing='procedure:\n  inspect:\n    command: Inspect the owner.',
    ),
    "pattern.invalid-shape": CheckExplanation(
        trigger=(
            "A pattern file gives a field a value of the wrong shape: an empty "
            "procedure mapping, a procedure key that is not "
            "lowercase-hyphenated, or a malformed inputs declaration."
        ),
        impact=(
            "The pattern is not read, so a step selecting it expands into "
            "nothing. A field that is absent rather than malformed reports its "
            "own check instead, naming the key: pattern.missing-summary or "
            "pattern.missing-procedure."
        ),
        failing="summary: Inspect, plan, and act.\\nprocedure: {}",
        passing=(
            "summary: Inspect, plan, and act.\\nprocedure:\\n  inspect-owner:\\n"
            "    command: Inspect the source that owns the target behavior."
        ),
    ),
    "pattern.missing-procedure": CheckExplanation(
        trigger="A pattern file declares no procedure.",
        impact=(
            "The procedure items are what a pattern step expands into, so a "
            "pattern with none expands to nothing and the step performs no "
            "work. Declare the ordered procedure items."
        ),
        failing="summary: Inspect the owner, choose a plan, then act.",
        passing=(
            "summary: Inspect the owner, choose a plan, then act.\\n"
            "procedure:\\n  inspect-owner:\\n"
            "    command: Inspect the source that owns the target behavior."
        ),
    ),
    "pattern.missing-summary": CheckExplanation(
        trigger="A pattern file declares no summary.",
        impact=(
            "Nothing states the method the procedure carries out, so a step "
            "selecting the pattern cannot be read against what it was for. "
            "State the method in one sentence."
        ),
        failing="title: Inspect, plan, and act\\nprocedure:\\n  inspect: ...",
        passing=(
            "summary: Inspect the owner, choose a bounded plan, then act.\\n"
            "procedure:\\n  inspect: ..."
        ),
    ),
    "pattern.unexpanded": CheckExplanation(
        trigger=(
            'A pattern step names a pattern the skill does not select, or the '
            'pattern expanded into no node.'
        ),
        impact=(
            'The step performs nothing: a pattern application is expanded '
            'inline, so a pattern that is not there leaves a gap in the graph '
            'rather than a link to follow. Check the file stem and the '
            '`content.patterns` pattern that should select it.'
        ),
        failing='change:\n  pattern: inspect-plan-act   # not selected',
        passing='content:\n  patterns:\n  - patterns/**/*.yaml',
    ),
    "pattern.unknown-field": CheckExplanation(
        trigger="A pattern file declares a field the pattern schema does not have.",
        impact=(
            "The field is read by nothing. A pattern declares title, summary, "
            "inputs, procedure, and references."
        ),
        failing=(
            "summary: Inspect, plan, and act.\\nprocedure:\\n  inspect: ...\\n"
            "outcomes:\\n  done: {}"
        ),
        passing="summary: Inspect, plan, and act.\\nprocedure:\\n  inspect: ...",
    ),
    # --------------------------------------------------------- heuristic
    "heuristic.invalid-placement": CheckExplanation(
        trigger='A step other than a `decide` or a `gate` names heuristics.',
        impact=(
            'A heuristic aids a choice among valid alternatives, so it has '
            'nowhere to appear on a step that makes no choice. This is '
            'reported as a misplaced heuristic rather than an unknown field, '
            'because the mistake is about what a heuristic is for.'
        ),
        failing=(
            'inspect:\n  action: Inspect the material.\n  heuristics: [smallest-change]'
        ),
        passing=(
            'choose:\n  decide: Choose the route.\n  heuristics: [smallest-change]'
        ),
    ),
    "heuristic.invalid-shape": CheckExplanation(
        trigger=(
            "A heuristic file gives a field a value of the wrong shape: an "
            "empty advice mapping, an advice key that is not "
            "lowercase-hyphenated, or an advice item declaring no prefer."
        ),
        impact=(
            "The heuristic is not read, so a decision naming it shows no "
            "advice. A field that is absent rather than malformed reports its "
            "own check instead, naming the key: heuristic.missing-question or "
            "heuristic.missing-advice."
        ),
        failing="question: Which option is preferred?\\nadvice: {}",
        passing=(
            "question: Which valid option should be preferred?\\nadvice:\\n"
            "  reversible:\\n    prefer: Prefer the smallest reversible option."
        ),
    ),
    "heuristic.missing-advice": CheckExplanation(
        trigger="A heuristic file declares no advice.",
        impact=(
            "The advice items are what render under Consider on a decision or "
            "gate, so a heuristic with none shows nothing. Declare at least one "
            "advice item with a prefer."
        ),
        failing="question: Which valid option should be preferred?",
        passing=(
            "question: Which valid option should be preferred?\\nadvice:\\n"
            "  reversible:\\n    prefer: Prefer the smallest reversible option."
        ),
    ),
    "heuristic.missing-question": CheckExplanation(
        trigger="A heuristic file declares no question.",
        impact=(
            "The question is what says which choice the advice is for, so "
            "without it a decision naming the heuristic gives no basis for "
            "reading it. State the choice the advice helps make."
        ),
        failing="advice:\\n  reversible:\\n    prefer: Prefer the smaller option.",
        passing=(
            "question: Which valid option should be preferred?\\nadvice:\\n"
            "  reversible:\\n    prefer: Prefer the smaller option."
        ),
    ),
    "heuristic.unknown-field": CheckExplanation(
        trigger=(
            "A heuristic file declares a field the heuristic schema does not "
            "have."
        ),
        impact=(
            "The field is read by nothing. A heuristic declares title, "
            "question, advice, and references. A heuristic cannot require or "
            "verify anything, so it has no field for either."
        ),
        failing=(
            "question: Which option is preferred?\\nadvice:\\n  small:\\n"
            "    prefer: Prefer the smaller option.\\n"
            "require: Take the smaller option."
        ),
        passing=(
            "question: Which option is preferred?\\nadvice:\\n  small:\\n"
            "    prefer: Prefer the smaller option."
        ),
    ),
    "heuristic.used-as-authority": CheckExplanation(
        trigger=(
            'A verification names a heuristic, or `verify` is written as '
            'advice.'
        ),
        impact=(
            'A heuristic can improve a choice and can never satisfy a binding '
            'check, so treating one as authority would make advice into a '
            'gate. `verify` takes an expression, a gate, or an agent '
            'confirmation.'
        ),
        failing='verify:\n  gate: smallest-change   # a heuristic id',
        passing='verify:\n  gate: authorization',
    ),
    # ---------------------------------------------------------- guidance
    "guidance.invalid-application": CheckExplanation(
        trigger=(
            'Guidance stands where a binding construct is expected, or is '
            'applied with `detail: inline` while the unit declares no points.'
        ),
        impact=(
            'Guidance is non-binding: it cannot be bound as a policy, a rule, '
            'or a protocol, and asking to render points inline renders '
            'nothing when there are none. Bind a policy or a rule where the '
            'requirement is mandatory.'
        ),
        failing='policies:\n- clear-reporting   # a guidance unit',
        passing='guidance:\n- clear-reporting',
    ),
    "guidance.invalid-shape": CheckExplanation(
        trigger=(
            "A guidance file gives a field a value of the wrong shape: a "
            "summary that is not a non-empty string, or points or references "
            "that are not a non-empty list of strings."
        ),
        impact=(
            "The unit is not read, so no synopsis renders where it is applied. "
            "A summary that is absent rather than malformed reports "
            "guidance.missing-summary instead."
        ),
        failing="summary: Lead with the result.\\npoints: []",
        passing=(
            "summary: Lead with the result.\\npoints:\\n"
            "- Distinguish observed facts from inferred conclusions."
        ),
    ),
    "guidance.missing-summary": CheckExplanation(
        trigger="A guidance file declares no summary.",
        impact=(
            "The summary is the synopsis rendered inline at every application, "
            "and it is the whole of what a run sees without opening a page. "
            "State the advice in one sentence."
        ),
        failing="points:\\n- Distinguish observed facts from inferred conclusions.",
        passing=(
            "summary: Lead with the result and state the limitations that "
            "affect its use.\\npoints:\\n"
            "- Distinguish observed facts from inferred conclusions."
        ),
    ),
    "guidance.unknown-field": CheckExplanation(
        trigger=(
            "A guidance file declares a field the guidance schema does not have."
        ),
        impact=(
            "The field is read by nothing. Guidance declares title, summary, "
            "points and references. Guidance is "
            "non-binding, so it has no phase, selector, or command."
        ),
        failing="summary: Lead with the result.\\nphase: before",
        passing="summary: Lead with the result.",
    ),
    # ----------------------------------------------------------- profile
    "profile.binding-contribution": CheckExplanation(
        trigger='A profile declares policies, rules, protocols, or workflows.',
        impact=(
            'Profiles are auxiliary guidance outside the execution graph, so '
            'mandatory behavior cannot depend on one. Put requirements in the '
            'core workflow, policies, rules, or protocols instead.'
        ),
        failing='points:\n- Keep it short.\npolicies:\n- request-authority',
        passing='points:\n- Keep it short.',
    ),
    "profile.duplicate-title": CheckExplanation(
        trigger="Two profiles have the same title, compared without regard to case.",
        impact=(
            "The profile index uses titles to distinguish its choices. Rename one "
            "profile so a reader can select one unambiguously."
        ),
        failing="title: Concise\npoints:\n- Keep it short.",
        passing="title: Detailed\npoints:\n- Keep it short.",
    ),
    "profile.guide-heading": CheckExplanation(
        trigger="A profile guide contains a level-one heading.",
        impact=(
            "Degardis supplies the generated profile page's level-one heading, "
            "so a guide must begin below that level."
        ),
        failing="guides:\n  - references/with-h1.md",
        passing="guides:\n  - references/detailed.md",
    ),
    "profile.guide-missing": CheckExplanation(
        trigger="A profile names a guide that does not exist.",
        impact=(
            "The auxiliary profile page would be missing guidance it declares. "
            "Guide paths are relative to the profile source."
        ),
        failing="guides:\n  - references/detailled.md",
        passing="guides:\n  - references/detailed.md",
    ),
    "profile.guide-not-markdown": CheckExplanation(
        trigger="A profile names a guide without a .md extension.",
        impact=(
            "Guides are appended to generated Markdown profile pages, so only "
            "Markdown sources can be included."
        ),
        failing="guides:\n  - references/detailed.txt",
        passing="guides:\n  - references/detailed.md",
    ),
    "profile.guide-outside-skill": CheckExplanation(
        trigger="A profile guide resolves outside the skill directory.",
        impact=(
            "The generated skill must be self-contained; an outside guide would "
            "not travel with the auxiliary profile."
        ),
        failing="guides:\n  - ../../shared/detailed.md",
        passing="guides:\n  - references/detailed.md",
    ),
    "profile.invalid-category": CheckExplanation(
        trigger="A profile's category is present but is not a non-empty string.",
        impact=(
            "The profile cannot be indexed. Supply a category containing "
            "non-whitespace text, or omit category to leave the profile uncategorized."
        ),
        failing="category: ''\npoints:\n- Prefer project tooling.",
        passing="category: Tooling\npoints:\n- Prefer project tooling.",
    ),
    "profile.invalid-description": CheckExplanation(
        trigger="A profile's description is present but is not a non-empty string.",
        impact=(
            "The profile cannot be indexed. Supply a description containing "
            "non-whitespace text, or omit description to show only the title."
        ),
        failing="description: ''\npoints:\n- Prefer project tooling.",
        passing="description: Apply where the project ships tooling of its own.\npoints:\n- Prefer project tooling.",
    ),
    "profile.invalid-shape": CheckExplanation(
        trigger=(
            "A profile field is present and cannot be read as the schema "
            "declares it."
        ),
        impact=(
            "The profile is not indexed, but core execution remains unchanged. "
            "Use a non-empty list of strings for the points."
        ),
        failing="points: []",
        passing="points:\n- Prefer project tooling.",
    ),
    "profile.missing-points": CheckExplanation(
        trigger="A profile file declares no points.",
        impact=(
            "A profile exists only to contribute auxiliary guidance, so a profile "
            "with no points contributes nothing useful to load."
        ),
        failing="title: Concise result",
        passing="title: Concise result\npoints:\n- Keep only decision-relevant detail.",
    ),
    "profile.missing-title": CheckExplanation(
        trigger="A profile declares no title.",
        impact=(
            "The compiler derives a display title from the filename, so the "
            "profile still appears in the index, but an explicit title makes a "
            "candidate easier to recognize."
        ),
        failing="# profiles/detailed-review.yaml",
        passing="title: Detailed review",
    ),
    "profile.unknown-field": CheckExplanation(
        trigger="A profile file declares a field the profile schema does not have.",
        impact=(
            "The field is read by nothing. A profile declares title, description, "
            "points, and guides. Every other field is outside the Format 2 schema."
        ),
        failing="applies:\n  terms: [concise]\npoints:\n- Keep it short.",
        passing="description: Apply for short answers.\npoints:\n- Keep it short.",
    ),
    "profile.workflow-dependency": CheckExplanation(
        trigger='A workflow or a step names a profile.',
        impact=(
            'Core execution must be authored without profiles in mind. A reader '
            'chooses a profile for itself from the generated index, and every '
            'profile can be deleted without changing any valid execution.'
        ),
        failing='inspect:\n  action: Inspect the material.\n  policies:\n  - concise',
        passing='inspect:\n  action: Inspect the material.\n  guidance:\n  - clear-reporting',
    ),
    # ------------------------------------------------------------ record
    "record.invalid-shape": CheckExplanation(
        trigger=(
            "A record file gives a field a value of the wrong shape: an empty "
            "fields mapping, a field name that is not lowercase-hyphenated, or "
            "a field entry that is not a mapping."
        ),
        impact=(
            "The record is not read, so every value typed by it is untyped. A "
            "fields mapping that is absent rather than malformed reports "
            "record.missing-fields instead."
        ),
        failing="title: Inspection result\\nfields: {}",
        passing=(
            "title: Inspection result\\nfields:\\n  summary:\\n"
            "    type: string\\n    description: Concise result."
        ),
    ),
    "record.missing-fields": CheckExplanation(
        trigger="A record file declares no fields.",
        impact=(
            "A record is its typed fields: with none, every value the record "
            "types is untyped and no contract renders where those values are "
            "produced or consumed. Declare at least one field."
        ),
        failing="title: Inspection result",
        passing=(
            "title: Inspection result\\nfields:\\n  summary:\\n"
            "    type: string\\n    description: Concise result."
        ),
    ),
    "record.unknown-field": CheckExplanation(
        trigger="A record file declares a field the record schema does not have.",
        impact=(
            "The field is read by nothing. A record declares a title and a "
            "fields mapping; the typed entries belong inside fields."
        ),
        failing="title: Inspection result\\nsummary:\\n  type: string",
        passing=(
            "title: Inspection result\\nfields:\\n  summary:\\n    type: string"
        ),
    ),
    # ---------------------------------------------------------- workflow
    "workflow.conflicting-obligation": CheckExplanation(
        trigger=(
            "One command is both required and prohibited at the same step and "
            "the same phase, by two provisions, two rules, or a provision and "
            "a rule."
        ),
        impact=(
            "No reading of the node satisfies both, so the agent reaching it "
            "can only block. This is the one conflict the compiler can see: it "
            "cannot read two different sentences to decide whether they "
            "disagree, and two provisions sharing a selector are ordinary "
            "policy rather than a conflict. Withdraw one, narrow one "
            "selector, or move one to another phase."
        ),
        failing=(
            "establish:\n  phase: before\n  match:\n    all: true\n"
            "  require: Report the effect.\nwithhold:\n  phase: before\n"
            "  match:\n    all: true\n  prohibit: Report the effect."
        ),
        passing=(
            "establish:\n  phase: after\n  match:\n    all: true\n"
            "  require: Report the effect.\nwithhold:\n  phase: before\n"
            "  match:\n    all: true\n  prohibit: Report the effect."
        ),
    ),
    "workflow.conflicting-value": CheckExplanation(
        trigger='Two steps declare one value name with different types.',
        impact=(
            'A later read cannot know which type it holds. Rename one of '
            'them, or declare both with the same type where they mean the '
            'same thing.'
        ),
        failing=(
            '# one step produces `plan: string`, another `plan: {list: '
            'string}`'
        ),
        passing=(
            '# one step produces `plan: string`, another `plans: {list: '
            'string}`'
        ),
    ),
    "workflow.duplicate-binding": CheckExplanation(
        trigger=(
            'One construct is bound at two scopes: the manifest and a '
            'workflow, or a workflow and one of its steps.'
        ),
        impact=(
            'The narrower binding lowers nothing the wider one did not, so '
            'the second copy states nothing new at the same boundary. Keep '
            'the binding at the widest scope that is correct, and remove the '
            'other.'
        ),
        failing=(
            '# manifest binds request-authority, and the workflow binds it again\npolicies:\n- request-authority'
        ),
        passing='# bound once, at the manifest',
    ),
    "workflow.invalid-edge": CheckExplanation(
        trigger=(
            'A workflow names an entry, a transition target, or a called '
            'workflow that does not exist, or leaves a non-return step with '
            'no successor.'
        ),
        impact=(
            'The graph cannot execute: a step with nowhere to go ends a run '
            'somewhere that is not a declared outcome. Only a return ends a '
            'workflow, so every other form declares where it continues.'
        ),
        failing='act:\n  action: Do the one thing.',
        passing='act:\n  action: Do the one thing.\n  next: finish',
    ),
    "workflow.invalid-shape": CheckExplanation(
        trigger=(
            "A workflow file gives a field a value of the wrong shape: an entry "
            "that is not a step id, an empty inputs, outcomes, or steps "
            "mapping, or a malformed outcome or input declaration."
        ),
        impact=(
            "The workflow is not read, so nothing renders it and no run can "
            "enter it. A field that is absent rather than malformed reports its "
            "own check instead, naming the key, such as "
            "workflow.missing-description or workflow.missing-outcomes."
        ),
        failing=(
            "description: Deliver the bounded result.\\nentry: inspect\\n"
            "outcomes: {}"
        ),
        passing=(
            "description: Deliver the bounded result.\\nentry: inspect\\n"
            "outcomes:\\n  completed: {}"
        ),
    ),
    "workflow.invalid-step": CheckExplanation(
        trigger=(
            "A step is not usable: it is an empty string, neither a string nor a "
            "mapping, holds an empty or non-string field, declares rules that are not a "
            "list, defines none of use, "
            "action, id, or instruction, or combines use with action or "
            "instruction."
        ),
        impact=(
            "The step cannot be rendered as an instruction, so the workflow would "
            "ship with a gap where an action belongs."
        ),
        failing=(
            "steps:\n"
            "  - use: review\n"
            "    instruction: Also check the tone"
        ),
        passing=(
            "steps:\n"
            "  - use: review\n"
            "  - instruction: Check the tone"
        ),
    ),
    "workflow.missing-description": CheckExplanation(
        trigger="A workflow file declares no description.",
        impact=(
            "The description is the workflow's purpose in the generated "
            "directory and its header, and the directory is how an agent sees "
            "what each workflow is for without navigating to it. State the "
            "purpose in one sentence."
        ),
        failing="title: Perform the task\\nentry: inspect",
        passing=(
            "description: Inspect the request and deliver the bounded result.\\n"
            "entry: inspect"
        ),
    ),
    "workflow.missing-entry": CheckExplanation(
        trigger="A workflow file declares no entry.",
        impact=(
            "Nothing names the step execution starts at, so the graph has no "
            "root, nothing is reachable, and no node can be rendered. Name one "
            "of the declared steps."
        ),
        failing=(
            "description: Deliver the bounded result.\\nsteps:\\n"
            "  inspect:\\n    action: Inspect the material.\\n    next: done"
        ),
        passing=(
            "description: Deliver the bounded result.\\nentry: inspect\\n"
            "steps:\\n  inspect:\\n    action: Inspect the material.\\n"
            "    next: done"
        ),
    ),
    "workflow.missing-gate": CheckExplanation(
        trigger=(
            'A check is verified by a gate that does not lie on every path to '
            'the node it constrains.'
        ),
        impact=(
            'The verification reads `gate.<step-id>`, so a gate some path '
            'skips leaves the check with nothing to read. Move the gate so '
            'every route to the constrained node passes it, or verify with an '
            'expression or an agent confirmation instead.'
        ),
        failing='verify:\n  gate: readiness   # reached on one branch only',
        passing=(
            'verify:\n  confirm: Every declared prerequisite is satisfied.'
        ),
    ),
    "workflow.missing-outcomes": CheckExplanation(
        trigger="A workflow file declares no outcomes.",
        impact=(
            "Every reachable path ends at a return, and every return names a "
            "declared outcome, so a workflow with no outcomes has no way to "
            "terminate and no result a caller can map. Declare each outcome a "
            "return may name."
        ),
        failing="description: Deliver the bounded result.\\nentry: inspect",
        passing=(
            "description: Deliver the bounded result.\\noutcomes:\\n"
            "  completed:\\n    record: delivery-result\\n  no-change: {}\\n"
            "entry: inspect"
        ),
    ),
    "workflow.missing-steps": CheckExplanation(
        trigger="A workflow file declares no steps.",
        impact=(
            "The steps are the workflow: with none there is no control flow to "
            "validate and no node to render. Declare at least the entry step."
        ),
        failing="description: Deliver the bounded result.\\nentry: inspect",
        passing=(
            "description: Deliver the bounded result.\\nentry: inspect\\n"
            "steps:\\n  inspect:\\n    action: Inspect the material.\\n"
            "    next: done"
        ),
    ),
    "workflow.reserved-outcome": CheckExplanation(
        trigger='A source declares, returns, or maps `blocked`.',
        impact=(
            "`blocked` is the compiler's own outcome: every workflow returns "
            'it when a binding check cannot be satisfied. A source declaring '
            'the same name would give one outcome two meanings, and a call '
            'mapping it would claim to handle a transition the compiler owns.'
        ),
        failing='outcomes:\n  completed: {}\n  blocked: {}',
        passing='outcomes:\n  completed: {}',
    ),
    "workflow.unhandled-outcome": CheckExplanation(
        trigger=(
            'A call leaves a callee outcome unmapped or maps one the callee '
            'does not declare, a return names an undeclared outcome, or an '
            'outcome is declared and never returned.'
        ),
        impact=(
            'A caller would have to handle a transition that cannot happen, '
            'or would meet one it has no route for. Map exactly the outcomes '
            'the callee declares, and return every outcome the workflow '
            'declares.'
        ),
        failing=(
            'outcomes:\n  completed: {}\n  no-change: {}   # no return names it'
        ),
        passing='outcomes:\n  completed: {}',
    ),
    "workflow.unknown-field": CheckExplanation(
        trigger=(
            "A workflow file declares a field the workflow schema does not have."
        ),
        impact=(
            "The field is read by nothing. A workflow declares title, "
            "description, policies, rules, protocols, guidance, inputs, "
            "outcomes, entry, and steps. A workflow cannot select a profile or "
            "a pattern at file scope."
        ),
        failing=(
            "description: Deliver the bounded result.\\nentry: inspect\\n"
            "profiles:\\n- concise"
        ),
        passing="description: Deliver the bounded result.\\nentry: inspect",
    ),
    "workflow.unreachable": CheckExplanation(
        trigger=(
            "No chain of use steps reaches this workflow from the primary "
            "workflow."
        ),
        impact=(
            "The workflow still ships, but no use step invokes it and no route "
            "from SKILL.md reaches its generated page."
        ),
        failing="# workflows/review.yaml is never named by a use step",
        passing="steps:\n  - use: review",
    ),
    "workflow.unreached": CheckExplanation(
        trigger=(
            'A selected workflow is not the primary workflow and no reached '
            'step calls it.'
        ),
        impact=(
            'Nothing renders it and no run can enter it. It still builds: an '
            'unreached workflow is what a partly wired skill looks like, and '
            '`--fail-on-warning` refuses one. Add the `use` step that calls '
            'it, or drop it from the content patterns.'
        ),
        failing='# workflows/report-gaps.yaml selected, and no step uses it',
        passing=(
            'describe-gaps:\n  use: report-gaps\n  on:\n    reported: done'
        ),
    ),
    # -------------------------------------------------------------- expr
    "expr.invalid-syntax": CheckExplanation(
        trigger=(
            'A DExpr condition does not parse: prose where an expression '
            'belongs, an unbalanced bracket, or an operator the grammar does '
            'not have.'
        ),
        impact=(
            'The condition cannot be evaluated, so the activation or branch '
            'it controls has no machine meaning. DExpr compares declared '
            'values with `and`, `or`, `not`, the six comparisons, `in`, and '
            'three functions.'
        ),
        failing='when: the request authorizes the change',
        passing='when: input.request.authorizes-change == true',
    ),
    "expr.type-mismatch": CheckExplanation(
        trigger=(
            'An expression compares or combines values whose types cannot be: '
            'a string against an integer, a list literal of mixed types, '
            '`length` of something with no length, or a non-boolean where a '
            'condition belongs.'
        ),
        impact=(
            'The comparison has no defined answer. Compare a value with a '
            'literal of its own type, and use `contains` for membership '
            'rather than equality.'
        ),
        failing='when: length(input.request) == "two"',
        passing='when: length(input.request) > 2',
    ),
    "expr.undefined-value": CheckExplanation(
        trigger=(
            'An expression reads a value that some path reaching this point '
            'has not produced.'
        ),
        impact=(
            'The value exists on one route and not another, so the condition '
            'would read nothing on that route. Produce it on every incoming '
            'path, or move the read to a point every path has passed the '
            'producing step.'
        ),
        failing=(
            '# read after a branch where only one arm produces `plan`\nwhen: result.plan == "small"'
        ),
        passing=(
            '# read after the step that produces it on every path\nwhen: result.plan == "small"'
        ),
    ),
    "expr.unguarded-optional": CheckExplanation(
        trigger=(
            'An expression reads a possibly absent value without an `exists` '
            'guard in the same short-circuit expression.'
        ),
        impact=(
            'An optional value may not be there when the condition runs, so '
            'the read has no defined result. Guard it in the same expression, '
            'so the guard and the read cannot be separated later.'
        ),
        failing='when: result.inspection.summary != ""',
        passing=(
            'when: exists(result.inspection) and result.inspection.summary != '
            '""'
        ),
    ),
    "expr.unknown-value": CheckExplanation(
        trigger=(
            'An expression reads a value the workflow does not declare, or a '
            'record field the record does not declare.'
        ),
        impact=(
            'There is nothing to evaluate against. Check the namespace and '
            'the name: `input` for a declared input, `result` for a produced '
            "value, `decision` and `gate` for a step's own id, `call` for a "
            'receipt.'
        ),
        failing=(
            'when: result.inspection == true   # no step produces inspection'
        ),
        passing='when: exists(result.inspection)',
    ),
    # ------------------------------------------------------------- value
    "value.invalid-binding": CheckExplanation(
        trigger=(
            'A binding is not a mapping naming exactly one of `from` and '
            '`literal`, or gives `literal` a list or a mapping.'
        ),
        impact=(
            'Nothing says where the value comes from. Bindings are tagged so '
            'that a value name and a written string cannot be confused: '
            '`{from: ...}` reads another value, `{literal: ...}` writes a '
            'scalar.'
        ),
        failing='with:\n  label: author',
        passing='with:\n  label: {literal: author}',
    ),
    "value.invalid-type": CheckExplanation(
        trigger=(
            'A declared value names no type the format has, or writes one in '
            'a shape it does not accept.'
        ),
        impact=(
            'The value is untyped, so nothing can be checked against it. A '
            'type is string, integer, number, or boolean, or a mapping naming '
            'exactly one of enum, list, record, or optional.'
        ),
        failing='produces:\n  summary:\n    type: text',
        passing='produces:\n  summary:\n    type: string',
    ),
    "value.missing-binding": CheckExplanation(
        trigger=(
            'A call, a pattern application, or a return leaves a declared '
            'value unsupplied.'
        ),
        impact=(
            'The callee, pattern, or record declares the value, so the '
            'boundary is incomplete and the generated node would name a value '
            'nothing provides. Supply every one the destination declares.'
        ),
        failing=(
            'return:\n  outcome: completed\n  with:\n    summary: {from: result.text}'
        ),
        passing=(
            'return:\n  outcome: completed\n  with:\n    summary: {from: result.text}\n    limitations: {from: result.gaps}'
        ),
    ),
    "value.mistyped-binding": CheckExplanation(
        trigger=(
            "A supplied value's type cannot stand where the destination "
            'expects one: a different scalar, a value that may be absent '
            'where one must be present, or a literal outside a declared enum.'
        ),
        impact=(
            'The destination would receive something it cannot use. Match the '
            'declared type, or declare the destination `{optional: T}` where '
            'an absent value is meant.'
        ),
        failing=(
            'with:\n  depth: {literal: deep}   # enum is [brief, detailed]'
        ),
        passing='with:\n  depth: {literal: detailed}',
    ),
    "value.unknown-binding": CheckExplanation(
        trigger=(
            'A call, a pattern application, or a return supplies a value the '
            'destination does not declare.'
        ),
        impact=(
            'Nothing reads it, so the binding is either a typo or a leftover '
            'from a contract that changed. Supply exactly the values the '
            'callee, pattern, or record declares.'
        ),
        failing=(
            'with:\n  target: {from: result.inspection}\n  depth: {literal: brief}'
        ),
        passing='with:\n  target: {from: result.inspection}',
    ),
    # ------------------------------------------------------------ render
    "render.external-execution-link": CheckExplanation(
        trigger=(
            'An execution transition names something that is not a node '
            'defined in the generated execution graph.'
        ),
        impact=(
            'The renderer cannot produce either a valid local edge or a typed '
            'cross-module load for that destination. This is a compiler failure '
            'rather than a source mistake; report it with the source that '
            'produced the broken transition.'
        ),
        failing='# a transition naming a node no workflow lowered',
        passing='# every transition targets a node in the generated execution graph',
    ),
    "render.incomplete-command": CheckExplanation(
        trigger=(
            "A generated node's heading, or a transition's destination "
            'command, is not a complete command that closes as a sentence.'
        ),
        impact=(
            'An agent skimming headings has to read what to do, so a heading '
            'that reads as a topic invites it to infer the content instead. '
            "The heading is the author's own command, rendered: write each "
            'action, check, decision, and return as a sentence.'
        ),
        failing='act:\n  action: Report',
        passing='act:\n  action: Report the result and its limitations.',
    ),
    "render.load-bearing-reference": CheckExplanation(
        trigger=(
            'An outbound reference appears in a role that carries execution: '
            'a command, a required or prohibited line, a verification, a '
            'state update, a produced or supplied value, or a transition.'
        ),
        impact=(
            'The requirement would depend on an untyped documentation link. '
            'Required cross-file execution is compiler-generated under `execution/`; '
            'author commands must state their behavior directly. Put explanatory '
            "material in the construct's `references` or use a typed action "
            '`resource` operation for a required bundled file.'
        ),
        failing=(
            'require: Apply the exceptions in `references/policies/notes.md`.'
        ),
        passing=(
            "require: Apply only an exception this provision's own `unless` "
            'states.'
        ),
    ),
    "render.node-label-collision": CheckExplanation(
        trigger='Two generated nodes answer to one node label.',
        impact=(
            'A transition names its destination by label, so a collision '
            'leaves one node unreachable and the other ambiguous. Nothing '
            'appends a numeric suffix to break the tie, because a label built '
            'from source ids is stable across rebuilds and a generated one '
            'would not be. Rename one of the source or local ids that build '
            'the label.'
        ),
        failing=(
            'provisions:\n  report:\n    ...\n  report:\n    ...   # one id twice'
        ),
        passing=(
            'provisions:\n  report-effect:\n    ...\n  report-boundary:\n    ...'
        ),
    ),
    # ------------------------------------------------------------ output
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
        failing="# SKILL.md links rules/outcome-first.md",
        passing="# the bundle writes rules/outcome-first.md",
    ),
    "output.path-collision": CheckExplanation(
        trigger=(
            "Two sources would be written to the same path in the bundle, "
            "compared without regard to letter case."
        ),
        impact=(
            "One file would overwrite the other, and which one survives depends on "
            "the filesystem. Rule, workflow, and profile names, scripts, assets, "
            "and generated icons all claim paths in one namespace."
        ),
        failing="rules/Report.yaml\nrules/report.yaml",
        passing="rules/outcome.yaml\nrules/format.yaml",
    ),
    "output.source-overlap": CheckExplanation(
        trigger=(
            "The build output directory is a skill source directory, contains "
            "one, or sits inside one."
        ),
        impact=(
            "A build replaces the whole folder it writes for each skill, so an "
            "output path overlapping a source would delete the authored files it "
            "was told to compile. The build stops before writing anything."
        ),
        failing="degardis build examples/structured-summary --output examples",
        passing="degardis build examples/structured-summary --output .artifacts",
    ),
    "output.unlinked-reference": CheckExplanation(
        trigger=(
            "The bundle would ship a reference page, script, or asset that no "
            "route from the generated SKILL.md reaches."
        ),
        impact=(
            "An installed skill is read from SKILL.md outwards, so a page no "
            "route reaches is a page the agent cannot open and the bundle "
            "carries for nothing. A route may cross a page on its way: a rule "
            "a supporting workflow declares is linked from that workflow's own "
            "page, and reaching that page is enough. The generated body links "
            "each page from the scope that requires it, so two sources strand "
            "one: a rule no step, workflow, or the skill declares, and a "
            "supporting workflow no use step reaches, which takes its own page "
            "and every rule only it declares off every route. It warns rather "
            "than stops, because shipping a page before anything declares it is "
            "what mid-design work looks like; pass --fail-on-warning where that "
            "is not acceptable."
        ),
        failing="workflows/audit.yaml  # reached by no use step",
        passing="- use: audit  # in a workflow a run reaches",
    ),
    # -------------------------------------------------------------- icon
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
}


CHECKS.update({
    "pattern.invalid-effects": CheckExplanation(
        trigger="A pattern application declares effects instead of the procedure item that takes them.",
        impact="Effects must attach to the exact operation that causes them so policy binding is neither duplicated nor skipped.",
        failing="apply:\n  pattern: inspect-plan-act\n  effects: [external.write]",
        passing="procedure:\n  perform-change:\n    command: Perform the change.\n    effects: [external.write]",
    ),
    "pattern.invalid-use": CheckExplanation(
        trigger="A pattern procedure item reads a value that is not one of the pattern inputs.",
        impact="Procedure reads must be typed and substitutable at every application site.",
        failing="uses: [input.missing]",
        passing="uses: [input.target]",
    ),
    "render.module-budget": CheckExplanation(
        trigger="A generated execution module is larger than the budget for a single loaded module.",
        impact="A module is read whole before it is executed, so one larger than a single read delivers arrives truncated and the agent executes what it did not finish reading.",
        failing="A workflow whose header, repeated in every module, leaves no room to fit a node around it.",
        passing="A workflow whose description and bound guidance leave each module room for the nodes it carries.",
    ),
    "render.node-budget": CheckExplanation(
        trigger="One generated node is larger than the budget for a single loaded module.",
        impact="Execution is partitioned so that every module fits one load, and one node is the case no partition can divide, so the module holding it is over the budget however the workflow is split.",
        failing="A step whose command, invariants, and advice render to more than 16 KiB at one node.",
        passing="A step whose command states one action, with the material behind it carried by the constructs bound to it.",
    ),
    "render.root-budget": CheckExplanation(
        trigger="The generated SKILL.md exceeds the compiler's root byte budget.",
        impact="The root is loaded every time the skill is selected, before any work begins, so it is charged against every run whether or not it is read.",
        failing="Generated SKILL.md is larger than 4 KiB.",
        passing="Generated SKILL.md stays within the 4 KiB root budget.",
    ),
    "resource.invalid-operation": CheckExplanation(
        trigger="A typed resource action names zero, multiple, or unsupported resource operations.",
        impact="A required resource use must have one deterministic operation the runtime can execute or fail closed on.",
        failing="resource: {run: scripts/a.py, read: references/a.md}",
        passing="resource: {run: scripts/a.py}",
    ),
    "resource.invalid-path": CheckExplanation(
        trigger="A typed resource action uses an absolute path, a path that escapes the skill, or a path outside the operation's allowed area.",
        impact="Required resources must resolve deterministically inside the built skill bundle.",
        failing="resource: {run: ../tool.py}",
        passing="resource: {run: scripts/tool.py}",
    ),
    "resource.not-selected": CheckExplanation(
        trigger="A workflow requires a resource that the manifest does not copy into the built skill.",
        impact="The generated instruction would otherwise require a file that cannot exist at runtime.",
        failing="The workflow runs scripts/tool.py but the manifest does not select it.",
        passing="The workflow runs scripts/tool.py and the manifest selects scripts/tool.py.",
    ),
    "value.invalid-capture": CheckExplanation(
        trigger="A call outcome is captured with `as`, but that callee outcome carries no record payload.",
        impact="A caller can bind only data the callee actually returns on that outcome edge.",
        failing="completed: {next: report, as: result} # completed has no record",
        passing="completed: {next: report, as: result} # completed returns summary-result",
    ),
})

def explanation(code: str) -> CheckExplanation | None:
    """The rule for one check code, or None when the code is not known."""
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
    """List every explainable code, one namespace at a time, for an error path.

    The naming rule comes first. A reader who reached this list guessed a code,
    and the rule is what makes the next guess right without reading the list.
    """
    lines = [
        "A code is <namespace>.<check>, hyphenated, except where the check names "
        "a field of",
        "the source, which it spells exactly as the key does: "
        "interface.short_description-length.",
        "",
        "Known check codes:",
    ]
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
