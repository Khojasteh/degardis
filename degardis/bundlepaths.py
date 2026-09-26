"""Where each generated file sits in a bundle, stated once.

A path is a contract: the root links to a task page, the facet index links to
a facet page, and a check resolves both against what the build wrote. Three
parts of the compiler therefore have to agree about the same string, and the way
they agree is by asking here rather than by each spelling it.

The shape is flat on purpose. `SKILL.md` routes straight to a task page, links to
the skill's principle pages, and points to the facet index. The facet index
is the one *situational* lookup, because which facets apply is a decision only
the situation in front of the agent can settle. There is no generated layer
between the root and a task: an index a run always passes through is a load that
answers no question.

When principles or guides exist, the instruction register is the generated file
that is not part of that shape. It is an asset: a form the agent copies into a
record of its own, naming each principle and guide by identity rather than linking
it, so nothing in the bundle points at a page because the register listed it.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass


REFERENCES_DIRECTORY = "references"
TASKS_DIRECTORY = f"{REFERENCES_DIRECTORY}/tasks"
FACETS_DIRECTORY = f"{REFERENCES_DIRECTORY}/facets"
PRINCIPLES_DIRECTORY = f"{REFERENCES_DIRECTORY}/principles"
GUIDES_DIRECTORY = f"{REFERENCES_DIRECTORY}/guides"
AGENTS_DIRECTORY = "agents"
ASSETS_DIRECTORY = "assets"

# Two names this compiler does not choose. A host finds a skill by opening
# `SKILL.md` and reads its interface from `agents/openai.yaml`, so neither can
# move: a source file that would be copied over one is reported instead.
ROOT = "SKILL.md"
OPENAI_METADATA = f"{AGENTS_DIRECTORY}/openai.yaml"

# The rest are names this compiler picked, and a name one party picked is the
# one that gives way. Each is the address its file prefers; where the source
# already puts a file there, the author wrote that file on purpose and the
# generated one is written beside it under a free name.
FACET_INDEX = f"{FACETS_DIRECTORY}/index.md"

# When emitted, the register sits beside the generated icons rather than under
# `references/`, because it is not a page of the skill: it is a form the agent
# copies out and keeps its own copy of, somewhere this bundle cannot address.
REGISTER = f"{ASSETS_DIRECTORY}/instruction-register.md"
ICON_OUTPUTS = {
    "small": f"{ASSETS_DIRECTORY}/icon-small.png",
    "large": f"{ASSETS_DIRECTORY}/icon-large.png",
}


@dataclass(frozen=True)
class Addresses:
    """Where one bundle's compiler-named files actually land.

    A module asks for these rather than reading the constants, because the
    preferred name is only where a file goes when the source left that address
    free. Reading `REGISTER` directly would be right for almost every skill and
    wrong for the one that ships a register of its own.
    """

    facet_index: str
    register: str
    icons: dict[str, str]


def resolve_addresses(taken: AbstractSet[str]) -> Addresses:
    """Place every compiler-named file, yielding each address the source claims.

    Resolved in one fixed order, each choice joining what is taken before the
    next is made, so two files that prefer one address cannot both be sent to
    the same free one and the result does not depend on a dictionary's order.
    Addresses are compared without regard to letter case, because a Windows or
    macOS file system writes two names that differ only in case to one file.
    """
    claimed = {address.casefold() for address in taken}

    def place(preferred: str) -> str:
        address = _free(preferred, claimed)
        claimed.add(address.casefold())
        return address

    return Addresses(
        facet_index=place(FACET_INDEX),
        register=place(REGISTER),
        icons={role: place(ICON_OUTPUTS[role]) for role in sorted(ICON_OUTPUTS)},
    )


def _free(preferred: str, taken: AbstractSet[str]) -> str:
    """The preferred address, or the first numbered name beside it that is free.

    `taken` holds casefolded addresses.
    """
    if preferred.casefold() not in taken:
        return preferred
    directory, _, name = preferred.rpartition("/")
    stem, dot, suffix = name.partition(".")
    counter = 1
    while True:
        candidate = f"{stem}-{counter}{dot}{suffix}"
        if directory:
            candidate = f"{directory}/{candidate}"
        if candidate.casefold() not in taken:
            return candidate
        counter += 1


def task_path(task_id: str) -> str:
    """The page one task's complete knowledge is compiled into."""
    return f"{TASKS_DIRECTORY}/{task_id}.md"


def facet_path(facet_id: str) -> str:
    """The page one facet is written to, beside the index that lists it."""
    return f"{FACETS_DIRECTORY}/{facet_id}.md"


def principle_path(principle_id: str) -> str:
    """The authored page a principle activation link opens."""
    return f"{PRINCIPLES_DIRECTORY}/{principle_id}.md"


def guide_path(guide_id: str) -> str:
    """The separately loaded page a task opens when its activation applies."""
    return f"{GUIDES_DIRECTORY}/{guide_id}.md"


def copied_path(key: str, source_relative: str) -> str:
    """Return the bundle address for an unchanged script or asset."""
    return source_relative
