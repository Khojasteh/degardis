"""The command-line surface: five commands, their help, and their exit status.

Every help text that names the source format reads `CURRENT_FORMAT_VERSION` from
the module whose check enforces it, so none can drift from what `validate`
accepts.

`inspect` is written for an AI agent running the installed CLI, which has this
help and nothing else: no README, no docs directory. Its epilog is therefore the
complete account of the command and of the CLI around it — the dimensions, the
output legend, how to gate on the result, the exit status, the sibling commands
it needs next, and runnable examples.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .build import SkillCompiler
from .explain import codes_by_namespace, explanation, known_codes, known_codes_message
from .model import CURRENT_FORMAT_VERSION, BLOCKED_OUTCOME, DegardisError
from .output import (
    write_build_report,
    write_check_explanations,
    write_inspect_report,
    write_skill_list,
    write_validation_report,
)
from .registry import discover_skill_paths
from .sources import BINDING_PHASES, HOOK_PHASES, SELECTOR_FORMS, STEP_FORMS
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
            "Compile a portable skill source into a compact Markdown control "
            "plane plus deterministic execution modules."
        ),
        epilog=f"""\
A source is format {CURRENT_FORMAT_VERSION}. Each selected YAML file defines one
construct whose lowercase-hyphenated file stem is its id.

Run `degardis COMMAND -h` for that command's options and examples.

Examples:
  degardis list examples/structured-summary
  degardis validate examples/structured-summary
  degardis build examples/structured-summary --output .artifacts
  degardis inspect examples/structured-summary --all
  degardis explain rule.unmatched workflow.invalid-edge
""",
        formatter_class=HELP_FORMATTER,
    )
    command.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subcommands = command.add_subparsers(
        dest="command", required=True, title="commands", metavar="COMMAND"
    )

    list_command = subcommands.add_parser(
        "list",
        help="summarize selected skills and what each one selects",
        description=(
            "Report each selected skill's identity, the constructs its manifest "
            "selects, its available profiles, whether it ships scripts, and where "
            "its source is. Writes nothing."
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
            "findings in one run: the manifest and its content selection, each "
            "construct's schema, every selector and expression, each workflow's "
            "graph and value flow, policy and rule activation, protocol state "
            "reachability, pattern expansion, heuristic and guidance placement, "
            "profile independence, and the generated document's node labels, "
            "same-document transitions, and outbound references. Writes nothing."
        ),
        epilog=f"""\
Exit status is 0 when no skill reports an error, and 1 otherwise. A warning does
not fail the run unless --fail-on-warning is given.

A pass means the sources compile to a complete execution graph whose every
transition stays inside the generated SKILL.md. It does not mean the skill guides
an agent well: the compiler validates declarations and relations it can observe,
and never the meaning of prose.

A source is format {CURRENT_FORMAT_VERSION}. Every finding carries a check code:
run `degardis explain CODE` for what triggers it, why it matters, and a failing
and a passing example.

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
            "Validate and compile each selected skill, render compact SKILL.md plus "
            "required execution modules, write supplementary reference pages, "
            "copy the references, "
            "scripts, and assets the manifest selects, and replace each output "
            "artifact atomically. Nothing is written unless every selected skill "
            "passes."
        ),
        epilog="""\
Build into a throwaway directory rather than a live agent skill directory: a
rebuild replaces that skill's folder and ZIP there. A build whose --output
overlaps a source tree is refused.

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
            "Report what a skill compiles to and what each binding construct was "
            "lowered into, with every error and warning aggregated in one run. "
            "This command is for AI agents: its output is line-oriented and "
            "shaped for minimum token cost, not for a person to read. The help "
            "below is its complete account."
        ),
        epilog=f"""\
Dimensions:
{describe_inspect_dimensions()}
Reported by default: {', '.join(DEFAULT_INSPECT_DIMENSIONS)}
--only selects dimensions; --all reports every one. Neither changes which checks
run: `validate`, this report, and `build` run the same checks over the same
compilation and set the same exit status.

Source format {CURRENT_FORMAT_VERSION}. Each selected YAML file defines one
construct, and its lowercase-hyphenated file stem is that construct's id.
Step forms: {', '.join(STEP_FORMS)}.
Selector forms: {', '.join(SELECTOR_FORMS)}.
Policy and rule phases: {', '.join(BINDING_PHASES)}.
Protocol hook phases: {', '.join(HOOK_PHASES)}.

Legend. `skill` opens with the name, version, title, root, description length,
primary workflow, and one count per selected content key. A `workflows` row is
`ID STATUS [from CALLER] N steps N nodes PATH BYTES`, where STATUS is primary,
reached, or unreached, followed by an indented `entry LABEL - COMMAND` and the
outcomes and inputs the workflow declares. An `execution` row is
`LABEL KIND [EDGE->TARGET, ...]` and then the node's own command; a target of
`{BLOCKED_OUTCOME}` is the compiler-owned outcome every binding check returns on
failure. A `lowering` row is `KIND ID lowered|not-lowered NODES`: not-lowered
means a bound binding item reached no generated node, which is an error, since a
requirement no node states is a requirement no agent can act on. `attention`
reports the generated SKILL.md size, execution-module bytes/count/maximum,
`path worst BYTESB | loads COUNT`, supplementary reference size, and outbound-link
counts, then one `link TARGET at NODE` row per supplementary link. Path bytes and
loads are independent worst cases from the primary entry;
each call is charged again and follows only its matching outcome. These are
structural upper bounds, with no assumed branch frequencies or host caching;
they exclude SKILL.md, optional material, and resources. A `diagnostics` row is
`SEVERITY CODE LOCATION MESSAGE`.

Gating. Exit status is 0 when no skill reports an error and 1 otherwise, so
`degardis inspect PATH --only diagnostics` is enough to gate a change; add
--fail-on-warning to treat a warning as a failure.

Next. `degardis explain CODE [CODE ...]` gives the trigger, the impact, and a
failing and a passing example for any code above. `degardis validate PATH` is the
same findings shaped for a person. `degardis build PATH --output DIR` writes the
bundle. Run `degardis build -h` before writing anywhere.

Examples:
  degardis inspect ./skill
  degardis inspect ./skill --only diagnostics
  degardis inspect ./skill --only execution,lowering,attention
  degardis inspect ./skill --all --body-text
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
        "--body-text",
        action="store_true",
        help=(
            "append the generated SKILL.md, preserving its lines with two "
            "spaces of indentation"
        ),
    )
    _add_fail_on_warning(inspect_command, "a source that only warns fails this run")

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
  degardis explain source.rejected-yaml
  degardis explain rule.unmatched render.load-bearing-reference
""",
        formatter_class=HELP_FORMATTER,
    )
    explain_command.add_argument(
        "codes",
        nargs="+",
        metavar="CODE",
        help=(
            "one or more check codes as reported by validate or inspect, such as "
            "rule.unmatched"
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

    skill_paths = discover_skill_paths(args.paths)

    if args.command == "inspect":
        selected = [name for group in args.dimensions or [] for name in group]
        if args.all_dimensions:
            selected = list(INSPECT_DIMENSIONS)
        dimensions = select_inspect_dimensions(selected)
        results = inspect_skills(skill_paths, include_body=args.body_text)
        _promote(results, args.fail_on_warning)
        write_inspect_report(sys.stdout, results, dimensions, body=args.body_text)
        return int(any(result["errors"] for result in results))

    if args.command == "validate":
        results = inspect_skills(skill_paths)
        promoted = _promote(results, args.fail_on_warning)
        write_validation_report(sys.stdout, results, promoted_warnings=promoted)
        return int(any(result["errors"] for result in results))

    if args.command == "list":
        write_skill_list(sys.stdout, inspect_skills(skill_paths))
        return 0

    compiler = SkillCompiler(skill_paths)
    paths = compiler.build(
        args.output, as_zip=args.zip, fail_on_warning=args.fail_on_warning
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
