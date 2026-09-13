"""What a build writes, and what it leaves alone when it cannot finish."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis import wording
from degardis.build import SkillCompiler, build_skills
from degardis.icons import ICON_OUTPUTS, MAX_SOURCE_BYTES
from degardis.model import DegardisError

from tests.support import (
    codes,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    folder_names,
    folder_text,
    inspect_one,
    set_interface_fields,
    task_path,
    write_raster_icon,
    write_source,
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
        self.assertIn("references/guides/checklist.md", names)
        self.assertIn("references/tasks/review.md", names)
        self.assertIn("references/profiles/index.md", names)

    def test_no_machine_model_is_emitted_beside_the_document(self):
        """The document is the artifact: no plan, closure, or source-map file
        is written beside it for something other than a reader to consume."""
        names = folder_names(self.build()[0])
        self.assertEqual([], [name for name in names if name.endswith(".json")])
        self.assertEqual(
            [],
            [
                name
                for name in names
                if name.startswith("knowledge/")
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

    def test_markdown_assets_and_scripts_keep_their_bytes(self):
        asset = self.root / "alpha" / "assets" / "template.md"
        asset.write_bytes(asset.read_bytes() + b"\n[[task:repair]]\n")
        script = self.root / "alpha" / "scripts" / "note.md"
        script.write_bytes(b"[[task:repair]]\n")
        with edit_yaml(self.root / "alpha" / "skill.yaml") as manifest:
            manifest["content"]["scripts"].append("scripts/*.md")
        artifact = self.build()[0]
        self.assertEqual(asset.read_bytes(), (artifact / "assets" / "template.md").read_bytes())
        self.assertEqual(script.read_bytes(), (artifact / "scripts" / "note.md").read_bytes())

    def test_a_guide_reference_resolves_inline_references(self):
        source = self.root / "alpha" / "guides" / "checklist.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nContinue with [[task:repair]].\n",
            encoding="utf-8",
        )
        artifact = self.build()[0]
        self.assertIn(
            "Continue with [Repair wrong behavior](../tasks/repair.md).",
            folder_text(artifact, "references/guides/checklist.md"),
        )

    def test_a_markdown_extension_guide_resolves_inline_references(self):
        source = self.root / "alpha" / "guides" / "checklist.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nContinue with [[task:repair]].\n",
            encoding="utf-8",
        )
        markdown_source = source.with_suffix(".markdown")
        source.rename(markdown_source)
        with edit_yaml(self.root / "alpha" / "skill.yaml") as manifest:
            manifest["content"]["guides"] = ["guides/*.markdown"]
        artifact = self.build()[0]
        self.assertIn(
            "Continue with [Repair wrong behavior](../tasks/repair.md).",
            folder_text(artifact, "references/guides/checklist.md"),
        )

    def test_a_rebuild_is_byte_identical(self):
        first = (self.build()[0] / "SKILL.md").read_bytes()
        second = (self.build()[0] / "SKILL.md").read_bytes()
        self.assertEqual(first, second)

    def test_a_rebuild_replaces_the_previous_bundle(self):
        artifact = self.build()[0]
        stale = artifact / "references" / "tasks" / "stale.md"
        write_text(stale, "# Stale\n")
        self.build()
        self.assertFalse(stale.exists())

    def test_a_task_page_stands_without_any_profile(self):
        """Profiles are auxiliary: removing the whole tree leaves the root and
        every task page readable and complete."""
        artifact = self.build()[0]
        shutil.rmtree(artifact / "references" / "profiles")
        text = folder_text(artifact, "references/tasks/review.md")
        self.assertIn(f"## {wording.GOAL_HEADING}", text)
        self.assertIn(f"## {wording.KNOWLEDGE_HEADING}", text)


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
        with edit_frontmatter(task_path(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
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
        write_source(
            self.root / "alpha" / "knowledge" / "unused.md",
            "kind: fact\ntitle: Unused",
            "Reached by nothing.",
        )
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

    def test_the_outputs_report_matches_the_files_a_build_writes(self):
        skill = self.root / "alpha"
        reported = {
            row["path"]: row["bytes"]
            for row in inspect_one(skill)["outputs"]
        }
        artifact = build_skills(skill, self.output)[0]
        written = {
            relative: (artifact / relative).stat().st_size
            for relative in folder_names(artifact)
        }

        self.assertEqual(written, reported)

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

    def test_an_icon_source_too_large_to_convert_is_refused_before_it_is_read(self):
        """The size is checked before the image is opened, so a file that would
        cost gigabytes to decode never reaches the decoder."""
        icon = self.root / "alpha" / "assets" / "huge.png"
        icon.write_bytes(b"\0" * (MAX_SOURCE_BYTES + 1))
        set_interface_fields(self.root, "alpha", icon="assets/huge.png")
        self.assertIn("icon.too-large", codes(self.root / "alpha"))

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


if __name__ == "__main__":
    unittest.main()
