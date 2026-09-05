"""Identify the exact source one inspection covered.

A report says what the checks found; it cannot say what they read. A caller that
validates a skill, keeps the result, and later ships a bundle has no way to show
that the two concern the same bytes, and a stale report is indistinguishable from
a current one. A digest over the selected source files closes that gap: the same
source yields the same value, and any edit that would change the bundle yields a
different one.

The digest normalizes newlines in exactly the files the compiler itself parses
and re-renders, and hashes byte-for-byte the files a build copies unchanged. That
is what keeps one commit's fingerprint equal on a Windows checkout and a Linux CI
runner while still noticing a line ending that really does reach the bundle.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .content import COPIED_CONTENT_KEYS, PARSED_CONTENT_KEYS


SOURCE_FINGERPRINT_ALGORITHM = "sha256"


def _normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _read(path: Path, *, parsed: bool) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return _normalized(data) if parsed else data


def source_fingerprint(
    root: Path, selected: dict[str, list[Path]]
) -> dict[str, Any]:
    """One digest over the manifest and every file the manifest selects."""
    digest = hashlib.new(SOURCE_FINGERPRINT_ALGORITHM)
    counted = 0
    manifest = root / "skill.yaml"
    entries: list[tuple[str, bytes]] = []
    data = _read(manifest, parsed=True)
    if data is not None:
        entries.append(("skill.yaml", data))
    for key in (*PARSED_CONTENT_KEYS, *COPIED_CONTENT_KEYS):
        parsed = key in PARSED_CONTENT_KEYS
        for path in selected.get(key, []):
            data = _read(path, parsed=parsed)
            if data is None:
                continue
            try:
                label = path.relative_to(root).as_posix()
            except ValueError:
                label = path.name
            entries.append((label, data))
    for label, data in sorted(entries):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        counted += 1
    return {
        "algorithm": SOURCE_FINGERPRINT_ALGORITHM,
        "digest": digest.hexdigest(),
        "files": counted,
    }
