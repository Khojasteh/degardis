"""Write one bundle, and replace an existing one without ever losing it.

Everything here is about files rather than meaning. What a bundle contains was
decided by the renderer; this module writes those bytes with newlines the host
cannot rewrite, copies what a build ships unchanged, and commits each artifact so
that a failure leaves the previous one exactly as it was.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .model import DegardisError, Skill
from .bundlepaths import copied_path
from .yamlsource import yaml_string


OPENAI_INTERFACE_FIELDS = (
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
)

OPENAI_INVOCATION_PREFIX = "$"


def render_invocations(text: str, name: str, prefix: str) -> str:
    """Render a host-neutral skill name in one target's invocation syntax."""
    pattern = rf"(?<![a-z0-9$@/#-]){re.escape(name)}(?![a-z0-9-])"
    return re.sub(pattern, f"{prefix}{name}", text)


def openai_metadata(interface: dict, icons: Mapping[str, str], name: str) -> str:
    """Render agents/openai.yaml so callers can write it or measure it alike."""
    emitted = dict(interface)
    emitted.pop("icon", None)
    for role, address in sorted(icons.items()):
        emitted[f"icon_{role}"] = f"./{address}"
    if "default_prompt" in emitted:
        emitted["default_prompt"] = render_invocations(
            str(emitted["default_prompt"]), name, OPENAI_INVOCATION_PREFIX
        )
    lines = ["interface:"]
    for key in OPENAI_INTERFACE_FIELDS:
        if key in emitted:
            lines.append(f"  {key}: {yaml_string(str(emitted[key]))}")
    return "\n".join(lines) + "\n"


def executable_paths(root: Path, copied: Mapping[str, list[Path]]) -> frozenset[str]:
    """The bundle paths a build marks executable: every file `content.scripts` selects.

    Selection decides, not location. A script keeps the path it has in the
    source, which may be anywhere the manifest selects it from, and a file under
    a `scripts/` directory that the manifest selects as an asset is not a
    script.
    """
    return frozenset(
        copied_path("scripts", path.relative_to(root).as_posix())
        for path in copied.get("scripts", [])
    )


def _permissions(relative: str, executable: frozenset[str]) -> int:
    """The permission bits both artifact forms give one bundle path.

    The rule comes from the manifest's selection alone, never from the source
    file, so a checkout that drops or adds an executable bit still builds the
    same bundle.
    """
    return 0o755 if relative in executable else 0o644


def artifact_mode(relative: str, executable: frozenset[str]) -> str:
    """Report the permission bits a build records for one bundle path."""
    return f"{_permissions(relative, executable):o}"


def write_generated(path: Path, text: str) -> None:
    """Write one generated file with newlines the host cannot rewrite.

    Without this the same source builds a different bundle on Windows than on
    Linux, byte for byte, and the archive carries that difference downstream.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _exists(path: Path) -> bool:
    return path.is_symlink() or path.exists()


def _copy_artifact(source: Path, destination: Path) -> None:
    if source.is_symlink():
        destination.symlink_to(
            source.readlink(), target_is_directory=source.is_dir()
        )
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


def replace_skill_artifacts(
    output: Path, skill_name: str, staged: Path, destination: Path
) -> None:
    artifacts = (output / skill_name, output / f"{skill_name}.zip")
    _replace_artifacts(artifacts, skill_name, staged, destination)


def _replace_artifacts(
    artifacts: tuple[Path, ...], label: str, staged: Path, destination: Path
) -> None:
    """Replace one artifact set, touching the old one only by rename.

    A folder build owns a matched directory and ZIP. The new artifact is first
    copied into a work directory beside them, which puts it on their file
    system, and nothing existing changes until that copy is complete. The old
    artifacts then move aside and the new one moves into place, each by rename:
    a file held open elsewhere fails the rename before anything is lost, and any
    failure or interruption before the new artifact is in place, Ctrl-C
    included, moves every old one back.
    """
    output = destination.parent
    work = Path(tempfile.mkdtemp(prefix=f".{label}-", dir=output))
    incoming = work / "incoming" / destination.name
    previous = work / "previous"
    moved: list[tuple[Path, Path]] = []
    try:
        _copy_artifact(staged, incoming)
        previous.mkdir()
        for artifact in artifacts:
            if _exists(artifact):
                aside = previous / artifact.name
                # Recorded first, so an interruption the moment the rename
                # returns cannot leave a moved artifact the rollback forgets.
                moved.append((artifact, aside))
                os.replace(artifact, aside)
        os.replace(incoming, destination)
    except BaseException as exc:
        stranded: list[OSError] = []
        for artifact, aside in reversed(moved):
            if not _exists(aside):
                continue
            try:
                os.replace(aside, artifact)
            except OSError as error:
                stranded.append(error)
        if stranded:
            raise DegardisError(
                f"Failed to replace {label} and restore its previous artifacts; "
                f"they remain at {previous}"
            ) from exc
        shutil.rmtree(work, ignore_errors=True)
        raise
    try:
        shutil.rmtree(work)
    except OSError as error:
        raise DegardisError(
            f"Replaced {label}, but its previous artifacts remain at {work}"
        ) from error


def write_bundle(
    skill: Skill,
    skill_text: str,
    pages: dict[str, str],
    copied: dict[str, list[Path]],
    icon_addresses: Mapping[str, str],
    icon_assets: dict[str, bytes],
    destination: Path,
) -> None:
    """Write one complete bundle into a directory that is not yet a bundle.

    The icons written are the bytes the compilation already converted, which is
    how the icon was checked at all. Converting them again here would cost what
    the first conversion cost and would leave the size a report states and the
    file a build writes separately derived, so the two could differ.
    """
    destination.mkdir(parents=True, exist_ok=True)
    write_generated(destination / "SKILL.md", skill_text)
    for relative, text in sorted(pages.items()):
        write_generated(destination / relative, text)
    # Scripts and assets retain their source-relative addresses and original bytes.
    for key in ("scripts", "assets"):
        for source in copied.get(key, []):
            relative = source.relative_to(skill.root).as_posix()
            output = copied_path(key, relative)
            path = destination / output
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
    for relative, data in icon_assets.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_generated(
        destination / "agents" / "openai.yaml",
        openai_metadata(skill.interface, icon_addresses, skill.name),
    )
    # Set here rather than left to the process umask, so a folder carries the
    # permissions an archive records and the commit's copy keeps them.
    executable = executable_paths(skill.root, copied)
    for path in destination.rglob("*"):
        if path.is_file():
            relative = path.relative_to(destination).as_posix()
            os.chmod(path, _permissions(relative, executable))


class ArchivePackager:
    def create(
        self, source: Path, destination: Path, executable: frozenset[str]
    ) -> Path:
        # Imported here rather than beside the module's other imports: only a
        # `--zip` build reaches this, and it is among the costlier imports of
        # every command that never writes an archive.
        import zipfile

        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            # Ordered by the POSIX name rather than by `Path`, whose ordering
            # ignores case on Windows and would reorder entries by host.
            files = {
                path.relative_to(source).as_posix(): path
                for path in source.rglob("*")
                if path.is_file()
            }
            for relative, path in sorted(files.items()):
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100000 | _permissions(relative, executable)) << 16
                archive.writestr(info, path.read_bytes())
        return destination
