"""Write one bundle, and replace an existing one without ever losing it.

Everything here is about files rather than meaning. What a bundle contains was
decided by the renderer; this module writes those bytes with newlines the host
cannot rewrite, copies what a build ships unchanged, and commits each artifact so
that a failure leaves the previous one exactly as it was.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .icons import ICON_OUTPUTS
from .model import DegardisError, Skill
from .bundlepaths import copied_path


OPENAI_INTERFACE_FIELDS = (
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
)

# The placeholder a source writes where the invoked skill belongs, so one
# authored prompt renders for whatever host the target file is read by.
NAME_PLACEHOLDER = "{name}"

# The character each host puts before a skill name in a typed invocation. Every
# shape is listed, not only the one a target here renders, because validation
# reads this to recognize a source that hardcoded some host's syntax.
HOST_INVOCATION_PREFIXES = ("$", "/", "@", "#")
OPENAI_INVOCATION_PREFIX = "$"


def render_invocations(text: str, name: str, prefix: str) -> str:
    """Resolve the name placeholder into one host's invocation syntax."""
    return text.replace(NAME_PLACEHOLDER, f"{prefix}{name}")


def openai_metadata(interface: dict, icon_roles: set[str], name: str) -> str:
    """Render agents/openai.yaml so callers can write it or measure it alike."""
    emitted = dict(interface)
    emitted.pop("icon", None)
    for role in icon_roles:
        emitted[f"icon_{role}"] = f"./{ICON_OUTPUTS[role]}"
    if "default_prompt" in emitted:
        emitted["default_prompt"] = render_invocations(
            str(emitted["default_prompt"]), name, OPENAI_INVOCATION_PREFIX
        )
    lines = ["interface:"]
    for key in OPENAI_INTERFACE_FIELDS:
        if key in emitted:
            lines.append(f"  {key}: {json.dumps(str(emitted[key]))}")
    return "\n".join(lines) + "\n"


def artifact_mode(relative: str) -> str:
    """Report the permission bits the archive records for one bundle path."""
    return "755" if relative.startswith("scripts/") else "644"


def write_generated(path: Path, text: str) -> None:
    """Write one generated file with newlines the host cannot rewrite.

    Without this the same source builds a different bundle on Windows than on
    Linux, byte for byte, and the archive carries that difference downstream.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _remove_artifacts(artifacts: tuple[Path, ...]) -> None:
    for path in artifacts:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


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
    """Replace one artifact set, rolling every member back if commit fails.

    A folder build owns a matched directory and ZIP. Both promises have the same
    failure boundary: no old artifact is lost merely because the staged one
    cannot be committed.
    """
    backup_root = Path(tempfile.mkdtemp(prefix="degardis-backup-"))
    backups: list[tuple[Path, Path]] = []
    try:
        for artifact in artifacts:
            if not (artifact.is_symlink() or artifact.is_file() or artifact.is_dir()):
                continue
            backup = backup_root / artifact.name
            _copy_artifact(artifact, backup)
            backups.append((artifact, backup))
    except Exception:
        shutil.rmtree(backup_root, ignore_errors=True)
        raise
    try:
        _remove_artifacts(artifacts)
        _copy_artifact(staged, destination)
    except Exception as exc:
        rollback_errors: list[OSError] = []
        try:
            _remove_artifacts(artifacts)
        except OSError as rollback_error:
            rollback_errors.append(rollback_error)
        for artifact, backup in reversed(backups):
            if not (backup.is_symlink() or backup.is_file() or backup.is_dir()):
                continue
            try:
                _copy_artifact(backup, artifact)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise DegardisError(
                f"Failed to replace {label} and restore its previous artifacts; "
                f"backups remain at {backup_root}"
            ) from exc
        shutil.rmtree(backup_root, ignore_errors=True)
        raise
    shutil.rmtree(backup_root, ignore_errors=True)


def write_bundle(
    skill: Skill,
    skill_text: str,
    pages: dict[str, str],
    copied: dict[str, list[Path]],
    icon_sources: dict[str, Path],
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
        openai_metadata(skill.interface, set(icon_sources), skill.name),
    )


class ArchivePackager:
    def create(self, source: Path, destination: Path) -> Path:
        # Imported here rather than beside the module's other imports: only a
        # `--zip` build reaches this, and it is among the costlier imports of
        # every command that never writes an archive.
        import zipfile

        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o100755 if relative.startswith("scripts/") else 0o100644
                info.external_attr = mode << 16
                archive.writestr(info, path.read_bytes())
        return destination
