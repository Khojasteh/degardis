"""What a build writes, and what it leaves alone when it cannot finish."""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from degardis.build import SkillCompiler, build_skills
from degardis.icons import ICON_ROLES, MAX_SOURCE_BYTES
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
        self.assertIn("references/facets/index.md", names)

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
        asset.write_bytes(asset.read_bytes() + b"\n[[guide:checklist]]\n")
        script = self.root / "alpha" / "scripts" / "note.md"
        script.write_bytes(b"[[guide:checklist]]\n")
        with edit_yaml(self.root / "alpha" / "skill.yaml") as manifest:
            manifest["content"]["scripts"].append("scripts/*.md")
        artifact = self.build()[0]
        self.assertEqual(asset.read_bytes(), (artifact / "assets" / "template.md").read_bytes())
        self.assertEqual(script.read_bytes(), (artifact / "scripts" / "note.md").read_bytes())

    def test_a_guide_reference_resolves_inline_references(self):
        source = self.root / "alpha" / "guides" / "checklist.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nThen work through [[guide:toolchain]].\n",
            encoding="utf-8",
        )
        artifact = self.build()[0]
        page = folder_text(artifact, "references/guides/checklist.md")
        self.assertIn("Then work through `guide:toolchain`.", page)
        self.assertIn("- [Toolchain checks](toolchain.md)", page)

    def test_a_markdown_extension_guide_resolves_inline_references(self):
        source = self.root / "alpha" / "guides" / "checklist.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nThen work through [[guide:toolchain]].\n",
            encoding="utf-8",
        )
        markdown_source = source.with_suffix(".markdown")
        source.rename(markdown_source)
        with edit_yaml(self.root / "alpha" / "skill.yaml") as manifest:
            manifest["content"]["guides"] = ["guides/*.md", "guides/*.markdown"]
        artifact = self.build()[0]
        page = folder_text(artifact, "references/guides/checklist.md")
        self.assertIn("Then work through `guide:toolchain`.", page)
        self.assertIn("- [Toolchain checks](toolchain.md)", page)

    def test_a_rebuild_over_an_existing_bundle_is_byte_identical(self):
        """Replacing a bundle in place must produce what a first build did.

        The conformance case builds each copy into its own directory; this one
        writes over the previous bundle, which is what an installed skill being
        rebuilt actually does, and reads every file rather than only the root.
        """
        artifact = self.build()[0]
        first = {name: (artifact / name).read_bytes() for name in folder_names(artifact)}
        again = self.build()[0]
        second = {name: (again / name).read_bytes() for name in folder_names(again)}
        self.assertEqual(sorted(first), sorted(second))
        for name in sorted(first):
            with self.subTest(name=name):
                self.assertEqual(first[name], second[name])

    def test_a_bundle_is_named_by_its_manifest_not_its_source_directory(self):
        (self.root / "alpha").rename(self.root / "alpha-source")
        paths = build_skills(self.root / "alpha-source", self.output)
        self.assertEqual([self.output / "alpha"], paths)

    def test_a_rebuild_replaces_the_previous_bundle(self):
        artifact = self.build()[0]
        stale = artifact / "references" / "tasks" / "stale.md"
        write_text(stale, "# Stale\n")
        self.build()
        self.assertFalse(stale.exists())


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

    def test_archive_entries_follow_bundle_paths_on_every_host(self):
        """Entry order is part of the archive's bytes, so it comes from the
        bundle's own POSIX paths, not from how this host compares paths: a
        Windows path sorts `SKILL.md` after `agents/`, a POSIX path before."""
        archive = build_skills(self.root / "alpha", self.output, as_zip=True)[0]
        with zipfile.ZipFile(archive) as opened:
            names = opened.namelist()
        self.assertEqual(sorted(names), names)

    def test_archive_bytes_depend_on_no_host_library_or_platform(self):
        """Deflated bytes are whatever the interpreter's zlib produces, and the
        creator code defaults to the building host's, which on Windows is one
        under which readers ignore the recorded permission bits. So entries are
        stored, and every one records the Unix creator code."""
        archive = build_skills(self.root / "alpha", self.output, as_zip=True)[0]
        with zipfile.ZipFile(archive) as opened:
            entries = opened.infolist()
        self.assertNotEqual([], entries)
        for info in entries:
            with self.subTest(entry=info.filename):
                self.assertEqual(zipfile.ZIP_STORED, info.compress_type)
                self.assertEqual(3, info.create_system)

    @unittest.skipUnless(os.name == "posix", "permission bits are POSIX-only")
    def test_a_folder_records_the_permissions_an_archive_records(self):
        """Both forms carry one permission rule, whatever the source file has."""
        (self.root / "alpha" / "scripts" / "greet.py").chmod(0o600)
        folder = build_skills(self.root / "alpha", self.output)[0]
        for relative, mode in (("scripts/greet.py", 0o755), ("SKILL.md", 0o644)):
            with self.subTest(path=relative):
                self.assertEqual(mode, (folder / relative).stat().st_mode & 0o777)


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

    def test_a_failed_or_interrupted_commit_restores_the_previous_bundle(self):
        """The previous artifact moves only by rename, and anything that stops
        the commit before the new one is in place, Ctrl-C included, moves it back
        and leaves nothing else in the output directory."""
        first = build_skills(self.root / "alpha", self.output)[0]
        before = folder_text(first, "SKILL.md")
        real = os.replace
        steps = {
            "moving aside": lambda source, target: Path(source) == first,
            "moving into place": lambda source, target: Path(target) == first,
        }
        for failure in (OSError("in use"), KeyboardInterrupt()):
            for step, matches in steps.items():
                with self.subTest(failure=type(failure).__name__, step=step):
                    raised: list[bool] = []

                    def replace(
                        source, target, matches=matches, failure=failure, raised=raised
                    ):
                        if not raised and matches(source, target):
                            raised.append(True)
                            raise failure
                        return real(source, target)

                    with mock.patch("degardis.package.os.replace", replace):
                        with self.assertRaises(type(failure)):
                            build_skills(self.root / "alpha", self.output)
                    self.assertEqual(before, folder_text(first, "SKILL.md"))
                    self.assertEqual(["alpha"], [p.name for p in self.output.iterdir()])

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

    def test_a_declared_icon_ships_unchanged_at_its_source_path(self):
        """The icon is copied like any selected file: the author's bytes, at
        the path and in the letter case the source has, and the host metadata
        names that one file for both icon roles."""
        for index, (relative, format_name) in enumerate(
            (
                ("assets/logo.png", "PNG"),
                ("assets/logo.jpg", "JPEG"),
                ("assets/logo.jpeg", "JPEG"),
                ("assets/logo.webp", "WEBP"),
                ("assets/LOGO.PNG", "PNG"),
                ("images/brand.png", "PNG"),
            )
        ):
            with self.subTest(relative=relative):
                root = copy_skills(self.workspace / f"icon{index}")
                source = root / "alpha" / relative
                write_raster_icon(source, (90, 75, 138, 255), format_name=format_name)
                set_interface_fields(root, "alpha", icon=relative)
                artifact = build_skills(root / "alpha", self.workspace / f"out{index}")[0]
                self.assertEqual(source.read_bytes(), (artifact / relative).read_bytes())
                metadata = folder_text(artifact, "agents/openai.yaml").splitlines()
                for role in ICON_ROLES:
                    self.assertIn(f"  icon_{role}: ./{relative}", metadata)

    def test_an_svg_icon_ships_as_the_text_the_author_wrote(self):
        """Nothing is rendered, reformatted, or normalized: even the line
        endings reach the bundle as written."""
        markup = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\r\n'
            b'  <rect width="64" height="64" fill="#123456"/>\r\n'
            b"</svg>\r\n"
        )
        source = self.root / "alpha" / "assets" / "logo.svg"
        source.write_bytes(markup)
        set_interface_fields(self.root, "alpha", icon="assets/logo.svg")
        artifact = build_skills(self.root / "alpha", self.output)[0]
        self.assertEqual(markup, (artifact / "assets" / "logo.svg").read_bytes())

    def test_an_icon_also_selected_as_an_asset_is_one_file_written_once(self):
        """Both name the same source file at the same path, so a build writes
        it once, the outputs report lists it once, and nothing collides."""
        source = self.root / "alpha" / "assets" / "logo.png"
        write_raster_icon(source, (90, 75, 138, 255))
        set_interface_fields(self.root, "alpha", icon="assets/logo.png")
        with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
            data["content"]["assets"] = ["assets/*.md", "assets/logo.png"]
        skill = self.root / "alpha"
        self.assertEqual(set(), codes(skill))
        listed = [row["path"] for row in inspect_one(skill)["outputs"]]
        self.assertEqual(1, listed.count("assets/logo.png"))
        artifact = build_skills(skill, self.output)[0]
        self.assertEqual(source.read_bytes(), (artifact / "assets" / "logo.png").read_bytes())
        metadata = folder_text(artifact, "agents/openai.yaml")
        self.assertIn("icon_small: ./assets/logo.png", metadata)

    def test_the_outputs_report_gives_the_icon_the_size_a_build_writes(self):
        write_raster_icon(
            self.root / "alpha" / "assets" / "icon.png", (90, 75, 138, 255)
        )
        set_interface_fields(self.root, "alpha", icon="assets/icon.png")
        skill = self.root / "alpha"
        reported = {
            row["path"]: row["bytes"] for row in inspect_one(skill)["outputs"]
        }
        artifact = build_skills(skill, self.output)[0]
        self.assertEqual(
            (artifact / "assets" / "icon.png").stat().st_size,
            reported["assets/icon.png"],
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

    def test_an_icon_in_a_format_no_host_displays_is_refused(self):
        """The accepted formats are a closed set, read from the suffix: a
        valid image under any other suffix is refused rather than converted."""
        for index, (name, format_name) in enumerate(
            (
                ("logo.ico", "ICO"),
                ("logo.gif", "GIF"),
                ("logo.bmp", "BMP"),
                ("logo.tiff", "TIFF"),
                ("logo", "PNG"),
            )
        ):
            with self.subTest(name=name):
                root = copy_skills(self.workspace / f"format{index}")
                write_raster_icon(
                    root / "alpha" / "assets" / name, (1, 2, 3, 255), format_name=format_name
                )
                set_interface_fields(root, "alpha", icon=f"assets/{name}")
                self.assertIn("icon.unsupported", codes(root / "alpha"))

    def test_a_raster_icon_that_is_not_the_image_its_suffix_states_is_refused(self):
        """The host reads the format from the suffix, so PNG bytes under a
        .jpg name are a file it cannot display."""
        source = self.root / "alpha" / "assets" / "logo.jpg"
        write_raster_icon(source, (1, 2, 3, 255), format_name="PNG")
        set_interface_fields(self.root, "alpha", icon="assets/logo.jpg")
        self.assertIn("icon.unsupported", codes(self.root / "alpha"))

    def test_an_svg_file_that_is_not_an_svg_document_is_refused(self):
        for index, (case, content) in enumerate(
            (
                ("unparsable markup", b"<svg xmlns='http://www.w3.org/2000/svg'"),
                ("another document", b'<html xmlns="http://www.w3.org/1999/xhtml"/>'),
                ("not text", b"\xff\xfe<svg/>"),
            )
        ):
            with self.subTest(case=case):
                root = copy_skills(self.workspace / f"svg{index}")
                (root / "alpha" / "assets" / "logo.svg").write_bytes(content)
                set_interface_fields(root, "alpha", icon="assets/logo.svg")
                self.assertIn("icon.unsupported", codes(root / "alpha"))

    def test_an_svg_icon_carrying_a_script_is_refused(self):
        """The icon ships as it is to a host that displays it, so the screen
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

    def test_an_svg_icon_carrying_an_event_handler_is_refused(self):
        """An `on...` attribute is script written where an element is not."""
        icon = self.root / "alpha" / "assets" / "handler.svg"
        icon.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
            'onload="alert(1)"/>',
            encoding="utf-8",
        )
        set_interface_fields(self.root, "alpha", icon="assets/handler.svg")
        self.assertIn("icon.unsafe", codes(self.root / "alpha"))

    def test_an_svg_icon_importing_a_stylesheet_is_refused(self):
        """`@import` reaches outside the file whether or not it spells `url()`."""
        for index, rule in enumerate(
            (
                '@import "https://example.test/x.css";',
                "@import 'x.css';",
                "@import url(https://example.test/x.css);",
            )
        ):
            with self.subTest(rule=rule):
                root = copy_skills(self.workspace / f"import{index}")
                (root / "alpha" / "assets" / "styled.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                    f"<style>{rule}</style></svg>",
                    encoding="utf-8",
                )
                set_interface_fields(root, "alpha", icon="assets/styled.svg")
                self.assertIn("icon.unsafe", codes(root / "alpha"))

    def test_an_svg_icon_with_inline_style_and_a_fragment_reference_ships(self):
        """The control for the screen above: self-contained styling passes."""
        (self.root / "alpha" / "assets" / "styled.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            "<style>.a { fill: url(#g); }</style>"
            '<rect class="a" width="16" height="16" style="opacity: 0.5"/></svg>',
            encoding="utf-8",
        )
        set_interface_fields(self.root, "alpha", icon="assets/styled.svg")
        self.assertEqual(set(), codes(self.root / "alpha"))

    def test_an_icon_that_is_not_an_image_is_refused(self):
        icon = self.root / "alpha" / "assets" / "broken.png"
        icon.write_bytes(b"this is not a PNG")
        set_interface_fields(self.root, "alpha", icon="assets/broken.png")
        self.assertIn("icon.unsupported", codes(self.root / "alpha"))

    def test_an_icon_source_too_large_to_ship_is_refused_before_it_is_read(self):
        """The size is checked before the file is read, so a file that would
        cost gigabytes to inspect never reaches the decoder."""
        icon = self.root / "alpha" / "assets" / "huge.png"
        icon.write_bytes(b"\0" * (MAX_SOURCE_BYTES + 1))
        set_interface_fields(self.root, "alpha", icon="assets/huge.png")
        self.assertIn("icon.too-large", codes(self.root / "alpha"))

    def test_a_missing_icon_is_reported_rather_than_built_around(self):
        set_interface_fields(self.root, "alpha", icon="assets/absent.png")
        with self.assertRaises(DegardisError) as raised:
            build_skills(self.root / "alpha", self.output)
        self.assertEqual("icon.not-found", raised.exception.code)

    def test_an_icon_outside_the_skill_directory_is_refused(self):
        """A build reads only the source, so the same source builds the same bundle everywhere."""
        write_raster_icon(self.workspace / "elsewhere" / "icon.png", (1, 2, 3, 255))
        set_interface_fields(self.root, "alpha", icon="../../elsewhere/icon.png")
        self.assertIn("icon.invalid-path", codes(self.root / "alpha"))

    def test_an_image_too_large_to_decode_safely_is_refused_rather_than_raised(self):
        """Pillow refuses a decompression bomb with an error of its own."""
        from PIL import Image

        write_raster_icon(self.root / "alpha" / "assets" / "icon.png", (1, 2, 3, 255))
        set_interface_fields(self.root, "alpha", icon="assets/icon.png")
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            self.assertIn("icon.too-large", codes(self.root / "alpha"))

    def test_editing_the_icon_changes_the_source_fingerprint(self):
        """The icon reaches the bundle without being selected under content."""
        icon = self.root / "alpha" / "assets" / "icon.png"
        write_raster_icon(icon, (90, 75, 138, 255))
        set_interface_fields(self.root, "alpha", icon="assets/icon.png")
        before = inspect_one(self.root / "alpha")["source_fingerprint"]
        write_raster_icon(icon, (10, 20, 30, 255))
        after = inspect_one(self.root / "alpha")["source_fingerprint"]
        self.assertNotEqual(before["digest"], after["digest"])


class CopiedFileTests(unittest.TestCase):
    """Scripts and assets keep the paths the manifest selects them from."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.skill = self.root / "alpha"

    def select(self, **patterns: list[str]) -> None:
        with edit_yaml(self.skill / "skill.yaml") as data:
            data["content"].update(patterns)

    def link_from_review(self, text: str) -> None:
        source = task_path(self.root, "alpha", "review")
        source.write_text(source.read_text(encoding="utf-8") + f"\n{text}\n", encoding="utf-8")

    def modes(self, archive: Path) -> dict[str, int]:
        with zipfile.ZipFile(archive) as opened:
            return {
                info.filename: (info.external_attr >> 16) & 0o777
                for info in opened.infolist()
            }

    def test_a_script_selected_from_anywhere_resolves_and_counts_as_used(self):
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/*.py", "tools/*.py"])
        self.link_from_review("Run [[script:check.py]] first.")
        self.assertEqual(set(), codes(self.skill))
        self.assertNotIn("content.unconsumed", codes(self.skill, "warning"))
        page = inspect_one(self.skill, body_pages=["references/tasks/review.md"])
        self.assertIn(
            "`tools/check.py`",
            page["page_text"]["references/tasks/review.md"],
        )

    def test_a_target_may_name_any_trailing_run_of_whole_path_segments(self):
        write_text(self.skill / "scripts" / "lint" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/**/*.py"])
        for target in ("check.py", "lint/check.py", "scripts/lint/check.py"):
            with self.subTest(target=target):
                source = task_path(self.root, "alpha", "review")
                original = source.read_text(encoding="utf-8")
                self.link_from_review(f"Run [[script:{target}]].")
                self.assertEqual(set(), codes(self.skill))
                source.write_text(original, encoding="utf-8")
        self.link_from_review("Run [[script:eck.py]].")
        self.assertIn("inline.unknown-target", codes(self.skill))

    def test_a_target_naming_two_selected_files_asks_for_more_of_the_path(self):
        write_text(self.skill / "scripts" / "check.py", "print('check')\n")
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/*.py", "tools/*.py"])
        self.link_from_review("Run [[script:check.py]].")
        records = [
            record
            for record in inspect_one(self.skill)["diagnostics"]
            if record.code == "inline.ambiguous-target"
        ]
        self.assertEqual([task_path(self.root, "alpha", "review")], [r.path for r in records])
        self.assertIn("scripts/check.py", records[0].message)
        self.assertIn("tools/check.py", records[0].message)

    def test_a_more_specific_target_settles_an_ambiguous_one(self):
        write_text(self.skill / "scripts" / "check.py", "print('check')\n")
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/*.py", "tools/*.py"])
        self.link_from_review("Run [[script:tools/check.py]] and [[script:scripts/check.py]].")
        self.assertEqual(set(), codes(self.skill))

    def test_a_full_path_is_never_ambiguous(self):
        """Exact is the most specific address there is, so it cannot be refined."""
        write_text(self.skill / "scripts" / "check.py", "print('check')\n")
        write_text(self.skill / "lib" / "scripts" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/*.py", "lib/scripts/*.py"])
        self.link_from_review(
            "Run [[script:scripts/check.py]] and [[script:lib/scripts/check.py]]."
        )
        self.assertEqual(set(), codes(self.skill))

    def test_selection_rather_than_location_makes_a_file_executable(self):
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        write_text(self.skill / "scripts" / "data.json", "{}\n")
        self.select(
            scripts=["scripts/*.py", "tools/*.py"], assets=["assets/*.md", "scripts/*.json"]
        )
        self.link_from_review("Run [[script:check.py]] with [[asset:data.json]].")
        archive = build_skills(self.skill, self.workspace / "out", as_zip=True)[0]
        modes = self.modes(archive)
        self.assertEqual(0o755, modes["tools/check.py"])
        self.assertEqual(0o755, modes["scripts/greet.py"])
        self.assertEqual(0o644, modes["scripts/data.json"])
        reported = {row["path"]: row["mode"] for row in inspect_one(self.skill)["outputs"]}
        self.assertEqual("755", reported["tools/check.py"])
        self.assertEqual("644", reported["scripts/data.json"])

    @unittest.skipUnless(os.name == "posix", "permission bits are POSIX-only")
    def test_a_folder_gives_a_script_outside_scripts_its_executable_bit(self):
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        self.select(scripts=["scripts/*.py", "tools/*.py"])
        self.link_from_review("Run [[script:check.py]].")
        folder = build_skills(self.skill, self.workspace / "out")[0]
        self.assertEqual(0o755, (folder / "tools" / "check.py").stat().st_mode & 0o777)

    def test_the_inspect_id_is_the_shortest_target_naming_the_file_alone(self):
        write_text(self.skill / "scripts" / "check.py", "print('check')\n")
        write_text(self.skill / "tools" / "check.py", "print('check')\n")
        write_text(self.skill / "tools" / "lint.py", "print('lint')\n")
        self.select(scripts=["scripts/*.py", "tools/*.py"])
        ids = {row["path"]: row["id"] for row in inspect_one(self.skill)["scripts"]}
        self.assertEqual(
            {
                "scripts/check.py": "scripts/check.py",
                "scripts/greet.py": "greet.py",
                "tools/check.py": "tools/check.py",
                "tools/lint.py": "lint.py",
            },
            ids,
        )

    def test_a_directory_differing_only_in_case_from_a_generated_one_is_refused(self):
        """A case-insensitive file system writes both into one directory, so the
        bundle a build writes would depend on the host that wrote it."""
        write_text(self.skill / "References" / "notes.txt", "notes\n")
        self.select(assets=["assets/*.md", "References/*.txt"])
        self.link_from_review("Read [[asset:notes.txt]].")
        self.assertIn("output.path-collision", codes(self.skill))

    def test_a_file_where_a_generated_directory_goes_is_refused(self):
        """No file system holds a file and a directory at one path, so the
        build could not write the bundle the validation passed."""
        write_text(self.skill / "agents", "not a directory\n")
        self.select(assets=["assets/*.md", "agents"])
        self.link_from_review("Read [[asset:agents]].")
        self.assertIn("output.path-collision", codes(self.skill))

    def test_the_icon_selected_as_an_asset_needs_no_inline_reference(self):
        """The host metadata names the icon, so it is not weight nothing uses."""
        write_text(
            self.skill / "assets" / "icon.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/>',
        )
        self.select(assets=["assets/*.md", "assets/*.svg"])

        def unconsumed() -> list[str]:
            return [
                record.path.name
                for record in inspect_one(self.skill)["diagnostics"]
                if record.code == "content.unconsumed" and record.path is not None
            ]

        self.assertIn("icon.svg", unconsumed())
        set_interface_fields(self.root, "alpha", icon="assets/icon.svg")
        self.assertNotIn("icon.svg", unconsumed())


class InterfaceMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)

    def test_the_prompt_renders_in_openai_invocation_syntax(self):
        set_interface_fields(
            self.root,
            "alpha",
            default_prompt="Use alpha exactly as authored.",
        )
        artifact = build_skills(self.root / "alpha", self.workspace / "out")[0]
        metadata = folder_text(artifact, "agents/openai.yaml")
        self.assertIn("default_prompt: Use $alpha exactly as authored.", metadata)
        self.assertNotIn("default_prompt: Use alpha exactly as authored.", metadata)


if __name__ == "__main__":
    unittest.main()
