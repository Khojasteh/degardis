"""Print the ATX headings in a Markdown file."""

from __future__ import annotations

import argparse
from pathlib import Path


def headings(text: str) -> list[str]:
    return [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("#") and line.lstrip("#").startswith(" ")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    for heading in headings(args.path.read_text(encoding="utf-8")):
        print(heading)


if __name__ == "__main__":
    main()
