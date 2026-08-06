from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .baseline import measure_baselines
from .build import SkillCompiler
from .explain import codes_by_namespace, explanation, known_codes, known_codes_message
from .model import SUPPORTED_FORMAT_VERSIONS, DegardisError
from .output import (
    write_agent_report,
    write_build_report,
    write_check_explanations,
    write_profile_matches,
    write_skill_list,
    write_validation_report,
)
from .registry import discover_skill_paths, load_skill_path
from .resolver import ALLOWED_ENTRY_KINDS, load_skill_profiles, profile_matches
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


def _supported_formats() -> str:
    """Announce the source formats the compiler accepts, oldest to newest.

    Read from the constant the manifest check enforces, so the help cannot claim
    a format the compiler would reject. Support is a set because a release that
    introduces a new source format keeps reading the formats before it, so this
    names every accepted version and, once there is a choice, which one new
    source should declare.
    """
    versions = sorted(SUPPORTED_FORMAT_VERSIONS)
    earlier = ", ".join(str(version) for version in versions[:-1])
    listed = " or ".join(part for part in (earlier, str(versions[-1])) if part)
    newest = f"; declare {versions[-1]} in new source" if len(versions) > 1 else ""
    return f"skill.yaml format_version {listed}{newest}"


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
        epilog=f"""\
Run `degardis COMMAND -h` for that command's options and examples.

Source format: this compiler accepts {_supported_formats()}. A manifest
declaring any other version is rejected by validate, agent, and build.

Examples:
  degardis list examples/structured-summary
  degardis validate examples/structured-summary
  degardis agent examples/structured-summary --all
  degardis explain entry.missing-priority
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
        description=(
            "Build selected skills into installable skill bundles. A build stops "
            "on any error, so a bundle means the sources are well-formed, not "
            "that the skill guides an agent well: no check judges what an "
            "instruction says."
        ),
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
        description=(
            "Validate explicit skills or recursively discovered skills. A pass "
            "means the sources are well-formed and the bundle they generate is "
            "consistent, not that the skill guides an agent well: no check "
            "judges what an instruction says."
        ),
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
            "token cost, not for a person to read, and its line shapes are "
            "stable and meant to be relied on. The legend below gives every one "
            "of them. Use list for a readable summary and validate for a pass "
            "or fail gate."
        ),
        epilog=f"""\
Dimensions: {', '.join(AGENT_DIMENSIONS)}
Reported by default: {', '.join(DEFAULT_AGENT_DIMENSIONS)}
Entry kinds known to this compiler: {', '.join(sorted(ALLOWED_ENTRY_KINDS))}
(an unrecognized kind is a warning, not an error, and compiles as declared)

Legend. A later release may add a section, a check code, or an entry kind, but
not change a shape below. Sizes are bytes of the generated Markdown, paths are
relative to the root in the header, ids drop the `<name>.` prefix, a blank line
separates sections and skills, and listed rows are indented and space-aligned.

  skill <name> <version> "<title>" [(derived title)]
  root  <absolute source directory>
  ids   <name>.*
  desc  <n> chars                 (identity reports the description itself instead)
  main  <primary workflow id>|none
  count <n> entries, <n> workflows, <n> profiles, <n> scripts, <n> assets
  desc|lic|copy <value>|none      identity: description, license, copyright
  body  SKILL.md <n>B <n>L | text <n>B <n>L <n>w | profiles <names>|<n> selected|none
                                  text is SKILL.md without its frontmatter
  refs  entries <n>B | workflows <n>B | profiles <n>B
                                  weight loaded on demand, not up front
  base  <ref> <body and refs sizes on one line>|absent|unmeasured
                                  --baseline only: those sizes as <ref> has them,
                                  absent if <ref> has no such skill, unmeasured if
                                  no SKILL.md could be built from the one it has
  delta <the same sizes, each signed>
                                  --baseline only: current minus base, and only
                                  where both were measured
  workflows <n>                   rows: <id> primary|<step>|unreached <n> steps <path> <n>B
                                  <step> reaches this workflow, as <workflow>.<index>
  entries <n>  <kind> <n>...      rows: <id> <kind>/<priority> <path> <n>B
  profiles <n>  <n> selected      rows: <name> *|- <path> <n>B
                                  * marks a profile the selection includes
  scripts|assets <n>              rows: <path> <n>B
  outputs <n>  <total>B           rows: <path> <n>B <octal mode>
  error|warn <path>[:<line>] <code> <message>
                                  <path> is - for a whole-skill finding, and
                                  <line> appears where the check knows one
  <n> skill(s), <n> error(s), <n> warning(s)
                                  final line, and the only labels that inflect;
                                  count 1 entries and 1 steps stay plural.
                                  0 errors means these sources are well-formed,
                                  not that the skill guides an agent well: no
                                  check judges what an instruction says

Examples:
  degardis agent examples/structured-summary
  degardis agent examples/structured-summary --only entries,outputs
  degardis agent examples/structured-summary --all
  degardis agent examples/structured-summary --profile detailed --only budget
  degardis agent examples/structured-summary --only budget --baseline HEAD
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
            "build; without it, the report covers a bundle with no profile, as "
            "an unqualified build produces one"
        ),
    )
    agent_command.add_argument(
        "--baseline",
        metavar="REF",
        help=(
            "also measure each skill as this git revision has it, and report "
            "the budget difference, which needs budget among the reported "
            "sections. Reads the revision without checking it out, so the "
            "working tree and the index are left alone. The revision's own "
            "errors and warnings are excluded from the report and from the "
            "exit status. --profile applies to both sides; a profile the "
            "revision does not have selects nothing there, so the delta "
            "carries that profile's whole cost"
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

    explain_command = subcommands.add_parser(
        "explain",
        help="explain one or more diagnostic check codes",
        description=(
            "Explain the check each diagnostic code names: what triggers it, why "
            "it matters, and a failing and passing example. Reads no source and "
            "needs no skill path. Every code given is explained in one run; an "
            "unrecognized code exits non-zero and lists every code this version "
            "can report."
        ),
        epilog=f"""\
Namespaces: {', '.join(sorted(codes_by_namespace()))}
Codes: {len(known_codes())}

Examples:
  degardis explain yaml.altered-scalar
  degardis explain entry.missing-priority entry.missing-title
""",
        formatter_class=HELP_FORMATTER,
    )
    explain_command.add_argument(
        "codes",
        nargs="+",
        metavar="CODE",
        help=(
            "one or more check codes as reported by validate or agent, such as "
            "entry.unknown-kind"
        ),
    )
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


def _explain(codes: list[str]) -> int:
    """Explain every code given, then report every one this version does not know.

    An agent reading a report has several codes at once, so all of them are
    explained in one run and every unknown one is named together, rather than
    stopping at the first.
    """
    requested = list(dict.fromkeys(codes))
    found = [(code, explanation(code)) for code in requested]
    unknown = [code for code, entry in found if entry is None]
    write_check_explanations(
        sys.stdout,
        [(code, entry) for code, entry in found if entry is not None],
    )
    if unknown:
        label = "code" if len(unknown) == 1 else "codes"
        raise DegardisError(
            f"Unknown check {label}: {', '.join(unknown)}\n{known_codes_message()}"
        )
    return 0


def _run(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(_normalize_help_position(tokens))

    if args.command == "explain":
        return _explain(args.codes)

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
        selected = [name for group in args.dimensions or [] for name in group]
        if args.all_dimensions:
            selected = list(AGENT_DIMENSIONS)
        dimensions = select_agent_dimensions(selected)
        baselines = None
        if args.baseline:
            if "budget" not in dimensions:
                raise DegardisError(
                    "--baseline reports a budget difference, which the selected "
                    "sections leave out; add budget to --only, or drop --only"
                )
            baselines = measure_baselines(skill_paths, args.baseline, args.profiles)
        results = inspect_skills(skill_paths, args.profiles)
        write_agent_report(sys.stdout, results, dimensions, baselines)
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
