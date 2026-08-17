"""What a build writes, and what it leaves alone when it cannot finish."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis import wording
from degardis.build import SkillCompiler, build_skills
from degardis.icons import ICON_OUTPUTS
from degardis.model import DegardisError

from tests.support import (
    codes,
    copy_skills,
    edit_workflow,
    edit_yaml,
    folder_names,
    folder_text,
    inspect_one,
    set_content_patterns,
    set_interface_fields,
    write_raster_icon,
    write_text,
    zip_names,
    zip_text,
)


class FolderBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def build(self, **kwargs) -> list[Path]:
        return build_skills(self.root, self.output, **kwargs)

    def test_a_bundle_ships_the_document_the_pages_and_the_copied_files(self):
        paths = self.build()
        names = folder_names(paths[0])
        self.assertIn("SKILL.md", names)
        self.assertIn("agents/openai.yaml", names)
        self.assertIn("scripts/greet.py", names)
        self.assertIn("assets/template.md", names)
        self.assertNotIn("references/policies/run-authority.md", names)
        self.assertIn("references/patterns/inspect-plan-act-notes.md", names)

    def test_no_machine_model_is_emitted_beside_the_document(self):
        """Format 2 emits no workflow, step, protocol, record, runtime,
        coverage, or source-map file: the document is the artifact."""
        names = folder_names(self.build()[0])
        self.assertEqual([], [name for name in names if name.endswith(".json")])
        self.assertEqual(
            [],
            [
                name
                for name in names
                if name.startswith(("workflows/", "policies/", "protocols/", "records/"))
            ],
        )

    def test_generated_text_uses_one_line_ending_on_every_host(self):
        text = (self.build()[0] / "SKILL.md").read_bytes()
        self.assertNotIn(b"\r\n", text)

    def test_a_copied_file_keeps_its_bytes(self):
        artifact = self.build()[0]
        self.assertEqual(
            (self.root / "alpha" / "scripts" / "greet.py").read_bytes(),
            (artifact / "scripts" / "greet.py").read_bytes(),
        )

    def test_a_rebuild_is_byte_identical(self):
        first = (self.build()[0] / "SKILL.md").read_bytes()
        second = (self.build()[0] / "SKILL.md").read_bytes()
        self.assertEqual(first, second)

    def test_a_rebuild_replaces_the_previous_bundle(self):
        artifact = self.build()[0]
        stale = artifact / "references" / "stale.md"
        write_text(stale, "# Stale\n")
        self.build()
        self.assertFalse(stale.exists())

    def test_the_document_is_readable_without_any_optional_page(self):
        artifact = self.build()[0]
        shutil.rmtree(artifact / "references")
        text = folder_text(artifact, "SKILL.md")
        self.assertIn(f"## {wording.CONTRACT_HEADING}", text)
        execution = folder_text(artifact, "execution/run-01.md")
        self.assertIn(f"**{wording.VERIFY}**", execution)


class ArchiveBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def test_an_archive_carries_the_same_files_as_a_folder(self):
        folder = build_skills(self.root / "alpha", self.output / "folder")[0]
        archive = build_skills(
            self.root / "alpha", self.output / "zip", as_zip=True
        )[0]
        self.assertEqual(folder_names(folder), zip_names(archive))
        self.assertEqual(
            folder_text(folder, "SKILL.md"), zip_text(archive, "SKILL.md")
        )

    def test_an_archive_records_a_fixed_timestamp_and_script_permissions(self):
        import zipfile

        archive = build_skills(
            self.root / "alpha", self.output, as_zip=True
        )[0]
        with zipfile.ZipFile(archive) as opened:
            entries = {info.filename: info for info in opened.infolist()}
        self.assertEqual((1980, 1, 1, 0, 0, 0), entries["SKILL.md"].date_time)
        self.assertEqual(
            0o755, (entries["scripts/greet.py"].external_attr >> 16) & 0o777
        )
        self.assertEqual(0o644, (entries["SKILL.md"].external_attr >> 16) & 0o777)


class AtomicityTests(unittest.TestCase):
    """A failure leaves an existing artifact exactly as it was."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def test_a_check_failure_leaves_the_previous_bundle_untouched(self):
        first = build_skills(self.root, self.output)[0]
        before = folder_text(first, "SKILL.md")
        with edit_workflow(self.root, "alpha", "run") as data:
            data["entry"] = "absent"
        with self.assertRaises(DegardisError):
            build_skills(self.root, self.output)
        self.assertEqual(before, folder_text(first, "SKILL.md"))

    def test_a_write_failure_leaves_the_previous_bundle_untouched(self):
        first = build_skills(self.root / "alpha", self.output)[0]
        before = folder_text(first, "SKILL.md")
        compiler = SkillCompiler(self.root / "alpha")
        with mock.patch(
            "degardis.build.write_bundle", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                compiler.build(self.output)
        self.assertEqual(before, folder_text(first, "SKILL.md"))

    def test_a_completed_sibling_still_commits(self):
        """Staging happens outside the output directory, so a skill that
        finished is not rolled back because a later one failed."""
        compiler = SkillCompiler(self.root)
        original = compiler._commit
        calls: list[str] = []

        def commit(inspection, output, as_zip):
            calls.append(inspection.skill.name)
            if len(calls) > 1:
                raise OSError("disk full")
            return original(inspection, output, as_zip)

        with mock.patch.object(compiler, "_commit", commit):
            with self.assertRaises(OSError):
                compiler.build(self.output)
        self.assertEqual(["alpha", "beta"], calls)
        self.assertTrue((self.output / "alpha" / "SKILL.md").is_file())
        self.assertFalse((self.output / "beta").exists())

    def test_nothing_is_written_when_a_warning_is_promoted(self):
        with edit_yaml(self.root / "alpha" / "rules" / "name-the-gap.yaml") as data:
            data["match"] = {"outcomes": ["never-returned"]}
        with self.assertRaises(DegardisError):
            build_skills(self.root, self.output, fail_on_warning=True)
        self.assertFalse(self.output.exists())


class IconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.output = self.workspace / "out"

    def test_a_declared_icon_is_rasterized_into_the_bundle(self):
        write_raster_icon(
            self.root / "alpha" / "assets" / "icon.png", (90, 75, 138, 255)
        )
        set_interface_fields(self.root, "alpha", icon="assets/icon.png")
        artifact = build_skills(self.root / "alpha", self.output)[0]
        names = folder_names(artifact)
        for relative in ICON_OUTPUTS.values():
            with self.subTest(relative=relative):
                self.assertIn(relative, names)
        metadata = folder_text(artifact, "agents/openai.yaml")
        self.assertIn("icon_small", metadata)
        self.assertIn("icon_large", metadata)

    def test_the_outputs_report_gives_each_icon_the_size_a_build_writes(self):
        write_raster_icon(
            self.root / "alpha" / "assets" / "icon.png", (90, 75, 138, 255)
        )
        set_interface_fields(self.root, "alpha", icon="assets/icon.png")
        skill = self.root / "alpha"
        reported = {
            row["path"]: row["bytes"] for row in inspect_one(skill)["outputs"]
        }
        artifact = build_skills(skill, self.output)[0]
        for relative in ICON_OUTPUTS.values():
            with self.subTest(relative=relative):
                self.assertEqual(
                    (artifact / relative).stat().st_size, reported[relative]
                )

    def test_an_icon_path_the_bundle_cannot_carry_is_reported(self):
        for index, value in enumerate(("", "   ", "/etc/icon.png", "C:/icon.png")):
            with self.subTest(icon=value):
                root = copy_skills(self.workspace / f"case{index}")
                set_interface_fields(root, "alpha", icon=value)
                self.assertIn("icon.invalid-path", codes(root / "alpha"))

    def test_an_svg_icon_carrying_a_script_is_refused(self):
        """The icon is untrusted input the compiler rasterizes, so the screen
        is a trust boundary rather than a formatting preference."""
        icon = self.root / "alpha" / "assets" / "unsafe.svg"
        icon.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            "<script>alert(1)</script></svg>",
            encoding="utf-8",
        )
        set_interface_fields(self.root, "alpha", icon="assets/unsafe.svg")
        self.assertIn("icon.unsafe", codes(self.root / "alpha"))

    def test_an_svg_icon_reaching_outside_itself_is_refused(self):
        icon = self.root / "alpha" / "assets" / "external.svg"
        icon.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            '<image href="https://example.com/logo.png"/></svg>',
            encoding="utf-8",
        )
        set_interface_fields(self.root, "alpha", icon="assets/external.svg")
        self.assertIn("icon.unsafe", codes(self.root / "alpha"))

    def test_an_icon_that_is_not_an_image_is_refused(self):
        icon = self.root / "alpha" / "assets" / "broken.png"
        icon.write_bytes(b"this is not a PNG")
        set_interface_fields(self.root, "alpha", icon="assets/broken.png")
        self.assertIn("icon.unsupported", codes(self.root / "alpha"))

    def test_a_missing_icon_is_reported_rather_than_built_around(self):
        set_interface_fields(self.root, "alpha", icon="assets/absent.png")
        with self.assertRaises(DegardisError) as raised:
            build_skills(self.root / "alpha", self.output)
        self.assertIn("icon.not-found", str(raised.exception) + raised.exception.code)


class InterfaceMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)

    def test_the_prompt_placeholder_renders_in_the_target_invocation_syntax(self):
        artifact = build_skills(self.root / "alpha", self.workspace / "out")[0]
        metadata = folder_text(artifact, "agents/openai.yaml")
        self.assertIn("$alpha", metadata)
        self.assertNotIn("{name}", metadata)


class BundleLayoutTests(unittest.TestCase):
    """What a build would write, checked before anything is written.

    Each guard here decides the file layout of the bundle, and a bundle is
    written once and read many times, so a silent collision or a link to a file
    the bundle does not ship costs every later reader.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.skill = self.root / "alpha"

    def test_a_copied_file_occupying_a_generated_page_is_reported(self):
        """A generated page and a copied reference can want one path.

        The generated page for pattern `inspect-plan-act` is
        `references/patterns/inspect-plan-act.md`. A selected reference file
        at that same path would be copied over it, so the collision is
        reported rather than resolved by whichever write happens last.
        """
        clash = (
            self.skill / "references" / "patterns" / "inspect-plan-act.md"
        )
        clash.write_text("## Notes\n\nSomething.\n", encoding="utf-8")
        self.assertIn("output.path-collision", codes(self.skill))

    def test_a_profile_named_index_gets_a_distinct_page(self):
        profile = self.skill / "profiles" / "index.yaml"
        profile.write_text(
            "title: Index\npoints:\n- Keep this separate.\n", encoding="utf-8"
        )
        artifact = build_skills(self.skill, self.workspace / "out")[0]
        names = folder_names(artifact)
        self.assertIn("profiles/index.md", names)
        self.assertIn("profiles/index-profile.md", names)
        index = folder_text(artifact, "profiles/index.md")
        self.assertIn("[Index](index-profile.md)", index)

    def test_profiles_with_the_same_stem_in_subfolders_keep_distinct_pages(self):
        set_content_patterns(
            self.root, "alpha", profiles=["profiles/*.yaml", "profiles/brief/*.yaml"]
        )
        profile = self.skill / "profiles" / "brief" / "quick.yaml"
        profile.parent.mkdir()
        profile.write_text(
            "title: Brief quick\npoints:\n- Keep this separate.\n",
            encoding="utf-8",
        )
        artifact = build_skills(self.skill, self.workspace / "out")[0]
        names = folder_names(artifact)
        self.assertIn("profiles/quick.md", names)
        self.assertIn("profiles/brief/quick.md", names)
        index = folder_text(artifact, "profiles/index.md")
        self.assertIn("[Brief quick](brief/quick.md)", index)

    def test_profile_titles_are_unique_without_regard_to_case(self):
        profile = self.skill / "profiles" / "another.yaml"
        profile.write_text(
            "title: quick\npoints:\n- Keep this separate.\n", encoding="utf-8"
        )
        self.assertIn("profile.duplicate-title", codes(self.skill))

    def test_a_construct_reference_the_bundle_does_not_ship_is_reported(self):
        with edit_yaml(self.skill / "patterns" / "inspect-plan-act.yaml") as data:
            data["references"] = ["references/patterns/absent.md"]
        self.assertIn("output.broken-reference", codes(self.skill))

    def test_a_shipped_reference_nothing_links_warns(self):
        stray = self.skill / "references" / "patterns" / "stray-notes.md"
        stray.write_text("## Stray\n\nNothing points here.\n", encoding="utf-8")
        self.assertIn("output.unlinked-reference", codes(self.skill, "warning"))


if __name__ == "__main__":
    unittest.main()
