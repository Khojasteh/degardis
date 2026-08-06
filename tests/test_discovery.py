"""Finding skill sources on disk, and refusing what is not a source."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.build import build_skills
from degardis.model import DegardisError
from degardis.registry import discover_skill_paths
from degardis.validate import inspect_skills

from tests.support import FIXTURES, copy_skills


class DiscoveryTests(unittest.TestCase):
    def test_collection_discovers_skill_descendants_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            nested = root / "groups" / "team"
            nested.mkdir(parents=True)
            (root / "beta").rename(nested / "beta")

            paths = discover_skill_paths([root])

            self.assertEqual(
                ["alpha", "gamma", "beta"],
                [path.name for path in paths],
            )

    def test_collection_discovery_stops_at_skill_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            embedded = root / "alpha" / "assets" / "embedded"
            shutil.copytree(root / "beta", embedded)

            paths = discover_skill_paths([root])

            self.assertEqual(
                ["alpha", "beta", "gamma"],
                [path.name for path in paths],
            )

    def test_collection_discovers_immediate_children(self):
        paths = discover_skill_paths([FIXTURES])
        self.assertEqual(["alpha", "beta", "gamma"], [path.name for path in paths])

    def test_a_generated_bundle_is_refused_as_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = Path(directory) / "out"
            build_skills(root / "alpha", output)
            bundle = output / "alpha"
            # The bundle ships alpha's template asset, which carries its own
            # skill.yaml, so descending would report a pass for another skill.
            shutil.copytree(root / "beta", bundle / "assets" / "starter" / "beta")

            for target in (bundle, output):
                with self.subTest(target=target.name):
                    with self.assertRaises(DegardisError) as raised:
                        discover_skill_paths([target])
                    self.assertIn("generated skill bundle", str(raised.exception))

    def test_a_zip_archive_is_refused_as_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = Path(directory) / "out"
            build_skills(root / "alpha", output, as_zip=True)

            with self.assertRaises(DegardisError) as raised:
                discover_skill_paths([output / "alpha.zip"])

        self.assertIn("skill archive", str(raised.exception))

    def test_explicit_and_collection_inputs_are_deduplicated(self):
        paths = discover_skill_paths([FIXTURES, FIXTURES / "alpha"])
        self.assertEqual(["alpha", "beta", "gamma"], [path.name for path in paths])

    def test_directory_must_match_manifest_name(self):
        """Discovery still finds the skill, so the report is what refuses it.

        A manifest that cannot be loaded has nothing discovery can do with it,
        and aborting there would leave the failure outside every report. The
        skill is returned so a reporting command can name it, and the commands
        that go on to load it raise as before.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["name"] = "wrong"
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            self.assertEqual(["alpha"], [
                path.name for path in discover_skill_paths([root / "alpha"])
            ])
            errors = inspect_skills([root / "alpha"])[0]["errors"]
            self.assertTrue(any("does not match" in error for error in errors))
            with self.assertRaisesRegex(DegardisError, "does not match"):
                build_skills(root / "alpha", Path(directory) / "out")
