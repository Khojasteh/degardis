from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath

import resvg_py
from PIL import Image, ImageOps, UnidentifiedImageError

from .model import DegardisError, Skill


ICON_ROLES = ("small", "large")
ICON_OUTPUTS = {
    "small": "assets/icon-small.png",
    "large": "assets/icon-large.png",
}
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 64 * 1024 * 1024
UNSAFE_SVG_ELEMENTS = {"script", "foreignObject"}
EXTERNAL_CSS_URL = re.compile(r"url\(\s*['\"]?(?!#|data:)", re.IGNORECASE)


def resolve_icon_sources(skill: Skill) -> dict[str, Path]:
    interface = skill.interface
    fallback = _resolve_icon_path(skill, "icon")
    sources: dict[str, Path] = {}
    for role in ICON_ROLES:
        explicit = _resolve_icon_path(skill, f"icon_{role}")
        source = explicit or fallback
        if source is not None:
            sources[role] = source
    return sources


def _resolve_icon_path(skill: Skill, field: str) -> Path | None:
    if field not in skill.interface:
        return None
    value = skill.interface[field]
    if not isinstance(value, str) or not value.strip():
        raise DegardisError(
            f"{skill.name}: interface.{field} must be a non-empty relative path"
        )
    if (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    ):
        raise DegardisError(
            f"{skill.name}: interface.{field} must be relative to the skill directory"
        )
    source = (skill.root / value).resolve()
    if not source.is_file():
        raise DegardisError(
            f"{skill.name}: interface.{field} icon not found: {value}"
        )
    return source


def validate_icon_sources(sources: dict[str, Path]) -> None:
    for role, source in sources.items():
        render_icon(source, role)


def render_icon_assets(sources: dict[str, Path]) -> dict[str, bytes]:
    return {
        ICON_OUTPUTS[role]: render_icon(source, role)
        for role, source in sources.items()
    }


def render_icon(source: Path, role: str) -> bytes:
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            raise DegardisError(
                f"Icon source exceeds {MAX_SOURCE_BYTES} bytes: {source}"
            )
        if source.suffix.casefold() == ".svg":
            image = _render_svg(source)
        else:
            image = _open_raster(source, role)
        return _encode_png(image, source)
    except DegardisError:
        raise
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise DegardisError(f"Cannot convert icon source {source}: {exc}") from exc


def _render_svg(source: Path) -> Image.Image:
    markup = source.read_text(encoding="utf-8-sig")
    _validate_svg(markup, source)
    rendered = resvg_py.svg_to_bytes(
        svg_string=markup,
        skip_system_fonts=True,
        image_rendering="optimize_quality",
    )
    with Image.open(io.BytesIO(rendered)) as image:
        image.load()
        return image.convert("RGBA")


def _validate_svg(markup: str, source: Path) -> None:
    try:
        root = ET.fromstring(markup)
    except ET.ParseError as exc:
        raise DegardisError(f"Invalid SVG icon {source}: {exc}") from exc
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in UNSAFE_SVG_ELEMENTS:
            raise DegardisError(
                f"Unsafe SVG icon {source}: {name} is not allowed"
            )
        for attribute, value in element.attrib.items():
            if attribute.rsplit("}", 1)[-1] == "href":
                reference = value.strip()
                if reference and not (
                    reference.startswith("#")
                    or reference.casefold().startswith("data:image/")
                ):
                    raise DegardisError(
                        f"Unsafe SVG icon {source}: external references are not allowed"
                    )
            if EXTERNAL_CSS_URL.search(value):
                raise DegardisError(
                    f"Unsafe SVG icon {source}: external CSS URLs are not allowed"
                )
        if element.text and EXTERNAL_CSS_URL.search(element.text):
            raise DegardisError(
                f"Unsafe SVG icon {source}: external CSS URLs are not allowed"
            )


def _open_raster(source: Path, role: str) -> Image.Image:
    with Image.open(source) as opened:
        image = opened
        if opened.format == "ICO" and hasattr(opened, "ico"):
            sizes = sorted(opened.ico.sizes())
            if sizes:
                selected = _select_ico_size(sizes, role)
                image = opened.ico.getimage(selected)
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_SOURCE_PIXELS:
            raise DegardisError(
                f"Icon source has unsupported dimensions {width}x{height}: {source}"
            )
        image.load()
        return ImageOps.exif_transpose(image).convert("RGBA")


def _select_ico_size(
    sizes: list[tuple[int, int]], role: str
) -> tuple[int, int]:
    key = lambda item: (item[0] * item[1], max(item), min(item))
    return min(sizes, key=key) if role == "small" else max(sizes, key=key)


def _encode_png(image: Image.Image, source: Path) -> bytes:
    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_SOURCE_PIXELS:
        raise DegardisError(
            f"Icon source has unsupported dimensions {width}x{height}: {source}"
        )
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()
