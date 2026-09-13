"""Write a new source tree that compiles, and shows the shape of the format.

A starter is read more often than it is run. What it is for is to answer, in
files rather than in prose, the four questions an author has on the first day:
where does a thing go, what is its name, where do its fields live, and what does
the compiler do with them.

So it ships one task that validates and builds as it stands, and it creates the
directories the rest of the format uses without selecting them — an empty
directory selected by the manifest would be a pattern matching nothing, which is
a finding, and a first run that fails teaches the wrong thing.

The starter skill names no principle, and `principles/` is created empty. A
principle is authored in the skill that uses it, so writing one here would put
the compiler's words in someone else's skill; and a skill naming a principle no
file states would refuse to compile on the first run.

Nothing generated here declares an id. That is the point being made: the
filename is the identity, and a starter that wrote one out would teach the
opposite of what the readers enforce.
"""

from __future__ import annotations

from pathlib import Path

from .model import CURRENT_FORMAT_VERSION, NAME_PATTERN, DegardisError, filename_title


STARTER_TASK = "primary"

# Created but not selected: the manifest names a key only once a directory holds
# something, so an author adds the key when they add the first file.
SCAFFOLD_DIRECTORIES = (
    "principles",
    "knowledge",
    "facets",
    "guides",
)


def _manifest(name: str, title: str) -> str:
    return f"""\
name: {name}
format_version: {CURRENT_FORMAT_VERSION}
version: 0.1.0
description: >-
  One sentence a host reads when it is deciding among many skills, saying what
  this one is for and when to reach for it.
purpose: >-
  One short paragraph the agent reads once this skill has been selected, saying
  what it is about to do and what the work is in aid of.
tasks:
# Every task, in first-match routing order. Order overlaps so the intended task
# is the first one whose cue matches.
- {STARTER_TASK}
content:
  tasks:
  - tasks/*.md
  # Add a key here as you add the directory's first file. Each selects Markdown
  # sources whose file stem is the construct's id:
  #   principles: [principles/*.md]
  #   knowledge:  [knowledge/*.md]
  #   facets:     [facets/*.md]
  #   guides: [guides/*.md]
interface:
  display_name: {title}
  short_description: What this skill does, briefly
  default_prompt: Use {name} to do this work.
"""


def _task(title: str) -> str:
    return f"""\
---
title: {title}
recognize:
- "[replace with a request-visible cue for this task]"
goal: "[replace with the observable finished state]"
---

Write guidance specific to this task here. Put reusable subject matter in
knowledge.

Name the knowledge a task needs in its frontmatter:

    knowledge:
    - how-this-works
    - what-must-hold

Each file in `knowledge/` declares a `kind`: `concept`, `fact`, `constraint`, or
`guidance`. The compiler groups those kinds in that order and preserves this
task's order within each kind. It also follows what knowledge `requires` and
compiles the whole closure into this page, so the agent reads one page rather
than a chain of them.

Cross-task working discipline goes in `principles/`, one file per principle.
Name the ones this skill uses in `skill.yaml`:

    principles:
    - state-your-evidence

The generated `SKILL.md` lists each selected principle and links to its page.
Write the file first: a name with no `principles/<id>.md` beside it does not
compile.

Run `degardis manual` for the topic that explains any part of this file.
"""


def create_skill(root: Path, name: str) -> Path:
    """Write a new skill source tree, refusing to write over one that exists."""
    if not NAME_PATTERN.fullmatch(name):
        raise DegardisError(
            f"{name} is not a skill name; use lowercase letters, digits, and "
            "single hyphens",
            "manifest.invalid-name",
        )
    destination = root / name
    if destination.exists():
        raise DegardisError(f"{destination} already exists")
    title = filename_title(name)
    (destination / "tasks").mkdir(parents=True)
    for directory in SCAFFOLD_DIRECTORIES:
        (destination / directory).mkdir(exist_ok=True)
    _write(destination / "skill.yaml", _manifest(name, title))
    _write(
        destination / "tasks" / f"{STARTER_TASK}.md",
        _task(filename_title(STARTER_TASK)),
    )
    return destination


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
