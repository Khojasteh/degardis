"""The interface icon: one source file a bundle ships exactly as it is.

The icon is read through one host's product metadata, and that host displays
the formats an icon is drawn in, so the compiler converts nothing: the bytes
the author drew are the bytes the bundle carries, wherever it is built. What
the compiler owes the host is that the file is the image its name says it is,
is not unreasonably large, and carries nothing a display should not run.
"""

from __future__ import annotations

import io
import re
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING

from .model import DegardisError, Skill

if TYPE_CHECKING:
    from PIL import Image

# The imaging library is imported where a raster icon is actually checked, not
# here. Loading it is the largest single import this package pulls in, and a
# skill that declares no icon, a command that reads no skill, and `-h` all
# reach this module without checking anything.


ICON_ROLES = ("small", "large")
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 64 * 1024 * 1024

# The formats a host displays, by the suffix it reads the format from, each
# with the name the imaging library reports for a file that really is one. An
# SVG is text the compiler screens itself.
ICON_FORMATS: dict[str, str | None] = {
    ".svg": None,
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
}
UNSAFE_SVG_ELEMENTS = {"script", "foreignObject"}
# An attribute such as `onload` is script attached to an element rather than
# written as one, and runs wherever a script element would.
EVENT_HANDLER_ATTRIBUTE = re.compile(r"on[a-z]+", re.IGNORECASE)
# A stylesheet reaches outside the file through `url()` or through `@import`,
# which takes a bare string as readily as a `url()`.
EXTERNAL_CSS_URL = re.compile(
    r"url\(\s*['\"]?(?!#|data:)|@import\s+(?!url\()['\"]?(?!data:)", re.IGNORECASE
)


class IconError(DegardisError):
    """An unusable interface icon, carrying the check code for what is wrong.

    Icon sources fail in ways that need different repairs: a path to correct, a
    file to add, an image to shrink, a format to replace, unsafe markup to
    remove. Each failure names its own check so a report says which of those it
    is, rather than one code for every icon problem.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message, code)


def resolve_icon_source(skill: Skill) -> Path | None:
    """The file `interface.icon` names, or None where the skill declares none."""
    if "icon" not in skill.interface:
        return None
    value = skill.interface["icon"]
    if not isinstance(value, str) or not value.strip():
        raise IconError(
            f"{skill.name}: interface.icon must be a non-empty relative path",
            "icon.invalid-path",
        )
    if (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    ):
        raise IconError(
            f"{skill.name}: interface.icon must be relative to the skill directory",
            "icon.invalid-path",
        )
    source = (skill.root / value).resolve()
    if not source.is_relative_to(skill.root.resolve()):
        raise IconError(
            f"{skill.name}: interface.icon must stay inside the skill directory: "
            f"{value}",
            "icon.invalid-path",
        )
    if not source.is_file():
        raise IconError(
            f"{skill.name}: interface.icon not found: {value}",
            "icon.not-found",
        )
    return source


def _icon_suffix(source: Path) -> str:
    """The suffix a host reads the icon's format from, in lower case.

    A file under a suffix no host displays is refused before it is read.
    """
    suffix = source.suffix.casefold()
    if suffix not in ICON_FORMATS:
        raise IconError(
            f"Unsupported icon format {source.suffix or '(no suffix)'}: {source}; "
            f"use one of {', '.join(ICON_FORMATS)}",
            "icon.unsupported",
        )
    return suffix


def read_icon(source: Path) -> bytes:
    """The icon's bytes, exactly as a bundle will carry them, once checked.

    The checks are what a host would otherwise discover on display: a file over
    the size limit, an SVG that does not parse or reaches outside itself, and a
    raster file that is not the image its suffix states, is damaged, or declares
    more pixels than any icon needs.
    """
    suffix = _icon_suffix(source)
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            raise IconError(
                f"Icon source exceeds {MAX_SOURCE_BYTES} bytes: {source}",
                "icon.too-large",
            )
        data = source.read_bytes()
    except OSError as exc:
        raise IconError(
            f"Cannot read icon source {source}: {exc}", "icon.unsupported"
        ) from exc
    expected = ICON_FORMATS[suffix]
    if expected is None:
        _check_svg(data, source)
    else:
        _check_raster(data, expected, source)
    return data


def _check_svg(data: bytes, source: Path) -> None:
    """Refuse an SVG a host could not display, or should not.

    The file ships as it is and a host displays it, so the screen is a trust
    boundary: a script or foreignObject element, or an event-handler attribute,
    is code that would run wherever the skill is shown, and an external
    reference, a stylesheet `@import` included, would make the icon depend on a
    file or a network the bundle does not carry.
    """
    try:
        root = ET.fromstring(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise IconError(
            f"Invalid SVG icon {source}: {exc}", "icon.unsupported"
        ) from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise IconError(
            f"Invalid SVG icon {source}: the document is not an svg element",
            "icon.unsupported",
        )
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in UNSAFE_SVG_ELEMENTS:
            raise IconError(
                f"Unsafe SVG icon {source}: {name} is not allowed",
                "icon.unsafe",
            )
        for attribute, value in element.attrib.items():
            local = attribute.rsplit("}", 1)[-1]
            if EVENT_HANDLER_ATTRIBUTE.fullmatch(local):
                raise IconError(
                    f"Unsafe SVG icon {source}: the {local} attribute is a script "
                    "and is not allowed",
                    "icon.unsafe",
                )
            if local == "href":
                reference = value.strip()
                if reference and not (
                    reference.startswith("#")
                    or reference.casefold().startswith("data:image/")
                ):
                    raise IconError(
                        f"Unsafe SVG icon {source}: external references are "
                        "not allowed",
                        "icon.unsafe",
                    )
            if EXTERNAL_CSS_URL.search(value):
                raise IconError(
                    f"Unsafe SVG icon {source}: external CSS URLs are not allowed",
                    "icon.unsafe",
                )
        if element.text and EXTERNAL_CSS_URL.search(element.text):
            raise IconError(
                f"Unsafe SVG icon {source}: external CSS URLs are not allowed",
                "icon.unsafe",
            )


def _check_raster(data: bytes, expected: str, source: Path) -> None:
    """Refuse a raster icon a host could not display as the file its name states.

    The imaging library reads the header only: enough to know the format and
    the size, which is where a mislabeled file, a damaged one, and one that
    declares more pixels than any icon needs all show. Its own refusal of an
    image whose declared size could exhaust memory is this module's pixel limit
    reached first by the library, so both are reported as one: a small file can
    declare an enormous image, and neither a raised library error nor a stray
    warning tells its author which check refused it.
    """
    from PIL import Image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != expected:
                    raise IconError(
                        f"Icon source {source} is {image.format or 'not an image'}, "
                        f"not the {expected} its suffix states",
                        "icon.unsupported",
                    )
                _check_dimensions(image, source)
                image.verify()
    except IconError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise IconError(
            f"Icon source is too large to display safely: {source}: {exc}",
            "icon.too-large",
        ) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise IconError(
            f"Cannot read icon source {source}: {exc}", "icon.unsupported"
        ) from exc


def _check_dimensions(image: Image.Image, source: Path) -> None:
    """Reject an image no icon can be shown from, and one too large to accept."""
    width, height = image.size
    if width <= 0 or height <= 0:
        raise IconError(
            f"Icon source has unusable dimensions {width}x{height}: {source}",
            "icon.unsupported",
        )
    if width * height > MAX_SOURCE_PIXELS:
        raise IconError(
            f"Icon source exceeds {MAX_SOURCE_PIXELS} pixels "
            f"at {width}x{height}: {source}",
            "icon.too-large",
        )
