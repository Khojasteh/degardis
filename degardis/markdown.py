from __future__ import annotations

import yaml

from . import __version__
from .model import Entry, SkillBundle, SkillContent


def humanize(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def module_slug(value: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "-" for character in value
    )
    return "-".join(part for part in cleaned.split("-") if part)


def entry_filename(entry: Entry) -> str:
    local_id = entry.id
    prefix = f"{entry.skill}."
    if local_id.startswith(prefix):
        local_id = local_id[len(prefix) :]
    kind_prefix = f"{entry.kind}."
    if local_id.startswith(kind_prefix):
        local_id = local_id[len(kind_prefix) :]
    return f"{module_slug(local_id)}.md"


def workflow_filename(workflow: dict, skill_name: str) -> str:
    workflow_id = str(workflow.get("id", workflow.get("title", "workflow")))
    prefix = f"{skill_name}."
    if workflow_id.startswith(prefix):
        workflow_id = workflow_id[len(prefix) :]
    return f"{module_slug(workflow_id)}.md"


def entry_markdown(entry: Entry) -> str:
    data = entry.data
    lines = [f"# {entry.title}", "", "## Rule", "", str(data["rule"])]
    for key in ("rationale", "scope", "constraint"):
        if data.get(key):
            lines += ["", f"## {humanize(key)}", "", str(data[key])]
    # Conditions qualify whether the requirements below bind, so they precede
    # them: an agent reading top-down learns the rule may not apply before it
    # has taken on what the rule demands.
    for key in (
        "conditions",
        "require",
        "allow",
        "reject",
        "exceptions",
        "examples",
    ):
        values = data.get(key)
        if values:
            lines += ["", f"## {humanize(key)}", ""]
            lines += [f"- {value}" for value in values]
    lines += [
        "",
        "## Metadata",
        "",
        f"- **ID:** `{entry.id}`",
        f"- **Kind:** `{entry.kind}`",
        f"- **Skill:** `{entry.skill}`",
        f"- **Priority:** `{entry.priority}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def workflow_steps(workflow: dict) -> list[str]:
    lines: list[str] = []
    for index, step in enumerate(workflow.get("steps", []), 1):
        if isinstance(step, str):
            lines.append(f"{index}. {step}")
            continue
        condition = step.get("when")
        suffix = f" when `{condition}`" if condition else ""
        if step.get("use"):
            lines.append(f"{index}. Follow workflow `{step['use']}`{suffix}.")
        else:
            action = str(step.get("action") or step.get("id", "step"))
            lines.append(f"{index}. **{humanize(action)}**{suffix}")
        if step.get("instruction"):
            lines.append(f"   {step['instruction']}")
    return lines


def workflow_markdown(workflow: dict) -> str:
    title = str(workflow.get("title", workflow.get("id", "Workflow")))
    lines = [f"# {title}", ""]
    if workflow.get("description"):
        lines += [str(workflow["description"]), ""]
    lines += ["## Steps", "", *workflow_steps(workflow)]
    return "\n".join(lines).rstrip() + "\n"


def _frontmatter(
    name: str,
    description: str,
    skill_version: str,
    license: str | None = None,
    copyright: str | None = None,
) -> str:
    fields: dict[str, str | dict[str, str]] = {
        "name": name,
        "description": description,
    }
    if license is not None:
        fields["license"] = license
    metadata: dict[str, str] = {
        "version": skill_version,
        "generated_by": f"degardis/{__version__}",
    }
    if copyright is not None:
        metadata["copyright"] = copyright
    fields["metadata"] = metadata
    data = yaml.safe_dump(
        fields,
        sort_keys=False,
        width=1000,
    ).strip()
    return f"---\n{data}\n---"


def skill_markdown_body(rendered: str) -> str:
    """Return generated SKILL.md without its YAML frontmatter."""
    body = rendered
    if rendered.startswith("---\n"):
        _, separator, after = rendered[len("---\n") :].partition("\n---\n")
        if separator:
            body = after
    return body.strip("\n")


def markdown_metrics(rendered: str) -> dict[str, int]:
    """Measure generated SKILL.md, separating the body from its frontmatter."""
    body = skill_markdown_body(rendered)
    return {
        "bytes": len(rendered.encode("utf-8")),
        "lines": len(rendered.splitlines()),
        "body_bytes": len(body.encode("utf-8")),
        "body_lines": len(body.splitlines()),
        "body_words": len(body.split()),
    }


def _primary_workflow(content: SkillContent) -> dict:
    for workflow in content.workflows:
        if workflow.get("id") == content.skill.primary_workflow:
            return workflow
    raise ValueError(
        f"{content.skill.name}: missing primary workflow "
        f"{content.skill.primary_workflow}"
    )


def skill_markdown(
    bundle: SkillBundle,
    skill_name: str,
) -> str:
    content = bundle.content(skill_name)
    skill = content.skill
    primary = _primary_workflow(content)
    lines = [
        _frontmatter(
            skill.name,
            skill.description,
            skill.version,
            skill.license,
            skill.copyright,
        ),
        "",
        f"# {skill.title}",
        "",
    ]
    if primary.get("description"):
        lines += [str(primary["description"]), ""]
    lines += ["## Workflow", "", *workflow_steps(primary)]

    if content.entries:
        lines += [
            "",
            "## References",
            "",
            "Load only the references needed for the current task:",
            "",
        ]
        for entry in content.entries:
            lines.append(
                f"- [{entry.title}](references/entries/{entry_filename(entry)})"
            )

    secondary = [
        workflow
        for workflow in content.workflows
        if workflow.get("id") != skill.primary_workflow
    ]
    if secondary:
        lines += ["", "## Supporting Workflows", ""]
        for workflow in secondary:
            lines.append(
                f"- [{workflow.get('title', workflow.get('id'))}]"
                f"(references/workflows/{workflow_filename(workflow, skill.name)})"
            )

    if content.profiles:
        lines += [
            "",
            "## Profiles",
            "",
            "Profiles adapt this skill to a particular audience, format, technology,"
            " or environment. Load every profile whose label names something this"
            " request involves, and no others:",
            "",
        ]
        for profile in content.profiles:
            line = f"- [{profile.title}](references/profiles/{profile.filename})"
            if profile.description:
                line += f" — {profile.description}"
            lines.append(line)

    if content.scripts:
        lines += [
            "",
            "## Scripts",
            "",
            "Executable helpers this skill can run directly:",
            "",
        ]
        for source in content.scripts:
            relative = source.relative_to(skill.root).as_posix()
            lines.append(f"- [{humanize(source.stem)}]({relative})")

    if content.assets:
        lines += [
            "",
            "## Assets",
            "",
            "Supporting files this skill can read, copy, or fill in:",
            "",
        ]
        for source in content.assets:
            relative = source.relative_to(skill.root).as_posix()
            lines.append(f"- [{humanize(source.stem)}]({relative})")

    return "\n".join(lines).rstrip() + "\n"
