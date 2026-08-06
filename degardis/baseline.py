"""Measure a skill as an earlier revision of the repository holds it.

An edit's cost is only decision-relevant as a difference, so answering "did this
instruction cost more than the loading it prevents" needs a before as well as an
after. Obtaining the before by moving the working tree — a stash, a checkout, a
branch switch — puts uncommitted work at risk for a measurement that writes
nothing, and leaves it at risk for as long as the measurement takes. `git
archive` reads the revision straight out of the object database, so the index and
the working tree are untouched whatever the measurement finds.

Only the budget numbers are taken from the baseline. Its diagnostics are not
reported and never affect exit status: the caller asked what an edit changed, not
whether a revision they already have would pass today's checks.
"""

from __future__ import annotations

import subprocess
import tarfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .model import DegardisError
from .validate import inspect_skills


def _git(root: Path, *arguments: str) -> tuple[int, bytes, str]:
    """Run one git command in `root`, returning its status, stdout, and stderr.

    Arguments are passed as a list, never as a shell string, so a revision that
    happens to contain shell syntax is a revision and nothing else.
    """
    try:
        finished = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise DegardisError(
            f"--baseline needs git, which could not be run: {error}"
        ) from error
    return (
        finished.returncode,
        finished.stdout,
        finished.stderr.decode("utf-8", "replace").strip(),
    )


def _git_output(root: Path, *arguments: str, failure: str) -> bytes:
    """Run one git command that must succeed, keeping git's own message.

    Git reports what went wrong but not what was being attempted, so every
    failure names the option that ran the command and what it needed, and git's
    message follows.
    """
    status, output, error = _git(root, *arguments)
    if status:
        raise DegardisError(
            f"--baseline {failure}: "
            f"{error or f'git exited with status {status}'}"
        )
    return output


def _work_tree(source: Path) -> Path:
    """Locate the git work tree that holds the skill."""
    located = _git_output(
        source,
        "rev-parse",
        "--show-toplevel",
        failure=f"needs {source} to be inside a git work tree",
    )
    return Path(located.decode("utf-8", "replace").strip()).resolve()


def _checked_ref(ref: str) -> str:
    """Refuse a revision git would read as an option rather than as a revision.

    `--end-of-options` is too recent to rely on for this, and no revision
    spelling git accepts begins with a dash, so nothing valid is refused.
    """
    if not ref or ref.startswith("-"):
        raise DegardisError(
            f"--baseline needs a git revision; git would read {ref!r} as an option"
        )
    return ref


def _tree_spec(revision: str, relative: str) -> str:
    """Name the tree that holds the skill at this revision.

    A skill directory that is itself the repository root has no path within the
    revision, so the commit's own tree is the one to read.
    """
    return f"{revision}^{{tree}}" if relative == "." else f"{revision}:{relative}"


def _extract(archive: bytes, destination: Path) -> None:
    """Unpack a git archive, using tarfile's own filter where the runtime has one.

    The archive comes from the caller's repository rather than from a stranger,
    but the filter is what keeps a member path or a link target from resolving
    outside the temporary directory, and it is absent before Python 3.12 and its
    backports.
    """
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(destination, filter="data")
        else:
            tar.extractall(destination)


def _measure(path: Path, ref: str, profiles: list[str] | None) -> dict[str, Any]:
    """Measure one skill at one revision, reporting why when it cannot be."""
    source = path.resolve()
    root = _work_tree(source)
    status, resolved, failure = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if status:
        # git names neither the revision nor the repository when a revision does
        # not resolve, and both are what the caller has to correct.
        raise DegardisError(
            f"--baseline cannot resolve {ref!r} to a commit in {root}: "
            f"{failure or 'git reported no such revision'}"
        )
    revision = resolved.decode("utf-8", "replace").strip()
    try:
        relative = source.relative_to(root).as_posix()
    except ValueError as error:
        raise DegardisError(
            f"--baseline cannot place {source} inside the git work tree at {root}"
        ) from error
    spec = _tree_spec(revision, relative)

    status, kind, _ = _git(root, "cat-file", "-t", spec)
    if status or kind.decode("utf-8", "replace").strip() != "tree":
        return {"ref": ref, "state": "absent"}

    archived = _git_output(
        root,
        "archive",
        "--format=tar",
        spec,
        failure=f"could not read {relative} at {ref}",
    )
    with TemporaryDirectory(prefix="degardis-baseline-") as directory:
        # A skill directory has to be named after the skill it holds, so the
        # revision is unpacked under the name the path already carries rather
        # than under the temporary directory's own.
        extracted = Path(directory) / source.name
        _extract(archived, extracted)
        result = inspect_skills([extracted], profiles)[0]

    markdown = result.get("skill_markdown", {})
    if not markdown.get("bytes"):
        # The revision holds the skill but nothing could be generated from it, so
        # every size would read zero and the delta would be a plausible lie.
        return {"ref": ref, "state": "unmeasured"}
    return {
        "ref": ref,
        "state": "measured",
        "skill_markdown": markdown,
        "reference_bytes": result.get("reference_bytes", {}),
    }


def measure_baselines(
    paths: list[Path],
    ref: str,
    profiles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Measure every selected skill at one revision, aligned with `inspect_skills`.

    Each result carries the state the comparison is in, so a skill the revision
    does not hold, or holds unmeasurably, is reported as such beside the skills
    that did compare rather than dropped or counted as zero.
    """
    checked = _checked_ref(ref)
    return [_measure(path, checked, profiles) for path in paths]
