"""Build every selected skill, checking them all before writing any.

A build is atomic per skill: staging happens outside the output directory, a
failure leaves an existing artifact exactly as it was, and a sibling that
completed still commits. Every skill is checked before the first byte is
written, so a run that reports a failure has changed nothing on the way to it.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .model import DegardisError, Diagnostics
from .package import ArchivePackager, replace_skill_artifacts, write_bundle
from .registry import discover_skill_paths
from .validate import Inspection, compile_all, promote_warnings, result_dict


class SkillCompiler:
    def __init__(self, sources: Path | list[Path]) -> None:
        paths = [sources] if isinstance(sources, Path) else list(sources)
        self.skill_paths = discover_skill_paths(paths)
        self.packager = ArchivePackager()
        self.warnings: list[str] = []
        self.inspections: list[Inspection] = []

    def _check_output_path(self, output: Path) -> None:
        resolved_output = output.resolve()
        for source in self.skill_paths:
            resolved_source = source.resolve()
            if (
                resolved_output == resolved_source
                or resolved_output in resolved_source.parents
                or resolved_source in resolved_output.parents
            ):
                raise DegardisError(
                    f"Output directory {resolved_output} must not overlap "
                    f"skill source {resolved_source}",
                    "output.source-overlap",
                )

    def build(
        self,
        output: Path,
        as_zip: bool = False,
        *,
        fail_on_warning: bool = False,
    ) -> list[Path]:
        """Compile and check every skill, then commit each bundle in turn.

        fail_on_warning promotes warnings before that check rather than after
        the build, so a source the caller's own standard rejects leaves the
        output directory exactly as it was instead of gaining a bundle it then
        fails.
        """
        self._check_output_path(output)
        self.inspections = compile_all(self.skill_paths)
        results = [result_dict(inspection) for inspection in self.inspections]
        if fail_on_warning:
            promote_warnings(results)
        diagnostics = Diagnostics()
        for result in results:
            # The records, not the message lists beside them: a build that stops
            # owes its caller the check code the same finding carries in a
            # report, and only the record still holds it.
            diagnostics.add(result["diagnostics"])
        self.warnings = list(diagnostics.warnings)
        diagnostics.raise_if_errors()
        if not self.inspections:
            raise DegardisError("at least one skill is required")
        output.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for inspection in self.inspections:
            paths.append(self._commit(inspection, output, as_zip))
        return paths

    def _commit(
        self, inspection: Inspection, output: Path, as_zip: bool
    ) -> Path:
        skill = inspection.skill
        compiled = inspection.compiled
        if skill is None or compiled is None or compiled.rendered is None:
            raise DegardisError(
                f"{inspection.root}: nothing was compiled for this skill"
            )
        name = skill.name
        with TemporaryDirectory(prefix="degardis-build-") as directory:
            staging_root = Path(directory)
            staged_folder = staging_root / name
            write_bundle(
                skill,
                compiled.rendered.skill_text,
                compiled.rendered.execution_modules,
                compiled.rendered.pages,
                compiled.content.selected,
                compiled.content.icon_sources,
                staged_folder,
            )
            if as_zip:
                destination = output / f"{name}.zip"
                staged = staging_root / f"{name}.zip"
                self.packager.create(staged_folder, staged)
            else:
                destination = output / name
                staged = staged_folder
            replace_skill_artifacts(output, name, staged, destination)
        return destination

    @property
    def skills(self) -> list:
        return [
            inspection.skill
            for inspection in self.inspections
            if inspection.skill is not None
        ]


def build_skills(
    sources: Path | list[Path],
    output_dir: Path,
    as_zip: bool = False,
    *,
    fail_on_warning: bool = False,
) -> list[Path]:
    return SkillCompiler(sources).build(
        output_dir, as_zip, fail_on_warning=fail_on_warning
    )
