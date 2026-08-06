from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .build import SkillCompiler
from .model import DegardisError
from .output import (
    write_agent_report,
    write_build_report,
    write_profile_matches,
    write_skill_list,
    write_validation_report,
)
from .registry import discover_skill_paths, load_skill_path, load_skill_profiles
from .resolver import ALLOWED_ENTRY_KINDS, profile_matches
from .validate import (
    AGENT_DIMENSIONS,
    DEFAULT_AGENT_DIMENSIONS,
    inspect_skills,
    select_agent_dimensions,
)


HELP_FORMATTER = argparse.RawDescriptionHelpFormatter


def _expand_path(value: str) -> Path:
    """Expand and resolve a CLI path using one uniform policy."""
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def _dimensions(value: str) -> list[str]:
    """Accept one dimension, or several separated by commas."""
    names = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [name for name in names if name not in AGENT_DIMENSIONS]
    if not names or unknown:
        raise argparse.ArgumentTypeError(
            f"invalid dimension: {value}; choose from "
            f"{', '.join(sorted(AGENT_DIMENSIONS))}"
        )
    return names


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
  degardis agent examples/structured-summary --all
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

    agent_command = subcommands.add_parser(
        "agent",
        help="report source intelligence for an AI agent",
        description=(
            "Report everything an AI agent needs to review, repair, and budget "
            "a skill, with all errors and warnings aggregated in one run. This "
            "command is for AI agents: its compact output is shaped for minimum "
            "token cost and its format is not stable. Use list for a readable "
            "summary and validate for a pass or fail gate."
        ),
        epilog=f"""\
Dimensions: {', '.join(AGENT_DIMENSIONS)}
Reported by default: {', '.join(DEFAULT_AGENT_DIMENSIONS)}
Entry kinds known to this compiler: {', '.join(sorted(ALLOWED_ENTRY_KINDS))}
(an unrecognized kind is a warning, not an error, and compiles as declared)

Examples:
  degardis agent examples/structured-summary
  degardis agent examples/structured-summary --only entries,outputs
  degardis agent examples/structured-summary --all
  degardis agent examples/structured-summary --profile detailed --only budget
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(agent_command)
    agent_command.add_argument(
        "--only",
        action="append",
        dest="dimensions",
        type=_dimensions,
        metavar="DIMENSION[,DIMENSION...]",
        help=(
            "report the named dimensions instead of the default set; repeat "
            "or comma-separate to combine. Available: "
            + ", ".join(sorted(AGENT_DIMENSIONS))
        ),
    )
    agent_command.add_argument(
        "--all",
        action="store_true",
        dest="all_dimensions",
        help="report every dimension",
    )
    agent_command.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        metavar="[SKILL:]PROFILE",
        help=(
            "measure and inventory the bundle this profile selection would "
            "build; defaults to the manifest defaults, as an unqualified build "
            "does"
        ),
    )

    list_command = subcommands.add_parser(
        "list",
        help="summarize selected skills and profiles",
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
        results = inspect_skills(skill_paths)
        write_validation_report(sys.stdout, results)
        return int(any(result["errors"] for result in results))

    if args.command == "agent":
        results = inspect_skills(skill_paths, args.profiles)
        selected = [name for group in args.dimensions or [] for name in group]
        if args.all_dimensions:
            selected = list(AGENT_DIMENSIONS)
        write_agent_report(
            sys.stdout,
            results,
            select_agent_dimensions(selected),
        )
        return int(any(result["errors"] for result in results))

    compiler = SkillCompiler(skill_paths)
    if args.profiles:
        write_profile_matches(
            sys.stdout,
            profile_matches(skill_paths, args.profiles),
        )
    paths = compiler.build(args.output, args.profiles, as_zip=args.zip)
    skills = [load_skill_path(path) for path in skill_paths]
    write_build_report(
        sys.stdout,
        skills,
        paths,
        as_zip=args.zip,
        warnings=compiler.warnings,
        metrics=compiler.metrics,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except (DegardisError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
