"""Where each generated file sits in a bundle, stated once.

A path is a contract: the root links to a task page, the profile index links to
a profile page, and a check resolves both against what the build wrote. Three
parts of the compiler therefore have to agree about the same string, and the way
they agree is by asking here rather than by each spelling it.

The shape is flat on purpose. `SKILL.md` routes straight to a task page, links to
the skill's principle pages, and points to the profile index. The profile index
is the one *situational* lookup, because which profiles apply is a decision only
the situation in front of the agent can settle. There is no generated layer
between the root and a task: an index a run always passes through is a load that
answers no question.
"""

from __future__ import annotations


ROOT = "SKILL.md"

REFERENCES_DIRECTORY = "references"
TASKS_DIRECTORY = f"{REFERENCES_DIRECTORY}/tasks"
PROFILES_DIRECTORY = f"{REFERENCES_DIRECTORY}/profiles"
PRINCIPLES_DIRECTORY = f"{REFERENCES_DIRECTORY}/principles"
GUIDES_DIRECTORY = f"{REFERENCES_DIRECTORY}/guides"
AGENTS_DIRECTORY = "agents"

PROFILE_INDEX = f"{PROFILES_DIRECTORY}/index.md"
OPENAI_METADATA = f"{AGENTS_DIRECTORY}/openai.yaml"

# The profile id the index would collide with, since the index occupies it.
RESERVED_PROFILE_IDS = frozenset({"index"})


def task_path(task_id: str) -> str:
    """The page one task's complete knowledge is compiled into."""
    return f"{TASKS_DIRECTORY}/{task_id}.md"


def profile_path(profile_id: str) -> str:
    """The page one profile is written to, beside the index that lists it."""
    return f"{PROFILES_DIRECTORY}/{profile_id}.md"


def principle_path(principle_id: str) -> str:
    """The authored page a principle activation link opens."""
    return f"{PRINCIPLES_DIRECTORY}/{principle_id}.md"


def guide_path(guide_id: str) -> str:
    """The separately loaded page a task opens when its activation applies."""
    return f"{GUIDES_DIRECTORY}/{guide_id}.md"


def copied_path(key: str, source_relative: str) -> str:
    """Return the bundle address for an unchanged script or asset."""
    return source_relative
