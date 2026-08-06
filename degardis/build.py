from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .model import DegardisError, Diagnostics
from .package import (
    ArchivePackager,
    ArtifactWriter,
    replace_skill_artifacts,
)
from .resolver import SkillResolver
from .validate import inspect_skills


class SkillCompiler:
    def __init__(self, sources: Path | list[Path]) -> None:
        self.resolver = SkillResolver(sources)
        self.writer = ArtifactWriter()
        self.packager = ArchivePackager()
        self.warnings: list[str] = []

    def _check_output_path(self, output: Path) -> None:
        resolved_output = output.resolve()
        for source in self.resolver.skill_paths:
            resolved_source = source.resolve()
            if (
                resolved_output == resolved_source
                or resolved_output in resolved_source.parents
                or resolved_source in resolved_output.parents
            ):
                raise DegardisError(
                    f"Output directory {resolved_output} must not overlap "
                    f"skill source {resolved_source}"
                )

    def build(
        self,
        output: Path,
        profiles: list[str] | None = None,
        as_zip: bool = False,
    ) -> list[Path]:
        self._check_output_path(output)
        diagnostics = Diagnostics()
        for result in inspect_skills(self.resolver.skill_paths):
            diagnostics.add_errors(result["errors"])
            diagnostics.add_warnings(result["warnings"])
        self.warnings = list(diagnostics.warnings)
        diagnostics.raise_if_errors()
        bundles = self.resolver.collect(profiles)
        if not bundles:
            raise DegardisError("at least one skill is required")
        output.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for bundle in bundles:
            name = bundle.primary.name
            with TemporaryDirectory(
                prefix="degardis-build-",
            ) as directory:
                staging_root = Path(directory)
                staged_folder = staging_root / name
                self.writer.write_skill(bundle, staged_folder)
                if as_zip:
                    destination = output / f"{name}.zip"
                    staged = staging_root / f"{name}.zip"
                    self.packager.create(staged_folder, staged)
                else:
                    destination = output / name
                    staged = staged_folder
                replace_skill_artifacts(
                    output,
                    name,
                    staged,
                    destination,
                )
            paths.append(destination)
        return paths


def build_skills(
    sources: Path | list[Path],
    output_dir: Path,
    profiles: list[str] | None = None,
    as_zip: bool = False,
) -> list[Path]:
    return SkillCompiler(sources).build(output_dir, profiles, as_zip)
