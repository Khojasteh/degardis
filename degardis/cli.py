from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

from . import __version__
from .build import SkillCompiler
from .model import DegardisError, DegardisWarning
from .output import (
    write_build_report,
    write_profile_matches,
    write_skill_list,
    write_validation_report,
)
from .registry import discover_skill_paths, load_skill_path, load_skill_profiles
from .resolver import collect_skills, profile_matches
from .validate import bundle_warnings, validate_skill


HELP_FORMATTER = argparse.RawDescriptionHelpFormatter


def _expand_path(value: str) -> Path:
    """Expand and resolve a CLI path using one uniform policy."""
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def _add_skill_paths(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "paths",
        nargs="+",
        type=_expand_path,
        metavar="PATH",
        help=(
            "skill directory, or a directory recursively containing skill "
            "directories"
        ),
    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="degardis",
        description="Compile self-contained agent skills into installable bundles.",
        epilog="""\
Run `degardis COMMAND -h` for that command's options and examples.

Examples:
  degardis list examples/structured-summary
  degardis validate examples/structured-summary
  degardis build examples/structured-summary --profile detailed --output .artifacts
""",
        formatter_class=HELP_FORMATTER,
    )
    command.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subcommands = command.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    build = subcommands.add_parser(
        "build",
        help="build one or more self-contained skills",
        description="Build selected skills into installable skill bundles.",
        epilog="""\
Examples:
  degardis build examples/structured-summary --output .artifacts
  degardis build examples/structured-summary --profile detailed --output .artifacts
  degardis build examples/structured-summary --zip --output dist
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(build)
    build.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        metavar="[SKILL:]PROFILE",
        help=(
            "profile to include; an unqualified name matches every selected "
            "skill, and all includes every selected skill's profiles"
        ),
    )
    build.add_argument(
        "--output",
        type=_expand_path,
        required=True,
        metavar="PATH",
        help="output directory",
    )
    build.add_argument(
        "--zip",
        action="store_true",
        help="output one zip archive per skill instead of an uncompressed folder",
    )

    validate_command = subcommands.add_parser(
        "validate",
        help="validate one or more skill sources",
        description="Validate explicit skills or recursively discovered skills.",
        epilog="""\
Examples:
  degardis validate examples/structured-summary
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(validate_command)

    list_command = subcommands.add_parser(
        "list",
        help="inspect selected skills and profiles",
        description="Show metadata and profiles for selected skills.",
        epilog="""\
Examples:
  degardis list examples/structured-summary
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(list_command)
    return command


def _normalize_help_position(argv: list[str]) -> list[str]:
    """Let ``-h``/``--help`` work before or after the command name.

    argparse only recognizes ``-h`` on the parser that reaches it, so
    ``degardis -h build`` shows the top-level help instead of the ``build``
    command's help that ``degardis build -h`` shows. Moving a leading
    ``-h``/``--help`` after the command name makes both spellings equivalent.
    """
    if (
        len(argv) >= 2
        and argv[0] in ("-h", "--help")
        and not argv[1].startswith("-")
    ):
        return [argv[1], argv[0], *argv[2:]]
    return argv


def _run(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(_normalize_help_position(tokens))
    skill_paths = discover_skill_paths(args.paths)

    if args.command == "list":
        skills = [load_skill_path(path) for path in skill_paths]
        details = [(skill, load_skill_profiles(skill)) for skill in skills]
        write_skill_list(sys.stdout, details)
        return 0

    if args.command == "validate":
        results = []
        for path in skill_paths:
            skill = load_skill_path(path)
            errors = validate_skill(path)
            skill_warnings = (
                []
                if errors
                else bundle_warnings(collect_skills([path])[0])
            )
            results.append((skill, errors, skill_warnings))
        write_validation_report(sys.stdout, results)
        return int(any(errors for _, errors, _ in results))

    compiler = SkillCompiler(skill_paths)
    if args.profiles:
        write_profile_matches(
            sys.stdout,
            profile_matches(skill_paths, args.profiles),
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DegardisWarning)
        paths = compiler.build(args.output, args.profiles, as_zip=args.zip)
    for warning in caught:
        print(f"[WARNING] {warning.message}", file=sys.stderr)
    skills = [load_skill_path(path) for path in skill_paths]
    write_build_report(sys.stdout, skills, paths, as_zip=args.zip)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except (DegardisError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
