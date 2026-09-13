"""The command-line surface: seven commands, their help, and their exit status.

The root help states the source format, reading `CURRENT_FORMAT_VERSION` from
the module whose check enforces it, and no command's help restates it.

The installed package ships no docs directory, so a command's help and a manual
topic are the only text a reader has. Each epilog is therefore a short paragraph
naming the topic that holds the detail: an epilog grown past that is a manual
topic left incomplete.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .build import SkillCompiler
from .explain import explanation, known_codes_message
from .model import CURRENT_FORMAT_VERSION, DegardisError
from .manual import TOPICS, describe_topics, render_topic
from .output import (
    write_build_report,
    write_check_explanations,
    write_inspect_report,
    write_skill_list,
    write_validation_report,
)
from .progress import status_line
from .registry import discover_skill_paths
from .scaffold import create_skill
from .validate import (
    INSPECT_DIMENSIONS,
    DEFAULT_INSPECT_DIMENSIONS,
    describe_inspect_dimensions,
    inspect_skills,
    promote_warnings,
    select_inspect_dimensions,
)


HELP_FORMATTER = argparse.RawDescriptionHelpFormatter


def _expand_path(value: str) -> Path:
    """Expand and resolve a CLI path using one uniform policy."""
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def _dimensions(value: str) -> list[str]:
    """Accept one dimension, or several separated by commas."""
    names = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [name for name in names if name not in INSPECT_DIMENSIONS]
    if not names or unknown:
        raise argparse.ArgumentTypeError(
            f"invalid dimension: {value}; choices:\n{describe_inspect_dimensions()}"
        )
    return names


def _pages(value: str) -> list[str]:
    """Accept one generated page path, or several separated by commas."""
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        raise argparse.ArgumentTypeError(f"invalid page: {value}")
    return names


def _add_fail_on_warning(command: argparse.ArgumentParser, effect: str) -> None:
    """Offer the strict warning standard, naming what it costs this command."""
    command.add_argument(
        "--fail-on-warning",
        action="store_true",
        help=f"report every warning as an error, so {effect}",
    )


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
        description=(
            "Compile a portable skill source into an installable agent skill"
        ),
        epilog=f"""\
This version accepts source format {CURRENT_FORMAT_VERSION} and no other. A source declaring an
earlier one is refused, and no command converts it: rewrite that source as
format {CURRENT_FORMAT_VERSION} by hand.

Run `degardis COMMAND -h` for that command's options and examples.

Examples:
  degardis init my-skill
  degardis list examples/structured-summary
  degardis validate examples/structured-summary
  degardis build examples/structured-summary --output .artifacts
  degardis inspect examples/structured-summary --all
  degardis explain manifest.unknown-principle knowledge.orphan
  degardis manual layout tasks principles
""",
        formatter_class=HELP_FORMATTER,
    )
    command.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subcommands = command.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    init_command = subcommands.add_parser(
        "init",
        help="write a new skill source tree that already compiles",
        description=(
            "Create a new skill directory with a manifest, one task that "
            "validates and builds as it stands, and the directories the rest of "
            "the format uses. Refuses to write over an existing directory."
        ),
        epilog="""\
Examples:
  degardis init my-skill
  degardis init my-skill --output ./skills
""",
        formatter_class=HELP_FORMATTER,
    )
    init_command.add_argument("name", metavar="NAME", help="the new skill's name")
    init_command.add_argument(
        "-o",
        "--output",
        default=".",
        type=_expand_path,
        metavar="PATH",
        help="directory the skill directory is created in (default: .)",
    )

    list_command = subcommands.add_parser(
        "list",
        help="summarize selected skills and what each one selects",
        description=(
            "Report each selected skill's identity, the tasks a request is routed "
            "to, the sources its manifest selects, its available profiles, "
            "whether it ships scripts, and where its source is. Writes nothing."
        ),
        epilog="""\
Examples:
  degardis list examples/structured-summary
  degardis list ./skills
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(list_command)

    validate_command = subcommands.add_parser(
        "validate",
        help="check selected skills and report every finding",
        description=(
            "Run every structural check over each selected skill and report all "
            "findings in one run, across the manifest, every construct's "
            "frontmatter, every reference between them, and the pages they "
            "generate. Writes nothing."
        ),
        epilog="""\
A pass means the sources compile to a complete bundle whose every generated link
resolves to a file the bundle ships. It does not mean the skill guides an agent
well: nothing here reads the meaning of prose.

Examples:
  degardis validate examples/structured-summary
  degardis validate ./skills --fail-on-warning
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(validate_command)
    _add_fail_on_warning(validate_command, "a source that only warns fails this run")

    build = subcommands.add_parser(
        "build",
        help="compile selected skills into installable bundles",
        description=(
            "Validate each selected skill, then write its bundle: the root that "
            "routes a request, one page per task carrying that task's complete "
            "knowledge closure, the pages a task opens separately, and the files "
            "the manifest selects. Each output artifact is replaced atomically, "
            "and nothing is written unless every selected skill passes."
        ),
        epilog="""\
The output directory is created if it does not exist, and one overlapping a
source path is refused so a build cannot overwrite what it read. A rebuild
replaces the folder and the ZIP already there under the same skill name, so
build into a throwaway directory rather than a live agent skill directory.

Examples:
  degardis build examples/structured-summary --output .artifacts
  degardis build ./skills --output dist --zip
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(build)
    build.add_argument(
        "-o",
        "--output",
        required=True,
        type=_expand_path,
        metavar="PATH",
        help="directory the bundles are written into",
    )
    build.add_argument(
        "--zip",
        action="store_true",
        help="write each bundle as a ZIP archive instead of a folder",
    )
    _add_fail_on_warning(build, "a source that only warns is not built")

    inspect_command = subcommands.add_parser(
        "inspect",
        help="report compilation intelligence for an AI agent",
        description=(
            "Report what a skill compiles to and why each generated page carries "
            "what it carries, with every error and warning aggregated in one "
            "run. This command is for AI agents: its output is line-oriented and "
            "shaped for minimum token cost, not for a person to read."
        ),
        epilog=f"""\
Dimensions:
{describe_inspect_dimensions()}
Reported by default: {', '.join(DEFAULT_INSPECT_DIMENSIONS)}

Run `degardis manual inspection` for each row's shape and what it answers, and
`degardis explain CODE` for any code a `diagnostics` row carries.

Examples:
  degardis inspect ./skill
  degardis inspect ./skill --only diagnostics
  degardis inspect ./skill --only composition,knowledge
  degardis inspect ./skill --only tasks --page SKILL.md
  degardis inspect ./skill --page references/tasks/review.md
""",
        formatter_class=HELP_FORMATTER,
    )
    _add_skill_paths(inspect_command)
    inspect_command.add_argument(
        "--only",
        action="append",
        dest="dimensions",
        type=_dimensions,
        metavar="DIMENSION[,DIMENSION...]",
        help="select report dimensions; repeat or comma-separate to combine",
    )
    inspect_command.add_argument(
        "--all",
        action="store_true",
        dest="all_dimensions",
        help="report every dimension",
    )
    inspect_command.add_argument(
        "--page",
        action="append",
        dest="pages",
        type=_pages,
        metavar="PATH[,PATH...]",
        help=(
            "append the generated text of each named page, such as SKILL.md or "
            "references/tasks/deliver.md, preserving its lines with two spaces of "
            "indentation; repeat or comma-separate to combine"
        ),
    )
    _add_fail_on_warning(inspect_command, "a source that only warns fails this run")

    explain_command = subcommands.add_parser(
        "explain",
        help="explain one or more diagnostic check codes",
        description=(
            "Explain the check each diagnostic code names: what triggers it, why "
            "it matters, and how to resolve it when a resolution is available. "
            "Reads no source and "
            "needs no skill path. Every code given is explained in one run; an "
            "unrecognized code exits non-zero and lists every code this version "
            "can report."
        ),
        epilog="""\
Examples:
  degardis explain source.rejected-yaml
  degardis explain manifest.unknown-principle output.broken-reference
""",
        formatter_class=HELP_FORMATTER,
    )
    explain_command.add_argument(
        "codes",
        nargs="+",
        metavar="CODE",
        help="one or more check codes as reported by build, validate, or inspect"
    )
    manual_command = subcommands.add_parser(
        "manual",
        help="read the source authoring manual by topic",
        description=(
            "Read the authoring manual shipped with this installation. With no "
            "topics, list available topics. Otherwise print each requested topic "
            "once, in request order, as Markdown with field tables and examples. "
            "Works offline, reads no skill source, needs no source path, and "
            "writes no files. Every known topic given is printed in one run; an "
            "unrecognized topic exits non-zero and lists every topic this "
            "version ships."
        ),
        epilog=f"""\
Topics:
{describe_topics()}

Unknown names are reported together, after every known topic has printed.

Examples:
  degardis manual
  degardis manual layout tasks knowledge
  degardis manual principles profiles guides
""",
        formatter_class=HELP_FORMATTER,
    )
    manual_command.add_argument(
        "topics", nargs="*", metavar="TOPIC", help="topic names from the list below"
    )
    return command


def _normalize_help_position(argv: list[str]) -> list[str]:
    """Let ``-h``/``--help`` work before or after the command name.

    argparse only recognizes ``-h`` on the parser that reaches it, so
    ``degardis -h build`` shows the top-level help instead of the ``build``
    command's help that ``degardis build -h`` shows. Moving a leading
    ``-h``/``--help`` after the command name makes both spellings equivalent.
    """
    if len(argv) >= 2 and argv[0] in ("-h", "--help") and not argv[1].startswith("-"):
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
    unknown = [code for code, rule in found if rule is None]
    write_check_explanations(
        sys.stdout, [(code, rule) for code, rule in found if rule is not None]
    )
    if unknown:
        label = "code" if len(unknown) == 1 else "codes"
        raise DegardisError(
            f"Unknown check {label}: {', '.join(unknown)}\n{known_codes_message()}"
        )
    return 0


def _manual(names: list[str]) -> int:
    if not names:
        print(f"Manual topics for source format {CURRENT_FORMAT_VERSION}:\n{describe_topics()}")
        print("\nRun: degardis manual TOPIC [TOPIC ...]")
        return 0
    catalog = {topic.name: topic for topic in TOPICS}
    unknown = []
    for name in dict.fromkeys(names):
        if name in catalog:
            print(render_topic(catalog[name]))
        else:
            unknown.append(name)
    if unknown:
        raise DegardisError(
            f"Unknown manual topics: {', '.join(unknown)}\nAvailable topics:\n{describe_topics()}"
        )
    return 0


def _init(name: str, output: Path) -> int:
    destination = create_skill(output, name)
    print(f"Created {destination}")
    print(
        "Next: degardis validate "
        f"{destination.name}, then degardis build {destination.name} "
        "--output .artifacts"
    )
    return 0


def _generated_pages_message(results: list[dict], missing: list[str]) -> str:
    """Name every page nothing generated, then what each skill does generate.

    A reader who reached this asked for a page by path and got the path wrong,
    so the pages that exist are the answer, listed per skill because the set is
    the skill's own. Every unknown path is named at once, as `explain` names
    every unknown code at once.
    """
    label = "page" if len(missing) == 1 else "pages"
    lines = [f"No selected skill generates {label}: {', '.join(missing)}"]
    for result in results:
        lines.append(f"Pages {result['name']} generates:")
        lines.extend(f"  {page}" for page in result["pages"])
    return "\n".join(lines)


def _promote(results: list[dict], fail_on_warning: bool) -> int:
    """Apply the caller's warning standard, reporting how many findings it moved.

    The count is taken before the promotion because nothing afterwards can tell a
    finding the checks called an error from one this run did.
    """
    if not fail_on_warning:
        return 0
    promoted = sum(len(result["warnings"]) for result in results)
    promote_warnings(results)
    return promoted


def _run(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(_normalize_help_position(tokens))

    if args.command == "explain":
        return _explain(args.codes)
    if args.command == "manual":
        return _manual(args.topics)
    if args.command == "init":
        return _init(args.name, args.output)

    skill_paths = discover_skill_paths(args.paths)

    if args.command == "inspect":
        selected = [name for group in args.dimensions or [] for name in group]
        if args.all_dimensions:
            selected = list(INSPECT_DIMENSIONS)
        dimensions = select_inspect_dimensions(selected)
        pages = list(
            dict.fromkeys(page for group in args.pages or [] for page in group)
        )
        with status_line(sys.stderr) as watcher:
            results = inspect_skills(skill_paths, body_pages=pages, progress=watcher)
        _promote(results, args.fail_on_warning)
        write_inspect_report(sys.stdout, results, dimensions, pages=pages)
        missing = [
            page
            for page in pages
            if not any(page in result["page_text"] for result in results)
        ]
        if missing:
            raise DegardisError(_generated_pages_message(results, missing))
        return int(any(result["errors"] for result in results))

    if args.command == "validate":
        with status_line(sys.stderr) as watcher:
            results = inspect_skills(skill_paths, progress=watcher)
        promoted = _promote(results, args.fail_on_warning)
        write_validation_report(sys.stdout, results, promoted_warnings=promoted)
        return int(any(result["errors"] for result in results))

    if args.command == "list":
        with status_line(sys.stderr) as watcher:
            listed = inspect_skills(skill_paths, progress=watcher)
        write_skill_list(sys.stdout, listed)
        return 0

    compiler = SkillCompiler(skill_paths)
    # The line is erased before the report starts, so the two never share a row.
    with status_line(sys.stderr) as watcher:
        paths = compiler.build(
            args.output,
            as_zip=args.zip,
            fail_on_warning=args.fail_on_warning,
            progress=watcher,
        )
    write_build_report(
        sys.stdout,
        compiler.skills,
        paths,
        as_zip=args.zip,
        warnings=compiler.warnings,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except (DegardisError, OSError) as error:
        # A failure carrying a check code is spelled the way the validate report
        # spells one, so the same `degardis explain CODE` follows from either.
        code = getattr(error, "code", "")
        suffix = f" ({code})" if code else ""
        print(f"[ERROR] {error}{suffix}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
