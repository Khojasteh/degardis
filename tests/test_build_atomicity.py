"""A failed build leaves existing artifacts as they were."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis.build import SkillCompiler, build_skills
from degardis.model import DegardisError
from degardis.package import ArtifactWriter

from tests.support import FIXTURES, copy_skills


class BuildAtomicityTests(unittest.TestCase):
    def test_folder_writer_failure_preserves_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            stale_zip = output / "alpha.zip"
            stale_zip.write_bytes(b"existing zip")

            with mock.patch(
                "degardis.build.ArtifactWriter.write_skill",
                side_effect=OSError("injected write failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    build_skills(FIXTURES / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))
            self.assertEqual(b"existing zip", stale_zip.read_bytes())

    def test_zip_packager_failure_preserves_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            existing_zip = artifact.read_bytes()
            stale_folder = output / "alpha"
            stale_folder.mkdir()
            marker = stale_folder / "existing.txt"
            marker.write_text("keep", encoding="utf-8")

            with mock.patch(
                "degardis.build.ArchivePackager.create",
                side_effect=OSError("injected package failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected package failure"):
                    build_skills(FIXTURES / "alpha", output, as_zip=True)

            self.assertEqual(existing_zip, artifact.read_bytes())
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_install_copy_failure_restores_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            stale_zip = output / "alpha.zip"
            stale_zip.write_bytes(b"existing zip")
            original_copytree = shutil.copytree
            failed = False

            def copytree(source, destination, *args, **kwargs):
                nonlocal failed
                if destination == artifact and not failed:
                    failed = True
                    raise OSError("injected install failure")
                return original_copytree(source, destination, *args, **kwargs)

            with mock.patch(
                "degardis.package.shutil.copytree",
                side_effect=copytree,
            ):
                with self.assertRaisesRegex(OSError, "injected install failure"):
                    build_skills(FIXTURES / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))
            self.assertEqual(b"existing zip", stale_zip.read_bytes())

    def test_rebuild_does_not_rename_installed_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("replace", encoding="utf-8")

            with mock.patch(
                "degardis.package.Path.replace",
                side_effect=PermissionError("Windows denied directory rename"),
            ):
                rebuilt = build_skills(FIXTURES / "alpha", output)[0]

            self.assertEqual(artifact, rebuilt)
            self.assertFalse(marker.exists())

    def test_build_stages_outside_the_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            compiler = SkillCompiler(FIXTURES / "alpha")
            original_write = compiler.writer.write_skill
            destinations = []

            def write_skill(bundle, destination, skill_name=None):
                destinations.append(destination)
                return original_write(bundle, destination, skill_name)

            with mock.patch.object(
                compiler.writer,
                "write_skill",
                side_effect=write_skill,
            ):
                compiler.build(output)

            self.assertEqual(1, len(destinations))
            self.assertFalse(
                destinations[0].resolve().is_relative_to(output.resolve())
            )

    def test_multi_skill_failure_commits_only_completed_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            build_skills(FIXTURES, output)
            markers = {}
            for name in ("alpha", "beta", "gamma"):
                marker = output / name / "existing.txt"
                marker.write_text("keep", encoding="utf-8")
                markers[name] = marker
            original_write = ArtifactWriter.write_skill

            def write_skill(writer, bundle, destination, skill_name=None):
                if bundle.primary.name == "beta":
                    raise OSError("injected second-skill failure")
                return original_write(writer, bundle, destination, skill_name)

            with mock.patch.object(
                ArtifactWriter,
                "write_skill",
                autospec=True,
                side_effect=write_skill,
            ):
                with self.assertRaisesRegex(
                    OSError, "injected second-skill failure"
                ):
                    build_skills(FIXTURES, output)

            self.assertFalse(markers["alpha"].exists())
            self.assertEqual("keep", markers["beta"].read_text(encoding="utf-8"))
            self.assertEqual("keep", markers["gamma"].read_text(encoding="utf-8"))

    def test_build_rejects_output_that_overlaps_sources_without_deleting_them(self):
        for output_kind in ("source", "parent"):
            with self.subTest(output_kind=output_kind):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha"
                    output = source if output_kind == "source" else root
                    with self.assertRaisesRegex(
                        DegardisError, "must not overlap skill source"
                    ):
                        build_skills(source, output)
                    self.assertTrue((source / "skill.yaml").is_file())
                    self.assertTrue((source / "scripts" / "greet.py").is_file())
