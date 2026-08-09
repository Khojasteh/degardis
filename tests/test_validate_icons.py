"""Validation of interface icon sources."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from degardis.icons import MAX_SOURCE_BYTES
from degardis.validate import inspect_skills

from tests.support import (
    copy_skills,
    diagnostic_codes,
    set_interface_fields,
    write_raster_icon,
)


class IconValidationTests(unittest.TestCase):
    def test_icon_paths_must_be_non_empty_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            absolute = (root / "icon.png").resolve()
            write_raster_icon(absolute, (255, 0, 0, 255))

            for field, value, expected_code in (
                ("icon", "", "icon.invalid-path"),
                ("icon_small", str(absolute), "icon.invalid-path"),
                ("icon_large", "missing.png", "icon.not-found"),
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

                    result = inspect_skills([copied])[0]

                    self.assertIn(expected_code, diagnostic_codes(result, "error"))

    def test_each_icon_failure_reports_the_check_that_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            (root / "not-an-image.png").write_text("plain text", encoding="utf-8")
            (root / "unsafe.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                encoding="utf-8",
            )
            (root / "oversized.png").write_bytes(b"\0" * (MAX_SOURCE_BYTES + 1))

            for value, expected in (
                ("", "icon.invalid-path"),
                ("missing.png", "icon.not-found"),
                ("../not-an-image.png", "icon.unsupported"),
                ("../unsafe.svg", "icon.unsafe"),
                ("../oversized.png", "icon.too-large"),
            ):
                with self.subTest(icon=value):
                    set_interface_fields(root, "alpha", icon=value)

                    result = inspect_skills([root / "alpha"])[0]

                    codes = [
                        record.code
                        for record in result["diagnostics"]
                        if record.severity == "error"
                    ]
                    self.assertIn(expected, codes)
                    self.assertNotIn("icon.invalid", codes)

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

            for source, expected_code in (
                ("../invalid.png", "icon.unsupported"),
                ("../unsafe.svg", "icon.unsafe"),
            ):
                with self.subTest(source=source):
                    set_interface_fields(root, "alpha", icon=source)
                    result = inspect_skills([root / "alpha"])[0]
                    self.assertIn(expected_code, diagnostic_codes(result, "error"))
