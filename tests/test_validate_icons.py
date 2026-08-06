"""Validation of interface icon sources."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.validate import validate

from tests.support import copy_skills, set_interface_icons, write_raster_icon


class IconValidationTests(unittest.TestCase):
    def test_icon_paths_must_be_non_empty_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            absolute = (root / "icon.png").resolve()
            write_raster_icon(absolute, (255, 0, 0, 255))

            for field, value, message in (
                ("icon", "", "must be a non-empty relative path"),
                ("icon_small", str(absolute), "must be relative"),
                ("icon_large", "missing.png", "icon not found"),
            ):
                with self.subTest(field=field):
                    copied = Path(directory) / f"{field}-skill"
                    shutil.copytree(root / "alpha", copied)
                    manifest = copied / "skill.yaml"
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                    data["name"] = copied.name
                    data["interface"]["default_prompt"] = (
                        f"Use ${copied.name} to run the example."
                    )
                    data["interface"][field] = value
                    manifest.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    errors = validate(copied)

                    self.assertTrue(any(message in error for error in errors))

    def test_invalid_and_unsafe_icon_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            invalid = root / "invalid.png"
            invalid.write_text("not an image", encoding="utf-8")
            unsafe = root / "unsafe.svg"
            unsafe.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                encoding="utf-8",
            )

            for source, message in (
                ("../invalid.png", "Cannot convert icon source"),
                ("../unsafe.svg", "script is not allowed"),
            ):
                with self.subTest(source=source):
                    set_interface_icons(root, "alpha", icon=source)
                    errors = validate(root / "alpha")
                    self.assertTrue(any(message in error for error in errors))
