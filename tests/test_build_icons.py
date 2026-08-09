"""The icons a build renders and packages."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from PIL import Image

from degardis.build import build_skills
from degardis.model import DegardisError

from tests.support import (
    copy_skills,
    folder_text,
    set_interface_fields,
    write_raster_icon,
    zip_names,
    zip_text,
)


class BuildIconTests(unittest.TestCase):
    def test_shared_ico_generates_both_icons_for_multiple_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.ico"
            write_raster_icon(shared, (30, 120, 220, 255), format_name="ICO")
            set_interface_fields(root, "alpha", icon="../shared.ico")
            set_interface_fields(root, "beta", icon="../shared.ico")

            paths = build_skills(root, Path(directory) / "output")

            for path in paths[:2]:
                small = path / "assets" / "icon-small.png"
                large = path / "assets" / "icon-large.png"
                self.assertTrue(small.is_file())
                self.assertTrue(large.is_file())
                with Image.open(small) as image:
                    self.assertEqual(("PNG", (32, 32)), (image.format, image.size))
                with Image.open(large) as image:
                    self.assertEqual(("PNG", (256, 256)), (image.format, image.size))
                metadata = yaml.safe_load(
                    folder_text(path, "agents/openai.yaml")
                )["interface"]
                self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
                self.assertEqual("./assets/icon-large.png", metadata["icon_large"])
                self.assertNotIn("icon", metadata)

    def test_explicit_role_overrides_fallback_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            fallback = root / "fallback.png"
            small = root / "alpha" / "small.png"
            write_raster_icon(fallback, (220, 20, 20, 255))
            write_raster_icon(small, (20, 40, 220, 255))
            set_interface_fields(
                root,
                "alpha",
                icon="../fallback.png",
                icon_small="small.png",
            )

            path = build_skills(root / "alpha", root / "output")[0]

            with Image.open(path / "assets" / "icon-small.png") as image:
                self.assertEqual((20, 40, 220, 255), image.getpixel((128, 96)))
            with Image.open(path / "assets" / "icon-large.png") as image:
                self.assertEqual((220, 20, 20, 255), image.getpixel((128, 96)))

    def test_one_explicit_icon_role_does_not_create_the_other(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            small = root / "small.png"
            write_raster_icon(small, (10, 180, 80, 255))
            set_interface_fields(root, "alpha", icon_small="../small.png")

            path = build_skills(root / "alpha", root / "output")[0]

            self.assertTrue((path / "assets" / "icon-small.png").is_file())
            self.assertFalse((path / "assets" / "icon-large.png").exists())
            metadata = yaml.safe_load(
                folder_text(path, "agents/openai.yaml")
            )["interface"]
            self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
            self.assertNotIn("icon_large", metadata)

    def test_svg_icon_is_rendered_to_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            svg = root / "icon.svg"
            svg.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" '
                    'viewBox="0 0 40 20">'
                    '<rect width="40" height="20" fill="#7c3aed"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            set_interface_fields(root, "alpha", icon="../icon.svg")

            path = build_skills(root / "alpha", root / "output")[0]

            with Image.open(path / "assets" / "icon-large.png") as image:
                self.assertEqual(("PNG", (40, 20)), (image.format, image.size))
                self.assertEqual((124, 58, 237, 255), image.getpixel((20, 10)))

    def test_generated_icon_path_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.png"
            generated_path = root / "alpha" / "assets" / "icon-small.png"
            write_raster_icon(shared, (255, 0, 0, 255))
            write_raster_icon(generated_path, (0, 0, 255, 255))
            set_interface_fields(root, "alpha", icon="../shared.png")

            with self.assertRaisesRegex(DegardisError, "output path collision"):
                build_skills(root / "alpha", root / "output")

    def test_generated_icons_are_packaged_in_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.webp"
            write_raster_icon(shared, (90, 40, 180, 255), format_name="WEBP")
            set_interface_fields(root, "alpha", icon="../shared.webp")

            path = build_skills(
                root / "alpha",
                root / "output",
                as_zip=True,
            )[0]

            names = zip_names(path)
            self.assertIn("assets/icon-small.png", names)
            self.assertIn("assets/icon-large.png", names)
            metadata = yaml.safe_load(zip_text(path, "agents/openai.yaml"))[
                "interface"
            ]
            self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
            self.assertEqual("./assets/icon-large.png", metadata["icon_large"])
