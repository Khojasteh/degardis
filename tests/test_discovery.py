"""Finding skill sources on disk."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.model import DegardisError
from degardis.registry import discover_skill_paths

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

    def test_explicit_and_collection_inputs_are_deduplicated(self):
        paths = discover_skill_paths([FIXTURES, FIXTURES / "alpha"])
        self.assertEqual(["alpha", "beta", "gamma"], [path.name for path in paths])

    def test_directory_must_match_manifest_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["name"] = "wrong"
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(DegardisError, "does not match"):
                discover_skill_paths([root / "alpha"])
