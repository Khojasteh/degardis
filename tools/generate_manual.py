from __future__ import annotations

import argparse
from pathlib import Path

from degardis.manual import render_manual


TEMPLATE = Path(__file__).resolve().parent / "manual_template.md"
TARGET = Path(__file__).resolve().parents[1] / "docs" / "manual.md"


def render() -> str:
    """Return the document the checked-in manual has to match.

    The staleness check and the write share this, so a reader comparing the two
    commands cannot be told the manual is current by one template and rewritten
    from another.
    """
    return render_manual(TEMPLATE.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the authoring manual from its template and the packaged topics."
    )
    parser.add_argument("--check", action="store_true", help="fail if the checked-in manual is stale")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != expected:
            print("The manual is stale. Run: python -m tools.generate_manual")
            return 1
        print("The manual is current.")
        return 0
    with TARGET.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
