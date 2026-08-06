"""Validation of the content selection and the output paths it implies."""

from __future__ import annotations

import ctypes
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.validate import inspect_skills, validate

from tests.support import (
    copy_skills,
    folder_names,
    folder_text,
    set_content_patterns,
    zip_names,
)


class ContentValidationTests(unittest.TestCase):
    def test_python_bytecode_beside_a_script_is_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            scripts = root / "alpha" / "scripts"
            cache = scripts / "__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "greet.cpython-314.pyc").write_bytes(b"\x00compiled")
            (scripts / "stale.pyc").write_bytes(b"\x00compiled")

            result = inspect_skills([root / "alpha"])[0]

            selected = [item["path"] for item in result["scripts"]]
            self.assertEqual(["scripts/greet.py"], selected)
            written = [item["path"] for item in result["outputs"]]
            self.assertNotIn("scripts/stale.pyc", written)
            self.assertFalse([path for path in written if "__pycache__" in path])

            output = Path(directory) / "artifacts"
            build_skills(root / "alpha", output)
            built = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertIn("alpha/scripts/greet.py", built)
            self.assertFalse([name for name in built if name.endswith(".pyc")])

    def test_unsupported_content_field_is_reported_as_a_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["documents"] = ["documents/*.md"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            result = inspect_skills([source.parent])[0]

        self.assertEqual([], result["errors"])
        self.assertTrue(
            any(
                "unrecognized content fields ignored: documents" in warning
                for warning in result["warnings"]
            )
        )

    def test_content_globs_must_stay_inside_skill_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            outside = root / "outside.yaml"
            outside.write_text(
                "id: alpha.outside\nrule: Outside content\n",
                encoding="utf-8",
            )
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["entries"] = ["../outside.yaml"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(source.parent)

            self.assertTrue(
                any("content patterns must stay within" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "content patterns must stay within"
            ):
                build_skills(source.parent, root / "output")

    def test_generated_reference_filenames_must_be_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entries = root / "alpha" / "entries"
            (entries / "hyphen.yaml").write_text(
                "id: alpha.foo-bar\nrule: Hyphen form\n",
                encoding="utf-8",
            )
            (entries / "dot.yaml").write_text(
                "id: alpha.foo.bar\nrule: Dot form\n",
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(any("output path collision" in error for error in errors))
            with self.assertRaisesRegex(DegardisError, "output path collision"):
                build_skills(root / "alpha", root / "output")


class ContentExclusionTests(unittest.TestCase):
    """Patterns prefixed with ! remove what the patterns before them selected."""

    def _skill_with_drafts(self, directory: Path) -> Path:
        root = copy_skills(directory)
        drafts = root / "alpha" / "assets" / "drafts"
        (drafts / "nested").mkdir(parents=True)
        (drafts / "outline.md").write_text("Outline\n", encoding="utf-8")
        (drafts / "keep.md").write_text("Keep\n", encoding="utf-8")
        (drafts / "nested" / "notes.md").write_text("Notes\n", encoding="utf-8")
        return root

    def _selected_assets(self, skill: Path) -> list[str]:
        result = inspect_skills([skill])[0]
        self.assertEqual([], result["errors"])
        return [item["path"] for item in result["assets"]]

    def test_negated_pattern_excludes_the_files_it_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_drafts(Path(directory))
            set_content_patterns(
                root, "alpha", assets=["assets/**/*", "!assets/drafts/**/*"]
            )

            self.assertEqual(
                ["assets/template.md"], self._selected_assets(root / "alpha")
            )

    def test_negated_directory_excludes_everything_beneath_it(self):
        for exclusion in ("!assets/drafts", "!assets/drafts/**"):
            with self.subTest(exclusion=exclusion):
                with tempfile.TemporaryDirectory() as directory:
                    root = self._skill_with_drafts(Path(directory))
                    set_content_patterns(
                        root, "alpha", assets=["assets/**/*", exclusion]
                    )

                    self.assertEqual(
                        ["assets/template.md"], self._selected_assets(root / "alpha")
                    )

    def test_a_pattern_after_an_exclusion_adds_a_file_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_drafts(Path(directory))
            set_content_patterns(
                root,
                "alpha",
                assets=[
                    "assets/**/*",
                    "!assets/drafts/**/*",
                    "assets/drafts/keep.md",
                ],
            )

            self.assertEqual(
                ["assets/template.md", "assets/drafts/keep.md"],
                self._selected_assets(root / "alpha"),
            )

    def test_excluded_files_reach_neither_the_bundle_nor_the_generated_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_drafts(Path(directory))
            set_content_patterns(
                root, "alpha", assets=["assets/**/*", "!assets/drafts/**/*"]
            )
            output = Path(directory) / "artifacts"
            zipped = Path(directory) / "archives"

            build_skills(root / "alpha", output)
            archive = build_skills(root / "alpha", zipped, as_zip=True)[0]

            built = folder_names(output / "alpha")
            self.assertIn("assets/template.md", built)
            self.assertFalse([name for name in built if "drafts" in name])
            packaged = zip_names(archive)
            self.assertIn("assets/template.md", packaged)
            self.assertFalse([name for name in packaged if "drafts" in name])
            self.assertNotIn("assets/drafts", folder_text(output / "alpha", "SKILL.md"))

    def test_exclusion_patterns_must_stay_inside_the_skill_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            (root / "outside.yaml").write_text(
                "id: alpha.outside\nrule: Outside content\n",
                encoding="utf-8",
            )
            set_content_patterns(root, "alpha", entries=["!../outside.yaml"])

            errors = validate(root / "alpha")

            self.assertTrue(
                any("content patterns must stay within" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "content patterns must stay within"
            ):
                build_skills(root / "alpha", root / "output")

    def test_a_pattern_that_is_only_the_exclusion_marker_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_content_patterns(root, "alpha", assets=["!"])

            errors = validate(root / "alpha")

            self.assertTrue(
                any(
                    "content.assets must be a list of non-empty glob strings" in error
                    for error in errors
                )
            )
            self.assertEqual([], inspect_skills([root / "alpha"])[0]["assets"])


class ContentPatternMatchingTests(unittest.TestCase):
    """Which files a source selects is a property of the source, not the host."""

    def test_pattern_segments_are_matched_case_sensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_content_patterns(root, "alpha", entries=["ENTRIES/*.yaml"])

            result = inspect_skills([root / "alpha"])[0]

            self.assertEqual([], result["entries"])

    def test_a_wrongly_cased_exclusion_removes_nothing_anywhere(self):
        """The destructive half: on a case-folding host this dropped the entry."""
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_content_patterns(
                root, "alpha", entries=["entries/*.yaml", "!ENTRIES/RULE-ONE.yaml"]
            )

            result = inspect_skills([root / "alpha"])[0]

            self.assertEqual(
                ["entries/rule-one.yaml"],
                [item["path"] for item in result["entries"]],
            )

    def test_a_matched_path_keeps_the_case_the_filesystem_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            set_content_patterns(root, "alpha", assets=["assets/template.md"])

            result = inspect_skills([root / "alpha"])[0]

            self.assertEqual(
                ["assets/template.md"], [item["path"] for item in result["assets"]]
            )

    def test_a_double_star_stands_for_any_number_of_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            nested = root / "alpha" / "assets" / "one" / "two"
            nested.mkdir(parents=True)
            (nested / "deep.md").write_text("Deep\n", encoding="utf-8")
            set_content_patterns(root, "alpha", assets=["assets/**/*.md"])

            result = inspect_skills([root / "alpha"])[0]

            self.assertEqual(
                ["assets/one/two/deep.md", "assets/template.md"],
                sorted(item["path"] for item in result["assets"]),
            )


class HiddenContentTests(unittest.TestCase):
    """Files the author cannot see, and files the host wrote, are not content."""

    def _skill_with_hidden_files(self, directory: Path) -> Path:
        root = copy_skills(directory)
        assets = root / "alpha" / "assets"
        (assets / ".vscode").mkdir()
        (assets / "img").mkdir()
        (assets / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        (assets / ".DS_Store").write_bytes(b"\x00finder")
        (assets / "._template.md").write_bytes(b"\x00sidecar")
        (assets / "Thumbs.db").write_bytes(b"\x00thumbs")
        (assets / "img" / "THUMBS.DB").write_bytes(b"\x00thumbs")
        (assets / "img" / "desktop.ini").write_text(
            "[.ShellClassInfo]\n", encoding="utf-8"
        )
        (assets / ".vscode" / "tasks.json").write_text("{}\n", encoding="utf-8")
        environment = root / "alpha" / "scripts" / ".venv" / "lib"
        environment.mkdir(parents=True)
        (environment / "sitecustomize.py").write_text("pass\n", encoding="utf-8")
        return root

    def _selected(self, skill: Path) -> list[str]:
        result = inspect_skills([skill])[0]
        self.assertEqual([], result["errors"])
        return [item["path"] for item in [*result["scripts"], *result["assets"]]]

    def test_a_dot_prefixed_file_is_ordinary_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_hidden_files(Path(directory))
            output = Path(directory) / "artifacts"

            self.assertIn("assets/.gitignore", self._selected(root / "alpha"))

            archive = build_skills(root / "alpha", output, as_zip=True)[0]
            self.assertIn("assets/.gitignore", zip_names(archive))

    def test_hidden_directories_are_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_hidden_files(Path(directory))
            output = Path(directory) / "artifacts"

            selected = self._selected(root / "alpha")
            self.assertNotIn("assets/.vscode/tasks.json", selected)
            self.assertNotIn("scripts/.venv/lib/sitecustomize.py", selected)

            build_skills(root / "alpha", output)
            zipped = Path(directory) / "archives"
            archive = build_skills(root / "alpha", zipped, as_zip=True)[0]
            for names in (folder_names(output / "alpha"), zip_names(archive)):
                self.assertIn("scripts/greet.py", names)
                self.assertFalse([name for name in names if ".vscode" in name])
                self.assertFalse([name for name in names if ".venv" in name])

    def _skill_with_a_marked_file(self, directory: Path) -> Path:
        """A skill whose assets hold one file the filesystem marks hidden."""
        root = copy_skills(directory)
        marked = root / "alpha" / "assets" / "marked.md"
        marked.write_text("Marked\n", encoding="utf-8")
        self.assertTrue(ctypes.windll.kernel32.SetFileAttributesW(str(marked), 0x2))
        return root

    @unittest.skipUnless(
        os.name == "nt", "only Windows exposes a settable hidden attribute here"
    )
    def test_a_file_the_filesystem_marks_hidden_is_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_a_marked_file(Path(directory))

            selected = self._selected(root / "alpha")

            self.assertNotIn("assets/marked.md", selected)
            self.assertIn("assets/template.md", selected)

    @unittest.skipUnless(
        os.name == "nt", "only Windows exposes a settable hidden attribute here"
    )
    def test_a_marked_file_a_pattern_names_without_a_wildcard_is_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_a_marked_file(Path(directory))
            set_content_patterns(
                root, "alpha", assets=["assets/*.md", "assets/marked.md"]
            )

            self.assertIn("assets/marked.md", self._selected(root / "alpha"))

    def test_platform_metadata_files_are_never_content(self):
        metadata = [
            "assets/.DS_Store",
            "assets/._template.md",
            "assets/Thumbs.db",
            "assets/img/THUMBS.DB",
            "assets/img/desktop.ini",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_hidden_files(Path(directory))
            set_content_patterns(root, "alpha", assets=["assets/**/*", *metadata])
            output = Path(directory) / "artifacts"

            selected = self._selected(root / "alpha")
            archive = build_skills(root / "alpha", output, as_zip=True)[0]
            packaged = zip_names(archive)

            for path in metadata:
                self.assertNotIn(path, selected)
                self.assertNotIn(path, packaged)

    def test_a_hidden_directory_named_by_a_pattern_is_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._skill_with_hidden_files(Path(directory))
            set_content_patterns(
                root, "alpha", assets=["assets/**/*", "assets/.vscode/*"]
            )
            output = Path(directory) / "artifacts"

            self.assertIn("assets/.vscode/tasks.json", self._selected(root / "alpha"))

            archive = build_skills(root / "alpha", output, as_zip=True)[0]
            self.assertIn("assets/.vscode/tasks.json", zip_names(archive))

    def test_a_hidden_sidecar_beside_an_entry_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            (root / "alpha" / "entries" / "._rule-one.yaml").write_bytes(
                b"\x00\x01 not yaml at all"
            )

            result = inspect_skills([root / "alpha"])[0]

            self.assertEqual([], result["errors"])
            self.assertEqual(1, result["counts"]["entries"])
