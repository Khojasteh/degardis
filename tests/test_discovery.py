"""Finding the skills a command was pointed at, before any check runs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from degardis.model import DegardisError
from degardis.registry import discover_skill_paths, load_skill_path

from tests.support import FIXTURES, copy_skills, edit_yaml, write_text


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_a_directory_of_skills_is_discovered_in_name_order(self):
        found = discover_skill_paths([FIXTURES])
        self.assertEqual(["alpha", "beta"], [path.name for path in found])

    def test_a_skill_directory_is_discovered_as_itself(self):
        found = discover_skill_paths([FIXTURES / "alpha"])
        self.assertEqual([FIXTURES / "alpha"], found)

    def test_a_repeated_path_is_discovered_once(self):
        found = discover_skill_paths([FIXTURES / "alpha", FIXTURES / "alpha"])
        self.assertEqual(1, len(found))

    def test_a_directory_with_no_skill_is_refused(self):
        with self.assertRaises(DegardisError):
            discover_skill_paths([self.root])

    def test_a_file_is_refused(self):
        path = self.root / "skill.yaml"
        write_text(path, "name: x\n")
        with self.assertRaises(DegardisError):
            discover_skill_paths([path])

    def test_an_archive_is_refused_with_its_code(self):
        path = self.root / "alpha.zip"
        path.write_bytes(b"PK\x03\x04")
        with self.assertRaises(DegardisError) as raised:
            discover_skill_paths([path])
        self.assertEqual("source.archive-input", raised.exception.code)

    def test_a_built_bundle_is_refused_with_its_code(self):
        bundle = self.root / "structured-summary"
        write_text(bundle / "SKILL.md", "# Built\n")
        with self.assertRaises(DegardisError) as raised:
            discover_skill_paths([bundle])
        self.assertEqual("source.generated-bundle", raised.exception.code)

    def test_two_skills_claiming_one_name_are_refused(self):
        """One manifest name is one skill. Two trees claiming it would build
        two bundles into one directory, and the second would replace the first."""
        import shutil

        first = self.root / "one"
        second = self.root / "two"
        first.mkdir()
        second.mkdir()
        source = FIXTURES / "beta"
        shutil.copytree(source, first / "beta")
        shutil.copytree(source, second / "beta")
        with self.assertRaises(DegardisError):
            discover_skill_paths([self.root])

    def test_an_unreadable_manifest_does_not_stop_discovery(self):
        """A command that reports on skills has to reach the broken one to
        report it, so discovery passes it through rather than raising."""
        root = copy_skills(self.root)
        write_text(root / "beta" / "skill.yaml", "name: [beta]\n")
        found = discover_skill_paths([root])
        self.assertEqual(["alpha", "beta"], [path.name for path in found])


class ManifestIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def failure(self, name: str = "alpha") -> DegardisError:
        with self.assertRaises(DegardisError) as raised:
            load_skill_path(self.root / name)
        return raised.exception

    def test_a_manifest_is_loaded_with_its_identity(self):
        skill = load_skill_path(self.root / "alpha")
        self.assertEqual("alpha", skill.name)
        self.assertEqual("Alpha", skill.title)
        self.assertEqual("1.2.3", skill.version)
        self.assertEqual(2, skill.format_version)

    def test_a_missing_manifest_is_refused(self):
        (self.root / "alpha" / "skill.yaml").unlink()
        self.assertEqual("manifest.missing", self.failure().code)

    def test_a_manifest_with_no_name_is_refused(self):
        with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
            del data["name"]
        self.assertEqual("manifest.missing-name", self.failure().code)

    def test_a_name_that_is_not_the_directory_is_refused(self):
        with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
            data["name"] = "other"
        self.assertEqual("manifest.name-mismatch", self.failure().code)

    def test_an_earlier_format_is_refused_rather_than_converted(self):
        with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
            data["format_version"] = 1
        self.assertEqual("manifest.obsolete-format_version", self.failure().code)

    def test_a_later_format_is_refused(self):
        with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
            data["format_version"] = 3
        self.assertEqual("manifest.unsupported-format_version", self.failure().code)

    def test_a_format_that_is_not_an_integer_is_refused(self):
        for value in ("2", 0, -1, True):
            with self.subTest(value=value):
                with edit_yaml(self.root / "alpha" / "skill.yaml") as data:
                    data["format_version"] = value
                self.assertEqual(
                    "manifest.invalid-format_version", self.failure().code
                )


if __name__ == "__main__":
    unittest.main()
