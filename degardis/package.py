from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from .icons import ICON_OUTPUTS, render_icon_assets
from .markdown import (
    entry_filename,
    entry_markdown,
    skill_markdown,
    workflow_filename,
    workflow_markdown,
)
from .model import DegardisError, SkillBundle


def write_generated(path: Path, text: str) -> None:
    """Write one generated file with newlines the host cannot rewrite.

    Without this the same source builds a different bundle on Windows than on
    Linux, byte for byte, and the archive carries that difference downstream.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def remove_skill_artifacts(output: Path, skill_name: str) -> None:
    for path in (output / skill_name, output / f"{skill_name}.zip"):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def _copy_artifact(source: Path, destination: Path) -> None:
    if source.is_symlink():
        destination.symlink_to(
            source.readlink(),
            target_is_directory=source.is_dir(),
        )
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


def replace_skill_artifacts(
    output: Path,
    skill_name: str,
    staged: Path,
    destination: Path,
) -> None:
    artifacts = (output / skill_name, output / f"{skill_name}.zip")
    backup_root = Path(
        tempfile.mkdtemp(prefix="degardis-backup-")
    )
    backups: list[tuple[Path, Path]] = []
    try:
        for artifact in artifacts:
            if not (
                artifact.is_symlink()
                or artifact.is_file()
                or artifact.is_dir()
            ):
                continue
            backup = backup_root / artifact.name
            _copy_artifact(artifact, backup)
            backups.append((artifact, backup))
    except Exception:
        shutil.rmtree(backup_root, ignore_errors=True)
        raise
    try:
        remove_skill_artifacts(output, skill_name)
        _copy_artifact(staged, destination)
    except Exception as exc:
        rollback_errors: list[OSError] = []
        try:
            remove_skill_artifacts(output, skill_name)
        except OSError as rollback_error:
            rollback_errors.append(rollback_error)
        for artifact, backup in reversed(backups):
            if not (
                backup.is_symlink()
                or backup.is_file()
                or backup.is_dir()
            ):
                continue
            try:
                _copy_artifact(backup, artifact)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise DegardisError(
                f"Failed to replace {skill_name} and restore its previous "
                f"artifacts; backups remain at {backup_root}"
            ) from exc
        shutil.rmtree(backup_root, ignore_errors=True)
        raise
    shutil.rmtree(backup_root, ignore_errors=True)


class ArtifactWriter:
    def write_skill(
        self,
        bundle: SkillBundle,
        destination: Path,
        skill_name: str | None = None,
    ) -> None:
        name = skill_name or bundle.primary.name
        content = bundle.content(name)
        icon_assets = render_icon_assets(content.icon_sources)
        destination.mkdir(parents=True, exist_ok=True)
        write_generated(destination / "SKILL.md", skill_markdown(bundle, name))

        for entry in content.entries:
            write_generated(
                destination / "references" / "entries" / entry_filename(entry),
                entry_markdown(entry),
            )

        for workflow in content.workflows:
            if workflow.get("id") == content.skill.primary_workflow:
                continue
            write_generated(
                destination
                / "references"
                / "workflows"
                / workflow_filename(workflow, name),
                workflow_markdown(workflow),
            )

        for profile in content.profiles:
            write_generated(
                destination / "references" / "profiles" / profile.filename,
                profile.text,
            )

        for source in content.scripts:
            path = destination / source.relative_to(content.skill.root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())

        for source in content.assets:
            path = destination / source.relative_to(content.skill.root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())

        for relative, data in icon_assets.items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        self._write_openai_metadata(
            content.skill.interface,
            destination,
            set(content.icon_sources),
        )

    def _write_openai_metadata(
        self,
        interface: dict,
        destination: Path,
        icon_roles: set[str],
    ) -> None:
        emitted = dict(interface)
        emitted.pop("icon", None)
        for role in icon_roles:
            emitted[f"icon_{role}"] = f"./{ICON_OUTPUTS[role]}"
        fields = [
            "display_name",
            "short_description",
            "icon_small",
            "icon_large",
            "brand_color",
            "default_prompt",
        ]
        lines = ["interface:"]
        for key in fields:
            if key in emitted:
                lines.append(f"  {key}: {json.dumps(str(emitted[key]))}")
        write_generated(
            destination / "agents" / "openai.yaml",
            "\n".join(lines) + "\n",
        )


class ArchivePackager:
    def create(self, source: Path, destination: Path) -> Path:
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
